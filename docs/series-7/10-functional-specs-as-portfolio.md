# Functional specs as a portfolio artifact

I spent a Tuesday afternoon writing eighteen functional specification documents on Confluence. Not for a deliverable. Not for a sprint. For a thing I haven't built yet — an extension of an internal SRE tool that I've been considering opening up into a full DevOps platform. I wrote them anyway. Here's why, and why I think more engineers should do this.

The tool is called `acme-deploy` internally and `Vigil` in its open-source form. Both names refer to the same engine: a self-hosted chat assistant over a team's runbooks, past incidents, Slack threads, and Jira tickets, plus a war-room state machine and the metrics that the team's reliability engineering cares about (MTTD, MTTR). I shipped v6 in late May and idled it the same week — the cost of running it exceeded the value at the time, but the value would come back the moment I had two specific blockers cleared. The story of that idle-then-restart cycle is in [part 8](08-rename-and-cutover.md) and [part 9](09-build-to-be-turned-off.md) of this series.

This is what came next: I knew the chat surface alone wasn't going to justify the ongoing cost. The tool needed to be a platform. Eleven more tabs, multi-account scoping, DORA metrics, FinOps integration, an IAM audit view. I'd been borrowing the pattern from a project called Aegis — another open-source DevSecOps dashboard I'd looked at for inspiration. It already had nine of the eleven tabs I wanted, in good condition, with the components named well and a sensible information architecture. I could lift them.

But before lifting code, I wrote specs.

---

## The case against specs

Engineers — especially solo engineers building internal tools — usually skip functional specifications. The arguments are reasonable.

The first is that specs go stale. You write a careful page describing what a feature does, then you build it, then the build informs your understanding of what the feature should actually do, and the doc no longer matches reality. Most spec documents I've seen at companies are six to eighteen months out of date.

The second is that specs over-design. You write what a feature should do, and the writing process pushes you toward completeness — every edge case, every acceptance criterion, every constraint. When you build it, you find that 60% of the spec is theater. You'd have shipped a simpler thing without it.

The third is that solo engineers don't need them. There's no audience. You aren't briefing a team. You're not coordinating with a designer. The spec is a thing you'd write and then never re-read.

I sympathize with all three arguments. I've been on the wrong side of all three. And I still wrote the eighteen specs.

---

## What changed for me

Three things, all related.

The first is that I noticed I was making the same architectural decision over and over, in slightly different forms, every time I sat down with the tool. *Should account scoping be a query parameter or a path segment? Should DORA be its own tab or fold into Deployments? Should incident state machine be optimistic-locked or last-write-wins?* Each time I revisited the project after a few weeks away, I'd re-derive answers, sometimes the same as last time, sometimes not. The waste was real. A spec is a single place where the decision lives — and the decision is the part that survives even when the implementation changes.

The second is that the spec is the part of the work that's portable to other people. The code is mine; I wrote it on a laptop in my home. The spec is a public artifact (well — internal-public; it lives on Confluence for the team to read). If I get hit by a bus, the spec is what enables someone else to pick up. If I want to hand off a piece of this to a teammate, the spec is the briefing. If I'm interviewed about this work — for a promotion, for a relocation, for an external role — the spec is what I show as proof that I think rigorously about the work, not just code furiously.

The third, and this is the one that surprised me: writing the spec changes what I build. Not because the spec is "what to build" — I know roughly what to build before I write it. It changes what I build because the act of writing the twelve sections (overview, scope, glossary, stakeholders, scenarios, functional requirements, data model, API/UI, non-functional, constraints, acceptance criteria, changelog) surfaces the assumptions I'd otherwise carry around in my head untested. The "constraints" section in particular is where you find out the design has a quiet problem. The "acceptance criteria" section is where you find out you don't know how you'd judge success.

---

## What the specs look like

I used the same twelve-section structure for every page. Korean for the internal versions because the team reads Korean; English for the OSS-facing equivalents because that audience reads English. Both versions cover the same ground.

The twelve sections are deliberate. They're not the longest spec template I've used — that honor goes to a multi-page IEEE-style template I encountered at a previous job that had seventeen sections plus a glossary plus a traceability matrix. They're also not the shortest — some teams ship one-paragraph "What is it and why" descriptions and call it done.

The twelve I land on are the ones that survived the question "if I skip this section, will the design change?" Sections that didn't survive: cost analysis (covered implicitly in non-functional), traceability matrix (over-engineered for solo work), historical context (belongs in the article, not the spec), user research summary (no users to interview yet). Sections that did survive include the ones a reader might think are overhead: glossary (because terms drift across teams), changelog (because diff-readability matters more than spec-readability after a year), constraints (because it forces honesty about what isn't true yet).

For each tab in the DevOps Console I wrote one page. For each cross-cutting concern (account filter, command bar, theme system) I either folded into a parent page or wrote a shorter spec. Eighteen pages total. Twelve sections each. Median length maybe 600 words.

---

## What I learned from the act of writing

A few things, mostly small.

**The "scope" section is where you find features you didn't actually want.** Writing "Includes / Excludes" forces a clean cut. I caught two tabs I'd been planning to build that, when I wrote out what they'd include vs. exclude, I realized were just confused FinOps. Folded them.

**The "glossary" section catches name collisions.** I'd been using `severity` and `p_class` interchangeably. When I wrote the glossary, I had to pick one. The spec said: `severity` for raw alert severity (ERROR / WARN / INFO), `p_class` for declared-incident classification (P0 / P1 / P2 / P3). Now the code is going to be more consistent because the spec forced the question.

**The "data model" section catches schema gaps.** Every page that promised "per-account split" forced me to write "account_id column missing from `paro_war.incidents`." Now there's a single migration ticket instead of eight different "this needs a column" comments scattered across the docs.

**The "constraints" section catches the parts you'd rather not admit.** The chat-api currently runs at one replica because the bm25-index PVC pins it to an over-loaded AZ. That's not a feature; it's a capacity constraint. The spec says so. Future-me will be glad it's documented; otherwise I'd waste a day six months from now wondering why I made that choice.

**The "acceptance criteria" section is the hardest.** I wrote criteria for every page. Some were easy ("Recall@5 ≥ 0.65 on golden test set"). Most were harder ("incident assignment recommendation accept rate ≥ 60%"). A few I had to leave fuzzy ("SLO compliance trend should be 'on track' or 'better' across the quarter") because I genuinely don't know how to measure them yet. The fuzzy ones are usually a sign that the feature is half-baked. Better to know that before I write code.

---

## How this fits the portfolio

I'm a one-person DevSecOps team at a small company in Korea, planning to relocate to Canada by 2027. The portfolio I bring to that move is partly code (Vigil on GitHub, with its installable PyPI package and its 482 passing tests), partly writing (this article series on Medium, the LinkedIn posts that go with it), and partly artifacts that prove the work — diffs, deploy logs, cost graphs, incident postmortems.

Specs belong in the artifacts bucket. They're the part of engineering work that's most directly comparable across companies and roles, because every team writes some form of them. An interviewer who's reviewed dozens of resumes from SRE candidates is going to scan an impact log faster than they'll scan a code sample. The impact log says "I shipped this and it cost $1k/month less than the thing it replaced." The specs say "I think about engineering work in twelve dimensions, here are the dimensions, here's my reasoning."

I think the under-appreciated career move for solo engineers is to write specs for the things you'd build, even when there's no team requiring it. Not gold-plated specs — short ones, the same twelve sections every time, two hours per page. The compound interest comes from:

- You build better, because the writing exposes weak assumptions.
- You hand off easier, because the docs are there when someone else needs to pick up.
- You interview better, because you have a stack of concrete artifacts to point at.
- You stay sharper, because the act of writing — even short writing — keeps the design space active in your head when you're between sprints.

---

## The other angle: this is what good documentation feels like

Most engineering documentation is bad. The reason it's bad isn't laziness or lack of skill; it's that documentation is usually written *after* the work, by the same person who just spent a week debugging the thing. By that point, the writer has lost the ability to model someone who doesn't know what they know.

Spec-first inverts this. The writer doesn't know what the system will be like, because the system doesn't exist. They have to imagine the reader's perspective from cold. The constraints section is honest about what isn't true yet because everything isn't true yet. The glossary doesn't assume the reader knows the team's slang because the team's slang hasn't crystallized yet.

The specs I wrote on Tuesday will go stale eventually. I'll update some sections, archive others, kill a few entirely. That's fine. The spec was useful at the moment I wrote it — it changed what I'd build next, it gave me a single place to put the architectural decisions, and it produced a portable artifact. The fact that the spec will eventually be wrong doesn't undo the value at the moment it was right.

---

## Try this

If you're a solo engineer with an internal tool you've been meaning to extend, try this:

1. Pick the next feature you'd add. One feature, not the whole roadmap.
2. Write twelve sections for it: overview, scope, glossary, stakeholders, scenarios, functional requirements, data model, API/UI, non-functional, constraints, acceptance criteria, changelog. Aim for 600 words.
3. Time-box: two hours.
4. Post it somewhere — internal wiki, Notion, even a markdown file in the repo. Doesn't matter where, as long as it has a URL.

Then build the feature.

I'd be surprised if the spec doesn't change what you build, at least a little. I'd be more surprised if the spec doesn't end up referenced six months later when you'd otherwise have re-derived the same decisions.

The portfolio benefit is a side effect. The primary win is that you build better.

---

*Part 10 of the Building Vigil series. The functional specs that prompted this article are at Confluence id 357367903 (internal); the OSS equivalent lives at [`docs/devops-platform.md`](../../../../teammate-oss/docs/devops-platform.md). The companion roadmap for the Next.js implementation is at [`acme-deploy-chat-web/ROADMAP.md`](../../acme-deploy-chat-web/ROADMAP.md).*
