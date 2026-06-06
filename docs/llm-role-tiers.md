# The LLM trust ladder

Vigil treats the LLM as a component with a trust ladder, not a brain. This
doc says which job runs on which engine and what gate each one needs. The
guiding rule is one line: **the model may propose; it may never decide.**
Everything the model touches is either deterministic or human-ratified.

The same rule governs retrieval scope: [`docs/domain-routing.md`](domain-routing.md)
keeps a mixed engineering/business corpus clean by deciding domain from
provenance, not from the model — a reranker proposes within the filter, but
the deterministic boundary is not the model's to set.

## The trust ladder

| Job | Engine | Trust level | Gate |
|---|---|---|---|
| Embeddings | Self-hosted (local) | Trusted | None — deterministic. Same input maps to the same vector. |
| Postmortem drafting | LLM | Trusted with gate | Human ratify. Drafts are pushed as `DRAFT` and never auto-published. |
| Similarity recommendation | Embeddings + retrieval | Trusted | Surfaced, not decided. A ranked list is shown; a human picks. |
| Anomaly prediction | LLM clusterer | NOT trusted | Disabled by flag `MTTD_PATTERN_LAYER_ENABLED=false`. |
| Autonomous remediation | LLM-proposed action | NOT trusted | Requires SLO budget + human approval; action-first/ratify-after with revert. |

Read the table top to bottom as "how much can this job do on its own,"
from "everything, it's deterministic" down to "nothing without a human in
the loop." The two trusted-without-caveat rows (embeddings, similarity)
are trusted precisely because they don't generate — they measure and
retrieve. The moment a job *generates* a claim or *takes* an action, a
gate appears.

### Embeddings — trusted, no gate

Turning a symptom string into a vector for similarity search is
deterministic-feeling: the same input produces the same vector, and the
output is a number, not a sentence a human has to second-guess. There is
nothing to ratify. This is the one job the self-hosted model does with no
gate at all, and it's the job it's best suited for.

### Postmortem drafting — trusted, but gated

The model is good at turning a messy incident timeline into a readable
first draft. It is not trusted to publish that draft. Every generated
postmortem lands as `DRAFT`. A human reads it, corrects the inevitable
errors, and ratifies before it becomes part of the corpus. The model
saves the blank-page time; it does not get the final say.

### Similarity recommendation — surfaced, not decided

"This incident looks like these three past incidents" is a retrieval
result, not a verdict. Vigil surfaces the ranked matches with their
sources and lets the on-call engineer decide which, if any, applies. The
ranking is trusted because it's grounded in embeddings over real past
incidents; the *conclusion* is the human's.

### Anomaly prediction — not trusted, disabled

An LLM clusterer that tries to predict "this metric pattern means an
incident is coming" stays behind a disabled flag
(`MTTD_PATTERN_LAYER_ENABLED=false`). See *Why prediction stays off*
below.

### Autonomous remediation — not trusted, hard-gated

The model may propose a remediation. It may never run one on its own.
Any action requires an SLO error budget to spend and explicit human
approval before it touches anything with blast radius. Where an action
does run, it follows action-first/ratify-after with a guaranteed revert
path — never fire-and-forget.

## Why chat is not the center

A chatbot is a destination. Mid-incident, nobody wants a new destination —
they want the answer where they already are. Asking an engineer to open a
browser tab and type into a chat box during a page is asking them to
context-switch at the worst possible moment.

So Vigil does not put a chat UI in the critical path. It ships a
local-sync agent instead: the team brain is cloned to the engineer's
laptop as plain markdown files, and the engineer's existing local
tooling reads it directly. No service to be up, no tab to open, no
round-trip to a website. The collective views (severity dashboards, SLO
burn, on-call) live in the web dashboard; individual reasoning happens in
the tools the engineer already has open.

## Why prediction stays off

LLM-based incident *prediction* has a bad industry track record: roughly
a 60–80% false-positive rate in practice. The failure mode is social, not
technical. By the third bad page at 3 AM, on-call stops trusting the
predictor — and a prediction system nobody trusts is worse than no system,
because it adds noise and erodes confidence in every other signal. The
feature dies on the floor regardless of how good the model gets.

Vigil substitutes *measurement* and *similarity* for *prediction*:

- **Per-service baseline measurement** — what does normal look like for
  *this* service, learned from its own history, not guessed.
- **Similarity** — "this looks like incident X from March," grounded in
  embeddings over real past incidents.

Both are things the on-call engineer can verify in seconds. Neither
claims to see the future. The prediction layer remains in the codebase
behind `MTTD_PATTERN_LAYER_ENABLED=false` for anyone who wants to
experiment, but it ships off and stays off.

## Roadmap — the reasoning tier

The two jobs Vigil currently trusts the LLM with — embeddings and
drafting — are *forgiving*. A slightly-off embedding still retrieves
useful neighbors; a draft is going to be human-edited anyway. Neither
needs a strong model, which is exactly why a small self-hosted model on a
single modest node is the right fit for them.

Judgment-heavy jobs are a different class. Weighing a remediation,
reasoning about blast radius, or reconciling contradictory sources needs
a stronger reasoning engine than a self-hosted model on one small node
can provide.

**Status: evaluating a managed model (e.g. AWS Bedrock) for the reasoning
tier, behind the same gates.** The gates do not relax for a bigger model:
action-first/ratify-after, human approval on any blast-radius action,
nothing reaches prod without an SLO budget to spend.

This is honest work-in-progress. There are no results yet, no benchmark
to report, and no commitment to a specific provider. The self-hosted
model stays exactly where it is — owning embeddings — regardless of what
the reasoning tier evaluation concludes.
