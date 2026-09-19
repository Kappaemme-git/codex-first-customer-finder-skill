---
name: first-customer-finder
description: Find evidence-backed potential first customers, beta users, or design partners from public demand signals. Use for product-specific prospect research, qualified shortlists, source-grounded outreach drafts, and follow-up searches refined by the user's feedback and local prospect history. Does not send outreach automatically.
---

# First Customer Finder

Turn a startup URL or product description into a short, evidence-backed list of plausible first customers. Use public signals, preserve privacy, and distinguish a prospect from a confirmed buyer.

Read [references/research-framework.md](references/research-framework.md) before researching or scoring prospects and [references/report-artifact.md](references/report-artifact.md) before creating the final report. For saved history, feedback, or a repeat search, also read [references/feedback-and-history.md](references/feedback-and-history.md).

Use English by default; follow an explicit language request. Keep the chat handoff short and put the useful detail in the report. Research requires available web search/browser tools; the bundled Python helpers only validate, export, and manage local files. If live browsing is unavailable, report that limitation instead of inventing leads.

## Workflow

### 1. Understand the product

- Inspect the supplied URL, repository, landing-page copy, or product description.
- Identify the product, outcome, buyer, user, price or buying motion, geography, and strongest use case.
- Define one primary ICP, one adjacent ICP, pain triggers, positive signals, and disqualifiers.
- Infer missing context when safe and label the inference. Ask one concise question only when ambiguity would materially change the search.
- Use one stable product-specific workspace folder. If its history exists, inspect the saved preferences and excluded prospects before searching. Never load another product's history just because it is nearby. State briefly where history will be saved; respect requests for no saved history.

### 2. Build a public-signal search plan

Search current public sources for:

- explicit tool or alternative requests
- first-person descriptions of the target problem
- manual workflows and repeated workaround complaints
- migration, churn, or competitor-frustration signals
- public company changes that create timing, such as hiring, launching, expanding, or adopting a relevant workflow

Use multiple query angles and source types, including accessible public X discussions, GitHub issues, forums, reviews, and company pages when relevant. Search engines are discovery aids, not evidence. Open original pages, record publication date separately from the date checked, and attribute the signal to its actual author/company. If a source is blocked or only a snippet is available, keep it outside the qualified shortlist and explain coverage gaps. Do not imply every platform was searched.

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

Remove duplicates and weak matches. Use a verified company homepage or public professional profile as `entity_url`, not a name alone or the shared platform homepage. One entity may have several signals. A prospect without a cited pain, need, or timing signal is only a speculative fit and must not appear in the primary shortlist.

Check whether the problem was already resolved, the author is selling rather than buying, the product lacks a required capability, or the buyer is outside the requested profile. Put material counter-evidence in the caution or exclude the candidate. A high numerical score cannot override contradictory evidence. Never fill a requested quota with weak matches.

Never claim that a prospect is interested, has consented, or will buy. Label the output “potential customer based on public signals.”

### 5. Draft outreach, never send it

- Identify the target role/function and label it observed or inferred. Do not invent a named decision-maker.
- Verify a concrete official/public contact route: relevant public thread, published business contact page, or public professional profile. Record its URL and why it is suitable. A visible route is not permission to promote there; inspect relevant community rules. If no appropriate route is found, say so and give a manual research next step, not a guessed address.
- Write one short opener in the buyer's problem language with a specific, low-friction CTA that can be accepted, declined, or forwarded. Offer a realistic next step such as a workflow review, checklist, or demo. Do not claim an asset, integration, customer result, or capability already exists unless verified.
- Avoid pretending to know the person, overstating familiarity, or mentioning unrelated personal details.
- Do not send messages, submit forms, connect, follow, comment, or create CRM records unless the user separately requests and authorizes that action.

### 6. Produce the report and save the next search's context

Lead with the most actionable evidence. Use this order:

1. **Verdict** — whether the startup has reachable early-customer signals.
2. **ICP** — buyer, job, trigger, and disqualifiers.
3. **Top prospect** — strongest evidence-backed candidate and why now.
4. **Prospect shortlist** — stable ID, source/date, score, why now, target role, verified contact route (or missing route), concrete next step, CTA, opener, and caution.
5. **Repeated patterns** — pains and triggers appearing across prospects.
6. **Seven-day outreach plan** — a manual, low-volume validation sequence.
7. **Limits** — missing evidence and what must be confirmed through real conversations.

Create a native Markdown report and CSV by default. Preserve the standalone HTML option; generate it when requested. Respect explicit chat-only or format preferences:

1. Write structured JSON using `references/report-artifact.md`.
2. Run the bundled generator with explicit output paths and, unless declined, the product's local state path. It computes scores, validates v2 data, exports Markdown/CSV/optional HTML, and saves a compact history. Use a fresh run folder so previous reports remain intact.
3. Verify the report, citations, actual number of included prospects, contact routes, and drafts. CSV export does not send anything or synchronize a CRM.
4. Return an absolute Markdown file link; when the Codex file-opening tool is available, open the report in the current task. Do not require that tool on other installations.
5. Invite short feedback using the displayed IDs, for example: “P1 and P3 are a fit; avoid enterprise buyers.” Do not delay the first report waiting for feedback.

### 7. Refine when the user responds

Save explicit keep/maybe/reject feedback with its reason. Translate an explicit general preference into updated search criteria and state what changed before a new search. A rejection of one company is not a rule against its entire industry; ask briefly if that distinction matters. “Learning” means a visible local preference update, not model training.

On a request for more/new prospects, use `--new-only`, retain the product scope, and exclude previously seen entities plus contacted/rejected records. Revalidate saved sources when the user requests a refresh instead. Only mark someone contacted, replied, or a customer when the user supplies that outcome. Never treat generating a draft as contacting someone. Do not start a scheduled monitor from an ordinary follow-up search.

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
- Keep local histories and research outputs out of the skill repository and npm package. Demo fixtures must be clearly labeled fictional in every output format.
