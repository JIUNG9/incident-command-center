"""Domain routing for a mixed-domain corpus.

The brain ingests Slack, Jira, and Confluence, which hold *both* engineering
and business-team content. Embeddings retrieve on topical similarity alone,
so a business "payment refund policy" page scores high for an engineering
"payment-service 5xx" incident query — same words, wrong domain. The answer
layer then quotes a refund SOP as if it were an incident runbook.

The fix is deterministic, not statistical. Business content lives in
*separate* Jira projects, Confluence spaces, and Slack channels from
engineering's. That separation is provenance we already capture: every
imported doc lands at ``archive/<source>/<unit>/...`` where ``<unit>`` is
the Jira project key, the Confluence space key, or the Slack channel name
(see the importers). So a document's domain can be assigned from *where it
came from*, never from *what it says*.

This module is the boundary. It does four jobs:

  1. **Domain map** — load a ``source unit -> domain`` map from YAML/JSON
     config. Jira project key, Confluence space key, Slack channel each map
     to a domain (e.g. ``eng`` / ``biz``). Unmapped units fall to
     ``unknown`` (see :data:`UNKNOWN`).
  2. **Ingest-time tagger** — :meth:`DomainMap.tag` takes a document's
     source metadata (source type + unit id) and returns its domain. This
     is meant to be stamped into the index payload at ingest.
  3. **Query-time filter builder** — :meth:`DomainMap.build_qdrant_filter`
     scopes retrieval to a requested domain set (default ``{"eng"}``) and
     *excludes ``unknown`` by default*. :meth:`DomainMap.make_predicate`
     is the server-free equivalent used to filter a result list in code or
     in tests.
  4. **Cross-domain detector** — :func:`detect_cross_domain` flags when the
     domains actually present in the returned results reach outside the
     requested set, so the answer layer can disclose "this came from a
     business-team doc — context, not authority."

The deterministic boundary is the point: the map is the hard boundary, set
by humans and reviewed weekly (the ``unknown`` bucket is the review queue).
A reranker may *propose within* the filtered set, but it never gets to set
the boundary itself. When the in-domain result set comes back empty and the
caller relaxes the filter, the cross-domain detector fires so provenance is
surfaced rather than silently trusted.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# The bucket every unmapped source unit falls into. Excluded from retrieval
# by default — an answer should never quote a doc whose domain nobody has
# vouched for.
UNKNOWN = "unknown"

# The default domain a query is scoped to when the caller doesn't say.
DEFAULT_REQUESTED_DOMAINS = frozenset({"eng"})

# Source types whose units carry domain provenance. These line up with the
# importers' ``source`` frontmatter field and the ``archive/<source>/``
# layout the indexer walks.
_KNOWN_SOURCES = ("jira", "confluence", "slack")


@dataclass(frozen=True)
class DomainMap:
    """A ``source unit -> domain`` map, loaded from config.

    The map is keyed per source type because unit namespaces don't overlap
    safely: a Jira project key ``FIN`` and a Slack channel ``fin`` are
    different things and may belong to different domains. Each inner map is
    ``{unit_id: domain}`` keyed by the *original* unit id (Jira/Confluence
    keys are upper-case, Slack channels lower-case) so the path prefixes the
    filter builds match the real ``archive/<source>/<unit>/`` layout on
    disk. Lookups are case-insensitive — ``INCD`` and ``incd`` resolve the
    same — via a normalized index built at construction.

    Unmapped units resolve to :data:`UNKNOWN`.
    """

    jira: Mapping[str, str] = field(default_factory=dict)
    confluence: Mapping[str, str] = field(default_factory=dict)
    slack: Mapping[str, str] = field(default_factory=dict)

    # ---------- construction ----------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> DomainMap:
        """Build a map from a parsed config dict.

        Expected shape::

            jira:        {INCD: eng, INFRA: eng, SALES: biz, FIN: biz}
            confluence:  {ENG: eng, OPS: eng, BIZ: biz}
            slack:       {incidents: eng, sales-ops: biz}

        Unknown top-level keys are ignored. Unit ids are lower-cased on
        load so lookups can be case-insensitive; domains are kept verbatim.
        """
        data = data or {}
        return cls(
            jira=_normalize_section(data.get("jira")),
            confluence=_normalize_section(data.get("confluence")),
            slack=_normalize_section(data.get("slack")),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> DomainMap:
        """Load a map from a YAML or JSON file (extension decides the parser)."""
        path = Path(path)
        raw = path.read_text(encoding="utf-8")
        data = (
            json.loads(raw)
            if path.suffix.lower() == ".json"
            else yaml.safe_load(raw)
        )
        if not isinstance(data, Mapping):
            raise ValueError(
                f"domain map at {path} must be a mapping at top level, "
                f"got {type(data).__name__}"
            )
        return cls.from_dict(data)

    # ---------- ingest-time tagging ----------

    def domain_for(self, source: str, unit: str | None) -> str:
        """Return the domain for a ``(source, unit)`` pair.

        ``source`` is the importer's source name (``jira`` / ``confluence``
        / ``slack``). ``unit`` is the Jira project key, Confluence space
        key, or Slack channel name. Anything not in the map — including an
        unknown source type or a missing unit — is :data:`UNKNOWN`.
        """
        if not unit:
            return UNKNOWN
        section = self._section(source)
        if section is None:
            return UNKNOWN
        # Case-insensitive lookup, original-cased keys preserved for prefixes.
        target = unit.strip().lower()
        for mapped_unit, domain in section.items():
            if mapped_unit.lower() == target:
                return domain
        return UNKNOWN

    def tag(self, frontmatter: Mapping[str, Any]) -> str:
        """Tag a document its domain from its source frontmatter.

        Reads the ``source`` field and the source-specific unit id the
        importers write (``extra.jira_*`` carries the project via the key;
        ``extra.confluence_space``; ``extra.slack_channel``). This is what
        an ingest pipeline calls to stamp ``domain`` into the payload.
        """
        source = str(frontmatter.get("source", "")).strip().lower()
        unit = _unit_from_frontmatter(source, frontmatter)
        return self.domain_for(source, unit)

    def domain_for_path(self, path: str) -> str:
        """Derive a domain from an ``archive/<source>/<unit>/...`` path.

        Useful when all you have back from retrieval is the payload
        ``path`` (the current indexer payload carries no domain field).
        Returns :data:`UNKNOWN` for paths outside the archive layout.
        """
        source, unit = _split_archive_path(path)
        if source is None:
            return UNKNOWN
        return self.domain_for(source, unit)

    # ---------- query-time filtering ----------

    def _prefixes_for_domains(self, domains: Iterable[str]) -> list[str]:
        """Path prefixes (``archive/<source>/<unit>/``) for the given domains."""
        wanted = {d for d in domains if d != UNKNOWN}
        prefixes: list[str] = []
        for source in _KNOWN_SOURCES:
            section = self._section(source) or {}
            for unit, domain in section.items():
                if domain in wanted:
                    prefixes.append(f"archive/{source}/{unit}/")
        return sorted(prefixes)

    def build_qdrant_filter(
        self, domains: Iterable[str] = DEFAULT_REQUESTED_DOMAINS
    ) -> dict[str, Any]:
        """Build a Qdrant filter scoping retrieval to ``domains``.

        Reuses the path-prefix idiom already in the MTTD similarity layer:
        a ``should`` of ``{"key": "path", "match": {"text": prefix}}``
        conditions, one per mapped unit in a requested domain. Because only
        mapped units appear, ``unknown`` is excluded structurally — there is
        no prefix for a unit nobody mapped.

        Pass this as the ``filter`` of a Qdrant ``points/search`` body. If no
        unit maps to the requested domains the scope is empty — and we make
        that filter **fail closed**, not open: Qdrant treats an empty
        ``should`` as "no constraint, match everything", which would invert
        the whole point of the feature. Instead we emit a ``must_not`` that
        excludes every document (a prefix match on ``archive/`` matches all
        imported content), so an empty scope matches nothing.
        """
        prefixes = self._prefixes_for_domains(domains)
        if not prefixes:
            # Fail closed: empty scope must match nothing, never everything.
            return {"must_not": [{"key": "path", "match": {"text": "archive/"}}]}
        conditions = [
            {"key": "path", "match": {"text": prefix}} for prefix in prefixes
        ]
        return {"should": conditions}

    def make_predicate(self, domains: Iterable[str] = DEFAULT_REQUESTED_DOMAINS):
        """Return a server-free predicate ``(path) -> bool`` for ``domains``.

        Mirrors :meth:`build_qdrant_filter` exactly: a path is retained iff
        its derived domain is in the requested set, which by construction
        excludes :data:`UNKNOWN`. This is the form used to filter an
        already-fetched result list — and the form the tests exercise so no
        live Qdrant is needed.
        """
        wanted = {d for d in domains if d != UNKNOWN}

        def _predicate(path: str) -> bool:
            return self.domain_for_path(path) in wanted

        return _predicate

    def filter_hits(
        self,
        hits: Iterable[Any],
        domains: Iterable[str] = DEFAULT_REQUESTED_DOMAINS,
        *,
        path_of=lambda h: getattr(h, "path", None) or h["path"],
    ) -> list[Any]:
        """Apply the domain predicate to a result list, retaining in-domain hits.

        ``path_of`` extracts the archive path from a hit; the default works
        for both attribute objects (``hit.path``) and Qdrant payload dicts
        (``hit["path"]``).
        """
        predicate = self.make_predicate(domains)
        return [h for h in hits if predicate(path_of(h))]

    # ---------- internals ----------

    def _section(self, source: str) -> Mapping[str, str] | None:
        return {
            "jira": self.jira,
            "confluence": self.confluence,
            "slack": self.slack,
        }.get((source or "").strip().lower())


# ---------- cross-domain detection ----------


@dataclass(frozen=True)
class CrossDomainReport:
    """Outcome of comparing requested domains to domains actually returned."""

    crossed: bool  # True if any returned domain is outside the requested set
    requested: frozenset[str]
    present: frozenset[str]  # domains actually present in the results
    outside: frozenset[str]  # present domains that are outside requested

    def disclosure(self) -> str:
        """A one-line provenance disclosure for the answer layer, or ``""``."""
        if not self.crossed:
            return ""
        labels = ", ".join(sorted(self.outside))
        return (
            f"Note: this draws on out-of-domain sources ({labels}) — "
            f"treat them as context, not authority."
        )


def detect_cross_domain(
    requested: Iterable[str],
    present: Iterable[str],
) -> CrossDomainReport:
    """Flag when retrieval reached outside the requested domain set.

    ``requested`` is the domain set the query asked for (default ``{"eng"}``).
    ``present`` is the set of domains actually represented in the returned
    results — derive it with :meth:`DomainMap.domain_for_path` over the hit
    paths.

    Fires (``crossed=True``) when any present domain is outside the requested
    set — including the case where the in-domain filter came back empty and
    the caller relaxed it, so only ``biz``/``unknown`` docs remain. Stays
    quiet on a clean in-domain result.
    """
    requested_set = frozenset(requested)
    present_set = frozenset(present)
    outside = present_set - requested_set
    return CrossDomainReport(
        crossed=bool(outside),
        requested=requested_set,
        present=present_set,
        outside=outside,
    )


# ---------- module-level helpers ----------


def _normalize_section(section: Any) -> dict[str, str]:
    """Strip + stringify keys and values; drop anything non-scalar.

    Original casing of unit ids is preserved so the path prefixes the filter
    builds match the real ``archive/<source>/<unit>/`` layout (Jira/Confluence
    keys are upper-case, Slack channels lower-case). Lookups are made
    case-insensitive at query time, not by mangling the stored key.
    """
    if not isinstance(section, Mapping):
        return {}
    out: dict[str, str] = {}
    for unit, domain in section.items():
        if unit is None or domain is None:
            continue
        out[str(unit).strip()] = str(domain).strip()
    return out


def _unit_from_frontmatter(source: str, fm: Mapping[str, Any]) -> str | None:
    """Pull the source unit id out of an importer's frontmatter.

    - jira: project key, derived from the issue key (``INCD-1102`` -> ``INCD``)
    - confluence: ``extra.confluence_space``
    - slack: ``extra.slack_channel``
    """
    extra = fm.get("extra") or {}
    if not isinstance(extra, Mapping):
        extra = {}
    if source == "jira":
        key = str(fm.get("source_id", "") or "")
        if "-" in key:
            return key.split("-", 1)[0]
        return key or None
    if source == "confluence":
        return extra.get("confluence_space") or None
    if source == "slack":
        return extra.get("slack_channel") or None
    return None


def _split_archive_path(path: str) -> tuple[str | None, str | None]:
    """Split ``archive/<source>/<unit>/...`` into ``(source, unit)``.

    Tolerates a leading prefix before ``archive/`` (absolute paths). Returns
    ``(None, None)`` if the path isn't under a recognized archive layout.
    """
    if not path:
        return None, None
    parts = Path(path).as_posix().split("/")
    try:
        i = parts.index("archive")
    except ValueError:
        return None, None
    rest = parts[i + 1 :]
    if len(rest) < 2:
        return None, None
    source, unit = rest[0], rest[1]
    if source not in _KNOWN_SOURCES:
        return None, None
    return source, unit


__all__ = [
    "DEFAULT_REQUESTED_DOMAINS",
    "UNKNOWN",
    "CrossDomainReport",
    "DomainMap",
    "detect_cross_domain",
]
