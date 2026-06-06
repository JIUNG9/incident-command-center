# Domain routing for a mixed-domain corpus

The brain ingests Slack, Jira, and Confluence. Those sources carry *both*
engineering and business-team content: incident tickets sit next to refund
SOPs, runbooks next to sales playbooks. Embeddings retrieve on topical
similarity alone, and topical similarity does not respect team boundaries.

## The mixed-corpus problem

Ask the brain about a `payment-service` 5xx incident and the embedding
search ranks every "payment" document highly — including the business
team's "payment refund policy" page. Same words, different domain. The
answer layer then quotes a refund SOP as if it were an incident runbook.
That is not a ranking bug to be tuned away; the two documents really are
topically close. The signal that separates them is not in the text.

It is in the provenance.

## Provenance-based domain tagging

Business content lives in *separate* Jira projects, Confluence spaces, and
Slack channels from engineering's. This is the clean case, and it is the
common one: org structure already partitions where content lands. The
importers preserve that partition — every imported document is written to
`archive/<source>/<unit>/...`, where `<unit>` is the Jira project key, the
Confluence space key, or the Slack channel name (see [`docs/IMPORT.md`](IMPORT.md)).

So a document's domain can be assigned from *where it came from*, never
from *what it says*. A document from Jira project `INCD` is engineering; a
document from Confluence space `BIZ` is business. The classification is
deterministic, auditable, and free of the false positives that plague
content-based classification.

The map lives in config — YAML or JSON — keyed per source type:

```yaml
jira:
  INCD: eng
  INFRA: eng
  SALES: biz
  FIN: biz
confluence:
  ENG: eng
  OPS: eng
  BIZ: biz
slack:
  incidents: eng
  sales-ops: biz
```

A shipped example is at [`examples/configs/domain-map.yaml`](../examples/configs/domain-map.yaml).
The keys there are generic — replace them with your own.

At ingest time, `DomainMap.tag(frontmatter)` reads the source and unit from
a document's frontmatter and returns its domain. Any source unit not in the
map resolves to `unknown` (see "The unknown bucket" below).

## Domain-scoped retrieval

Retrieval is scoped to a requested domain set — `{"eng"}` by default. The
filter builder turns that request into the same path-prefix idiom the MTTD
similarity layer already uses: a Qdrant `should` of
`{"key": "path", "match": {"text": "archive/<source>/<unit>/"}}` conditions,
one per mapped unit in a requested domain.

Two properties fall out of this construction:

- **`unknown` is excluded structurally.** There is no prefix for a unit
  nobody mapped, so an unmapped document can never be returned by the
  default filter. An answer never quotes a document whose domain nobody has
  vouched for.
- **The boundary is deterministic.** The set of in-domain prefixes is fully
  determined by the human-maintained map. No model, no threshold, no
  ranking decides what is in scope.

For callers that already hold a result list (or for tests), `make_predicate`
returns the server-free equivalent: a `(path) -> bool` that mirrors the
filter exactly.

The filter scopes the *imported* corpus — content under
`archive/<source>/<unit>/`. First-party content the team authors directly
(`docs/`, `knowledge/`, `CLAUDE.md`) has no source unit and is out of this
filter's scope; route it with its own policy rather than the domain map.
When the requested scope maps to no units at all, the filter fails closed —
it matches nothing rather than letting Qdrant's empty-`should` semantics
silently match everything.

## The reranker proposes within the filter

A reranker may reorder the candidates that survive the filter. It does not
get to set the filter. This is the same principle the rest of Vigil runs on
(see [`docs/llm-role-tiers.md`](llm-role-tiers.md)): **the model may
propose; it may never decide.** The deterministic boundary — which domains
are in scope — is not the model's to move. The reranker operates strictly
within the set provenance already admitted.

## Provenance surfacing on cross-domain reach

The filter and the cross-domain detector look contradictory at first: the
filter *excludes* out-of-domain documents, yet the detector *fires* when
out-of-domain documents appear in the results. They are not in conflict —
they cover two different paths.

The filter is the hard boundary on the normal path. When the in-domain
result set comes back **empty**, the caller may relax the filter to avoid
returning nothing — widen the requested set, or drop the scope for that one
query. That is a deliberate fallback, not a leak. When it happens,
`detect_cross_domain(requested, present)` compares the requested domains to
the domains actually present in the results and fires whenever retrieval
reached outside the requested set — including the case where only
`biz`/`unknown` documents remain.

When it fires, the report's `disclosure()` yields a one-line note for the
answer layer:

> Note: this draws on out-of-domain sources (biz) — treat them as context,
> not authority.

The out-of-domain document is surfaced *as context, not authority*. The
reader sees that the answer reached across a team boundary and can weigh it
accordingly. On a clean in-domain result the detector stays quiet and adds
no note.

## The unknown bucket — weekly mapping review

Every source unit not in the map falls into `unknown`, and `unknown` is
excluded from retrieval by default. That makes the `unknown` bucket the
review queue. A document that keeps landing in `unknown` is a new source
unit nobody has classified yet — a new Jira project, a freshly created
Confluence space, a new channel.

Walk the `unknown` bucket weekly. For each unmapped unit, decide its domain
and add it to the map. Until then it stays excluded, which is the safe
default: better to omit an unclassified source than to let it answer an
engineering question with unvetted provenance. The review is cheap because
the unit of decision is a *source*, not a document — one line in the map
covers every document that source will ever produce.

## Code

- Module: `src/vigil/domain_routing.py`
- Tests: `tests/test_domain_routing.py`
- Example config: `examples/configs/domain-map.yaml`
