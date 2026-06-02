# Vigil — DevOps Platform (v6.x roadmap)

> **Status**: roadmap document · drafted 2026-06-02 · referenced by the spec on the internal twin (paro)

Vigil started as an SRE chat assistant (Q&A over your runbooks, war-room state machine, MTTD/MTTR measurement). The v6.x line extends that into a full DevOps Console — eleven sidebar tabs that consolidate the surfaces a small DevSecOps team has otherwise scattered across SigNoz, Datadog, Grafana, Confluence, Jira, and Slack.

The pattern is borrowed from [Aegis](https://github.com/JIUNG9/aegis) — an OSS multi-account devops-dashboard project that already implements the sidebar nav, account filter, SLO components, FinOps components, incident timeline, and DORA metric cards. Vigil mirrors that pattern and adds the four things Aegis does not: chat (Q&A), war-room (multi-party incident response), MTTD (mode-split detect-time), and adaptive feedback loops (SigNoz baseline learning, postmortem auto-drafting).

---

## Sidebar — full surface

The DevOps Console adds an 11-tab left sidebar to the existing Chat / Timeline / Watchlist / MTTD / MTTR surfaces. Tabs in display order:

| # | Tab | What it does | Backed by |
|---|---|---|---|
| 1 | **Log Explorer** | SigNoz APM logs scoped by service / severity / time. Always queries ERROR and WARN together to avoid the auto-alert-filter blind spot. | SigNoz ClickHouse `signoz_logs.distributed_logs_v2` |
| 2 | **SLO Dashboard** | Per-service error-budget burn + service-health grid + time-window toggle (7d / 30d / 90d). | `paro_war.slo_targets`, `slo_measurements`; SigNoz APM derived |
| 3 | **FinOps** | Cost-overview, cost-by-service, kubernetes-cost, rightsizing recommendations, budget management, daily anomaly cards. | AWS Cost Explorer + Kubecost |
| 4 | **Incidents** | Multi-account incident list, alert-feed (SSE), incident-stats, incident-detail, Slack-thread import, AI suggestions. | `paro_war.incidents` + `incident_events` + `alert_feed` |
| 5 | **Security** | Three-tier posture cards (critical / warn / ok) — secrets archaeology, dependency vulns, CI/CD pipeline security, OWASP Top 10 + STRIDE progress. | `paro_war.security_findings`, `/cso` skill |
| 6 | **IAM Audit** | Per-account IAM inventory + last-accessed timestamps + removal candidate queue with dev → prod sequence lock. | IAM API + CloudTrail 90d lookback |
| 7 | **Deployments + DORA** | Recent rollouts + DORA 4 KPI cards (Deployment Frequency / Lead Time / MTTR / Change Failure Rate) + Lead Time tab + deploy↔incident correlation. | ArgoCD events + git log + `paro_war.dora_metrics` |
| 8 | **On-Call** | Rotation table per account + escalation matrix + AI assignee recommendation + member-manager (vacations / shift swaps). | `paro_war.oncall_*` |
| 9 | **Services** | Service catalog (account / tier / owner / deploy method) + multi-account health grid + SLI summary + recent incidents per service. | `paro_war.services` |
| 10 | **Account Mgmt** | AWS account inventory cards (id / name / alias / CIDR / region) + cross-account assume-role map + VPC topology overview. | `paro_war.aws_accounts` |
| 11 | **Settings** | Per-user preferences (theme / lang / default account / default chat mode), alert routing rules, confidence/rerank thresholds, data retention. | `paro_war.user_preferences`, `system_config` |

Above the sidebar tabs sit the four already-shipped Vigil surfaces:

- **Chat** (`/chat`) — RAG Q&A with per-source confidence and citations
- **War-room** (`/war/[id]/chat`) — 3-column multi-party incident chat with 7-panel auto-preload
- **MTTD** (`/mttd`) — 30-day rule-vs-similarity detect time chart per mode (auto / peer / customer)
- **MTTR** (`/mttr`) — 30-day P0-P3 boxplots

And a **Current Dashboard** that opens by default — pod / PVC / ALB state + cost lines + idle/restart toggle + recent ArgoCD syncs + banner alerts.

---

## Multi-account model

Every page is account-scoped. The header carries a sticky chip row (`All / nexus / shared / nowwaiting / dodopoint` in the internal deployment; users define their own account labels in `aws_accounts`). The chip selection flows as a `?account=` query parameter into every page's data fetch.

The corresponding schema migration on `paro_war.incidents` adds:

```sql
ALTER TABLE paro_war.incidents ADD COLUMN account_id varchar(16);
CREATE INDEX idx_incidents_account_window ON paro_war.incidents(account_id, declared_at DESC);
```

Webhook ingest receivers (`/hooks/{github,jira,confluence,signoz}`) need a small enrichment to extract the originating account — for SigNoz this is `service.namespace` (e.g. `prod-now` → `nowwaiting`), for GitHub `repository.owner.login`, for Atlassian `org_id`.

---

## DORA + SPACE

DORA lives inside the **Deployments** tab, not as a separate sidebar item — that matches the Aegis pattern. The four KPIs:

1. **Deployment Frequency** — ArgoCD `synced` events per day per account
2. **Lead Time for Changes** — git commit → ArgoCD synced time (median)
3. **Mean Time to Restore** — reuses the MTTR page's calculation
4. **Change Failure Rate** — ArgoCD `Degraded` rolled back within 24h / total deploys

A **DORA tier classifier** combines these into Elite / High / Medium / Low.

**SPACE** (Microsoft Research extension) is on the v6.2 roadmap:
- **Satisfaction** — Slack `/paro` feedback thumb up/down rate
- **Performance** — already covered by DORA + SLO
- **Activity** — per-engineer `/paro` usage + response acceptance
- **Communication** — war-room thread participation rate
- **Efficiency** — postmortem publish rate (drafts → published)

---

## Adaptive layers (the part Aegis doesn't have)

Where Aegis is a dashboard, Vigil's value-add is the **adaptive feedback loops** — two pages that turn measurement into improvement.

### Adaptive MTTD — SigNoz threshold learner

The `paro-apm-suggester` daily CronJob analyzes the last 28 days of SigNoz metrics per service, computes P50/P95/P99 baselines, and posts proposed `watchlist/*.yaml` rule changes to `#oncall-pager` with Approve / Skip / Edit buttons. Approve → automatic brain-repo PR → SigNoz alert rule sync. The "action-first / ratify-after" mode is opt-in per rule — Vigil adjusts the threshold first, then auto-reverts in 24h if false-positive rate spikes.

### Adaptive MTTR — analysis workbench

When an incident is declared, Vigil auto-preloads 7 panels into the war-room: similar past incidents (vector search), root-cause candidates, runbooks, action checklist, participants (CODEOWNERS + git-blame + on-call), live dashboards, summary. Twenty-four hours after resolution, the postmortem auto-drafter writes a timeline + 5-whys draft into Confluence as DRAFT. The continuous-learning loop closes when the published postmortem gets embedded back into the corpus — the next similar incident's preload includes the lesson.

---

## What this costs

Self-hosted, single-vm baseline:

| Component | Cost |
|---|---|
| SigNoz (self-hosted) | $0 |
| Postgres (managed or in-cluster) | varies |
| Qdrant (in-cluster on EBS) | ~$3/mo for 20GiB gp3 |
| Ollama (CPU-only, no GPU) | $0 incremental |
| 2 ALBs (chat-web + webhook-ingest) | ~$34/mo |
| Total for a small team | **~$50-100/mo** depending on EKS node footprint |

Vigil OSS targets the same "fifteen-to-fifty dollars a month" sweet spot Aegis was designed for. The internal Vigil deployment at Placen (`paro`) currently runs at ~$200/mo when fully live, ~$11/mo when idled with PVCs retained.

---

## Compatibility with Aegis

The two projects are siblings, not competitors. The components that overlap (account-filter, slo, finops, incidents, oncall, deployments) come from Aegis and are MIT-licensed for direct lift. The chat / war-room / MTTD / MTTR / adaptive layers are Vigil-original. If you're choosing between the two:

- Want a clean OSS multi-account devops dashboard with mock data and a designer-quality UI? Use **Aegis**.
- Want chat + war-room + brain-RAG + the dashboard layer on top? Use **Vigil** — and lift Aegis components where you want them.

---

## Implementation status (June 2026)

| Layer | Status |
|---|---|
| Chat (`/chat`) | ✅ shipped in v6.0 |
| War-room (`/war/[id]/chat`) | ✅ shipped in v3.0 |
| MTTD page | ✅ shipped (single-tenant) |
| MTTR page | ✅ shipped (single-tenant) |
| `account_id` schema migration | ⏳ planned |
| 11 sidebar tabs | ⏳ specs written, implementation planned per `ROADMAP.md` |
| Adaptive MTTD (SigNoz suggester) | ✅ CronJob shipped; Slack-approval flow live |
| Adaptive MTTR (postmortem drafter) | ✅ shipped in v4.0 |
| DORA tier classifier | ⏳ planned for v6.2 |
| SPACE metrics | 🔮 v6.3+ |

The internal twin (paro at Placen) has the full functional spec written up in 18 Korean Confluence pages — those are not public, but the structure mirrors this document one-to-one.

---

## See also

- [Series 7 articles](./series-7/) — the build history
- [Vigil README](../README.md) — install + quickstart
- [Aegis on GitHub](https://github.com/JIUNG9/aegis) — the design pattern source
