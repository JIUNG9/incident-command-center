"""Tests for domain routing over a mixed-domain corpus.

Pure functions only — no live Qdrant, no Ollama. The collision case is
exercised by applying the query-time predicate to mock hits, mirroring what
the filter would do server-side.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from vigil.domain_routing import (
    UNKNOWN,
    DomainMap,
    detect_cross_domain,
)


@dataclass(frozen=True)
class FakeHit:
    """Stand-in for a retrieval hit — just enough surface for the predicate."""

    path: str
    text: str


@pytest.fixture
def dmap() -> DomainMap:
    return DomainMap.from_dict(
        {
            "jira": {"INCD": "eng", "INFRA": "eng", "SALES": "biz", "FIN": "biz"},
            "confluence": {"ENG": "eng", "OPS": "eng", "BIZ": "biz"},
            "slack": {"incidents": "eng", "sales-ops": "biz"},
        }
    )


# ---------- ingest-time tagging ----------


def test_known_unit_resolves_to_domain(dmap: DomainMap) -> None:
    assert dmap.domain_for("jira", "INCD") == "eng"
    assert dmap.domain_for("jira", "FIN") == "biz"
    assert dmap.domain_for("confluence", "OPS") == "eng"
    assert dmap.domain_for("slack", "sales-ops") == "biz"


def test_unit_lookup_is_case_insensitive(dmap: DomainMap) -> None:
    assert dmap.domain_for("jira", "incd") == "eng"
    assert dmap.domain_for("JIRA", "Fin") == "biz"


def test_unmapped_unit_is_unknown(dmap: DomainMap) -> None:
    assert dmap.domain_for("jira", "MKTG") == UNKNOWN
    assert dmap.domain_for("confluence", "LEGAL") == UNKNOWN
    assert dmap.domain_for("slack", "random") == UNKNOWN


def test_unknown_source_and_missing_unit_are_unknown(dmap: DomainMap) -> None:
    assert dmap.domain_for("email", "INCD") == UNKNOWN
    assert dmap.domain_for("jira", None) == UNKNOWN
    assert dmap.domain_for("jira", "") == UNKNOWN


def test_tag_from_frontmatter(dmap: DomainMap) -> None:
    # Jira issue: domain derived from the project key in source_id.
    jira_fm = {"source": "jira", "source_id": "INCD-1102", "extra": {}}
    assert dmap.tag(jira_fm) == "eng"

    biz_jira_fm = {"source": "jira", "source_id": "FIN-204", "extra": {}}
    assert dmap.tag(biz_jira_fm) == "biz"

    # Confluence: extra.confluence_space carries the unit.
    conf_fm = {"source": "confluence", "extra": {"confluence_space": "BIZ"}}
    assert dmap.tag(conf_fm) == "biz"

    # Slack: extra.slack_channel carries the unit.
    slack_fm = {"source": "slack", "extra": {"slack_channel": "incidents"}}
    assert dmap.tag(slack_fm) == "eng"

    # Unmapped source unit -> unknown.
    orphan_fm = {"source": "jira", "source_id": "MKTG-9", "extra": {}}
    assert dmap.tag(orphan_fm) == UNKNOWN


def test_domain_for_path(dmap: DomainMap) -> None:
    assert dmap.domain_for_path("archive/jira/INCD/INCD-1102.md") == "eng"
    assert dmap.domain_for_path("archive/jira/FIN/FIN-204.md") == "biz"
    assert dmap.domain_for_path("archive/confluence/BIZ/123-refunds.md") == "biz"
    # absolute path with a prefix before archive/ still resolves
    assert dmap.domain_for_path("/home/u/brain/archive/jira/INFRA/x.md") == "eng"
    # outside the archive layout, or unmapped unit -> unknown
    assert dmap.domain_for_path("docs/runbooks/foo.md") == UNKNOWN
    assert dmap.domain_for_path("archive/jira/MKTG/MKTG-1.md") == UNKNOWN


# ---------- query-time filter builder ----------


def test_filter_excludes_unknown_and_scopes_to_requested(dmap: DomainMap) -> None:
    f = dmap.build_qdrant_filter({"eng"})
    prefixes = {c["match"]["text"] for c in f["should"]}

    # every eng unit's prefix is present
    assert "archive/jira/INCD/" in prefixes
    assert "archive/jira/INFRA/" in prefixes
    assert "archive/confluence/OPS/" in prefixes
    assert "archive/slack/incidents/" in prefixes

    # no biz unit and nothing for unknown
    assert "archive/jira/FIN/" not in prefixes
    assert "archive/jira/SALES/" not in prefixes
    assert all("FIN" not in p and "SALES" not in p and "BIZ" not in p for p in prefixes)


def test_filter_condition_shape_matches_qdrant_idiom(dmap: DomainMap) -> None:
    f = dmap.build_qdrant_filter({"biz"})
    assert set(f.keys()) == {"should"}
    for cond in f["should"]:
        assert cond["key"] == "path"
        assert "text" in cond["match"]
        assert cond["match"]["text"].startswith("archive/")


def test_empty_scope_fails_closed(dmap: DomainMap) -> None:
    # A domain with no mapped units must match nothing, never everything.
    f = dmap.build_qdrant_filter({"nonexistent-domain"})
    assert "should" not in f
    assert f["must_not"] == [{"key": "path", "match": {"text": "archive/"}}]


def test_predicate_mirrors_filter(dmap: DomainMap) -> None:
    pred = dmap.make_predicate({"eng"})
    assert pred("archive/jira/INCD/INCD-1102.md") is True
    assert pred("archive/jira/FIN/FIN-204.md") is False
    assert pred("archive/jira/MKTG/MKTG-1.md") is False  # unknown excluded
    assert pred("docs/runbooks/foo.md") is False  # unknown excluded


# ---------- the collision case ----------


def test_collision_eng_retained_biz_dropped(dmap: DomainMap) -> None:
    """An incident query retains the eng doc and drops the topically-similar
    biz doc.

    Both docs are about "payment", so an embedding search ranks them both
    highly. Provenance — not topic — is what separates them.
    """
    eng_doc = FakeHit(
        path="archive/jira/INCD/INCD-1102.md",
        text="payment-service returning 5xx after deploy; rolled back",
    )
    biz_doc = FakeHit(
        path="archive/confluence/BIZ/501-refund-policy.md",
        text="payment refund policy: refunds processed within 5 business days",
    )

    retained = dmap.filter_hits([eng_doc, biz_doc], {"eng"})

    assert eng_doc in retained
    assert biz_doc not in retained
    assert [h.path for h in retained] == ["archive/jira/INCD/INCD-1102.md"]


# ---------- cross-domain detector ----------


def _domains_of(dmap: DomainMap, hits: list[FakeHit]) -> set[str]:
    return {dmap.domain_for_path(h.path) for h in hits}


def test_cross_domain_quiet_on_clean_eng_result(dmap: DomainMap) -> None:
    hits = [
        FakeHit("archive/jira/INCD/INCD-1102.md", "5xx"),
        FakeHit("archive/jira/INFRA/INFRA-2391.md", "rds cpu"),
    ]
    report = detect_cross_domain({"eng"}, _domains_of(dmap, hits))
    assert report.crossed is False
    assert report.outside == frozenset()
    assert report.disclosure() == ""


def test_cross_domain_fires_when_only_biz_unknown_remain(dmap: DomainMap) -> None:
    """The relaxed-filter fallback: in-domain set was empty, so only
    biz/unknown docs came back. The detector fires and produces a
    provenance disclosure.
    """
    hits = [
        FakeHit("archive/confluence/BIZ/501-refund-policy.md", "refund policy"),
        FakeHit("archive/jira/MKTG/MKTG-9.md", "campaign"),  # unknown
    ]
    report = detect_cross_domain({"eng"}, _domains_of(dmap, hits))
    assert report.crossed is True
    assert report.outside == frozenset({"biz", UNKNOWN})
    assert "context, not authority" in report.disclosure()


def test_cross_domain_fires_on_partial_reach(dmap: DomainMap) -> None:
    # eng plus one biz doc — still a reach outside the requested set.
    hits = [
        FakeHit("archive/jira/INCD/INCD-1102.md", "5xx"),
        FakeHit("archive/jira/FIN/FIN-204.md", "invoice"),
    ]
    report = detect_cross_domain({"eng"}, _domains_of(dmap, hits))
    assert report.crossed is True
    assert report.outside == frozenset({"biz"})


# ---------- config loading ----------


def test_from_file_yaml(tmp_path) -> None:
    p = tmp_path / "domain-map.yaml"
    p.write_text(
        "jira:\n  INCD: eng\n  FIN: biz\nslack:\n  incidents: eng\n",
        encoding="utf-8",
    )
    dmap = DomainMap.from_file(p)
    assert dmap.domain_for("jira", "INCD") == "eng"
    assert dmap.domain_for("jira", "FIN") == "biz"
    assert dmap.domain_for("slack", "incidents") == "eng"


def test_from_file_json(tmp_path) -> None:
    p = tmp_path / "domain-map.json"
    p.write_text('{"jira": {"INFRA": "eng", "SALES": "biz"}}', encoding="utf-8")
    dmap = DomainMap.from_file(p)
    assert dmap.domain_for("jira", "INFRA") == "eng"
    assert dmap.domain_for("jira", "SALES") == "biz"
    assert dmap.domain_for("jira", "INCD") == UNKNOWN


def test_shipped_example_map_loads() -> None:
    """The example config ships and parses, and its generic keys resolve."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    example = repo_root / "examples" / "configs" / "domain-map.yaml"
    dmap = DomainMap.from_file(example)
    assert dmap.domain_for("jira", "INCD") == "eng"
    assert dmap.domain_for("jira", "FIN") == "biz"
    assert dmap.domain_for("jira", "NOPE") == UNKNOWN
