---
name: unreal-media-brand-prospector
description: Find, deeply research, qualify, filter, deduplicate, and report evidence-backed brand prospects for Unreal Media Group using local campaign and prospect-history JSON. Use for open or focused brand discovery, including product-photography or product-video opportunities that exclude UGC advertising, when Codex must preserve public-source evidence and stop before creative generation or outreach.
---

# Unreal Media Brand Prospector

Produce a local, reviewable Unreal Media Group prospecting run. Treat every prospect as a research hypothesis based on public business evidence, never a confirmed buyer.

## Read first

Read these files before research:

- `references/unreal-media-positioning.md`
- `references/ideal-customer-profile.md`
- `references/discovery-framework.md`
- `references/qualification-framework.md`
- `references/deduplication-rules.md`
- `references/evidence-rules.md`
- `references/compliance-rules.md`
- `references/campaign-config.md`

Read `references/report-artifact.md` before assembling or rendering the final run report.

Resolve the shared core at installed sibling `../unreal-prospecting-core/` or repository path `shared/prospecting-core/`. Shared scripts are at installed sibling `../unreal-prospecting-core/scripts/` or repository path `shared/prospecting-core/scripts/`. Use the installed `examples/` directory or repository `fixtures/prospecting/` only as synthetic examples, never as real prospect data.

## Phase 6 boundary

This skill performs public-source research and local file generation only. It does not:

- connect to Unreal OS, Supabase, a CRM, OpenClaw, or an external database,
- schedule itself or create a recurring loop,
- find private emails or phone numbers,
- generate ads, product imagery, UGC, or video,
- draft or send outreach,
- submit forms, follow accounts, comment, or post.

Stop before every external write or creative-generation action.

## Workflow

### 1. Validate the campaign

Run the shared `validate_campaign.py` against the supplied campaign JSON.

Confirm:

- `business_unit` is `unreal-media-group`,
- the campaign name and prospect limits are explicit,
- `discovery_scope: open` may use `verticals: []`,
- `discovery_scope: filtered` has one or more verticals,
- geography, signals, includes, exclusions, cooldown, evidence age, and output formats are understood,
- the local prospect-history path resolves.

When `opportunity_filter` is present, confirm it is UMG-only, uses the controlled values `product_photography`, `product_video`, and `ugc_ad`, includes at least one desired kind, and does not include and exclude the same kind. The filter expresses search intent; it is never evidence that a company has demand, budget, or buying intent.

Do not invent a vertical when the campaign requests open discovery.

### 2. Load history before discovery

Load and validate durable local prospect history before searching.

History is the authority for:

- canonical company identity,
- domains and alternate domains,
- aliases and public social handles,
- parent, subsidiary, subbrand, and agency relationships,
- prior discovery and campaign appearances,
- prior scores and decisions,
- active outreach,
- client and partner status,
- suppression,
- cooldown,
- prior signals and rejection reasons.

If history is missing, invalid, or internally ambiguous, stop. Never describe a candidate as new when history was not successfully loaded.

### 3. Build a multi-bucket discovery plan

Use several query angles rather than generic lists of brands.

Search for:

1. **Product and launch signals:** new products, collections, restocks, packaging, SKUs, crowdfunding, retail expansion, seasonal drops.
2. **Marketing activity:** paid social, creator programs, ambassador programs, launch countdowns, frequent short-form content, visible campaign testing.
3. **Creative need:** repetitive assets, sparse lifestyle content, limited formats, large catalogs with little product variation, strong products presented inconsistently. Describe gaps neutrally.
4. **Growth and timing:** funding, hiring, new leadership, distribution, expansion, partnerships, site relaunches, new markets.
5. **Explicit demand:** public requests for video, paid-social creative, product photography, production capacity, or help with a content bottleneck. Treat UGC demand as an exclusion when the campaign excludes `ugc_ad`.

Use multiple source types. Prefer official websites, product pages, press pages, public brand profiles, public job posts, ad libraries, crowdfunding pages, retail announcements, and interviews. Search-result snippets may locate a source but are not final evidence.

When an `opportunity_filter` is configured, use its included kinds to shape discovery queries from the start and treat excluded kinds as negative routing criteria. Still preserve raw candidates and run history classification before making the final include/exclude decision. Query wording and search snippets never count as opportunity evidence.

### 4. Preserve raw candidates

For each candidate, record at least:

- company name,
- original domain or URL,
- company type,
- discovery source URLs,
- current signal and visible date,
- why the brand may fit UMG,
- uncertainty that still requires review.

Do not deep-research a candidate before identity normalization and duplicate classification.

### 5. Normalize and classify identity

Use shared deterministic scripts to normalize domains, company names, and public handles, then classify the candidate against history.

Allowed outcomes include:

- `new_prospect`
- `existing_no_new_trigger`
- `existing_new_trigger`
- `existing_active_outreach`
- `existing_client`
- `existing_partner`
- `suppressed`
- `possible_duplicate_needs_review`
- `distinct_subbrand`
- `parent_company_relationship`
- `agency_brand_overlap`

A prior company is never new. Suppression, active-client, active-partner, and active-outreach protections override subbrand or relationship treatment. Ambiguous identity requires human resolution.

Re-engagement requires:

- campaign re-engagement enabled,
- a materially new dated public trigger,
- a recorded reason,
- evidence inside the campaign freshness limit,
- expired cooldown,
- a source not already stored in history.

Do not use or create test-only cooldown overrides in a real run.

### 6. Apply the opportunity filter

Apply this only after history classification. For every candidate in a campaign with `opportunity_filter`, record `opportunity_matches` with:

- one controlled opportunity kind,
- an observed or explicitly confidence-labeled basis,
- one or more URLs already preserved as signal evidence,
- a concise reason grounded in that evidence.

A qualified result must match at least one `include_any` kind and no `exclude` kind. If the evidence supports an excluded UGC-ad opportunity, preserve the finding and reject the candidate for this campaign. A product launch or visual brand alone does not prove demand; label a defensible opportunity as inference unless the source states it directly.

### 7. Apply the UMG qualification model

Score each dimension from 0 to 5 using `references/qualification-framework.md`:

- creative need,
- product and visual fit,
- budget likelihood,
- marketing activity,
- timing,
- reachability,
- evidence quality.

Use the shared score calculator. Do not hand-edit the total.

Budget, buying authority, and expected performance remain inferences unless a cited source explicitly supports them. Label each claim as observed or inferred.

Primary stages:

- `high_intent`: public request for relevant creative or production help,
- `active_trigger`: launch, expansion, campaign, hiring, or other current reason to act,
- `creative_gap`: strong product and marketing activity with a defensible creative opportunity,
- `strong_icp_fit`: strong fit without urgency,
- `watchlist`: plausible but insufficient evidence,
- `disqualified`, `duplicate`, or `reengagement` as applicable.

Use the configured minimum score. Do not weaken the threshold to reach the requested count.

### 8. Deep-research the eligible shortlist

For each eligible shortlisted company, research all material public business facts that affect qualification, not only a contact route. Cover the company and brand, products and services, audience and positioning, current launches and campaigns, visual and content patterns, owned channels, material news and growth signals, public business leadership roles, public business contact routes, risks, and contradictions. Preserve each material fact as a dated, linked signal with an observation or inference label. Record missing or unverifiable areas in uncertainty or limitations; never fill gaps by guessing.

Do not collect personal emails, personal phone numbers, private profiles, sensitive traits, or paid-enrichment data. A public business role or general company contact route is research context, not permission to contact anyone.

### 9. Apply evidence and eligibility gates

A non-rejected qualified result requires:

- a canonical domain,
- an official company source,
- at least one fresh dated signal,
- preserved source URLs,
- a UMG-specific use case,
- a valid score breakdown,
- an explicit uncertainty,
- a recommended human next action.

Only `new_prospect`, eligible `distinct_subbrand`, and `existing_new_trigger` records may enter the qualified shortlist. Suppressed, duplicate, relationship-only, active-client, active-partner, and active-outreach records must be rejected for prospecting and cannot be marked ready for a creative handoff.

### 10. Assemble and validate the run report

Preserve one result decision for every raw candidate, including duplicates and rejections.

The report must include:

1. campaign scope,
2. search assumptions,
3. raw candidate count,
4. new unique prospects,
5. duplicates and relationship matches,
6. re-engagement prospects,
7. rejections and reasons,
8. qualified shortlist,
9. score breakdowns,
10. evidence links and dates,
11. evidence-linked opportunity matches when a filter is active,
12. observed-versus-inferred labels,
13. uncertainties and next actions,
14. limitations and validation errors,
15. future creative-handoff readiness.

Run the shared result validator before rendering. Every signal URL must be preserved in the discovery event. Rejected or ineligible records must have `future_handoff.ready: false`.

### 11. Render locally

Run:

```text
scripts/generate_report.py <run-report.json> <report.md|report.html>
```

The wrapper delegates to the shared renderer. Keep the validated JSON audit record alongside the human-readable report.

## Fail closed

Stop and report the exact blocker when:

- history cannot be loaded,
- identity maps to conflicting historical records,
- configuration is contradictory,
- evidence is stale or unverifiable,
- an official source is missing for a qualified record,
- score or summary totals do not validate,
- an ineligible record is marked qualified or handoff-ready,
- the requested count cannot be reached without lowering quality,
- the task crosses the Phase 6 finder/researcher boundary.

Return fewer strong prospects rather than filling the report with generic brands.
