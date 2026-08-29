---
name: first-customer-finder
description: Find and qualify evidence-backed potential first customers, early adopters, design partners, or beta users for a startup using recent public pain and buying signals. Use when Codex needs to analyze a product URL or idea, define an ideal customer profile, research public discussions and business pages, identify first-user prospects, rank lead fit and timing, prepare source-based outreach drafts, or create a shareable early-customer prospecting report without sending messages automatically.
---

# First Customer Finder

Turn a startup URL or product description into a short, evidence-backed list of plausible first customers. Use public signals, preserve privacy, and distinguish a prospect from a confirmed buyer.

Read [references/research-framework.md](references/research-framework.md) before researching or scoring prospects. Read [references/report-artifact.md](references/report-artifact.md) before creating the final report.

## Workflow

### 1. Understand the product

- Inspect the supplied URL, repository, landing-page copy, or product description.
- Identify the product, outcome, buyer, user, price or buying motion, geography, and strongest use case.
- Define one primary ICP, one adjacent ICP, pain triggers, positive signals, and disqualifiers.
- Infer missing context when safe and label the inference. Ask one concise question only when ambiguity would materially change the search.

### 2. Build a public-signal search plan

Search current public sources for:

- explicit tool or alternative requests
- first-person descriptions of the target problem
- manual workflows and repeated workaround complaints
- migration, churn, or competitor-frustration signals
- public company changes that create timing, such as hiring, launching, expanding, or adopting a relevant workflow

Use multiple query angles and source types. Prefer original pages over search snippets. Record the source URL, source type, publication date when visible, and the exact evidence supporting qualification.

### 3. Research safely

- Use public, intentionally shared professional or business information only.
- Do not bypass login walls, paywalls, access controls, rate limits, or robots restrictions.
- Do not use data brokers, leaked datasets, private groups, personal email discovery, phone enrichment, or sensitive personal information.
- Do not infer protected traits or target people using health, financial hardship, political belief, sexuality, religion, or other sensitive attributes.
- Prefer companies, public professional profiles, public requests, and community posts relevant to the product.
- Quote minimally and paraphrase by default. Link every material pain or timing signal.

### 4. Qualify and deduplicate

Score each prospect using the bundled framework:

- pain strength
- product fit
- timing
- public reachability
- evidence quality

Remove duplicates and weak matches. A prospect without a cited pain, need, or timing signal is only a speculative fit and must not appear in the primary shortlist.

Never claim that a prospect is interested, has consented, or will buy. Label the output “potential customer based on public signals.”

### 5. Draft outreach, never send it

- Recommend concrete official/public contact routes when available, and say when no direct public route is found.
- Translate the product into the prospect's buyer/problem language.
- Keep outreach manual and source-grounded.
- Make each opener include a specific, low-friction CTA that can be accepted, rejected, or forwarded.
- Avoid private enrichment. Do not perform any outreach actions (e.g., sending messages, submitting forms, connecting, following, commenting, or creating CRM records).
- Avoid pretending to know the person, overstating familiarity, or mentioning unrelated personal details.

### 6. Produce the report

Lead with the most actionable evidence. Use this order:

1. **Verdict** — whether the startup has reachable early-customer signals.
2. **ICP** — buyer, job, trigger, and disqualifiers.
3. **Top prospect** — strongest evidence-backed candidate and why now.
4. **Prospect shortlist** — source, pain signal, fit score, stage, why now, channel, and opener.
5. **Repeated patterns** — pains and triggers appearing across prospects.
6. **Seven-day outreach plan** — a manual, low-volume validation sequence.
7. **Limits** — missing evidence and what must be confirmed through real conversations.

Create a standalone HTML report unless the user explicitly requests chat-only output:

1. Write structured JSON using `references/report-artifact.md`.
2. Run `scripts/generate_report.py <analysis.json> <report.html>`.
3. Save the report in the workspace `outputs/` directory.
4. Verify prospect cards, source links, scores, patterns, outreach plan, and limitations.
5. Return a clickable absolute file link in the final response so it opens from Codex.

## Modes

- **quick**: Find and qualify up to five strong prospects.
- **standard**: Find up to ten prospects across several public source types.
- **deep**: Research up to twenty prospects and map repeated pain patterns.
- **design-partners**: Prioritize users willing to test and give feedback over immediate buyers.
- **b2b**: Prioritize companies, public business triggers, and relevant decision roles.
- **community**: Prioritize public discussion and explicit request signals.

Use `standard` by default.

## Quality bar

- Link every prospect to at least one meaningful public signal.
- Prefer ten strong matches over a long generic lead list.
- Make uncertainty and stale evidence visible.
- Personalize from the source, not from invented assumptions.
- Keep outreach manual and respectful.
- Treat the shortlist as a research hypothesis, not a customer database.
