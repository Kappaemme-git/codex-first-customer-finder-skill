---
name: unreal-talent-campaign-prospector
description: Find, research, qualify, deduplicate, relationship-map, and report evidence-backed brand or agency campaign buyers for Unreal Talent using local Phase 1 campaign and history JSON. Use for open, vertical, brand, agency, combined, talent-category, trigger-focused, or re-engagement discovery when Codex must apply rights, roster, conflict, brand-safety, and named-talent constraints and stop before likeness use, creative generation, or outreach.
---

# Unreal Talent Campaign Prospector

Produce a local, reviewable Unreal Talent campaign-buyer run. This is a rights-managed qualification workflow, not a celebrity endorsement generator or an influencer list builder.

## Read first

Read every file under `references/` before research. They separate:

- Unreal Talent positioning,
- brand and agency ICPs,
- campaign triggers,
- scoring,
- company and campaign relationships,
- roster and rights constraints,
- brand safety,
- campaign configuration,
- report requirements.

Resolve the shared core at installed sibling `../unreal-prospecting-core/` or repository path `shared/prospecting-core/`. Shared scripts are at installed sibling `../unreal-prospecting-core/scripts/` or repository path `shared/prospecting-core/scripts/`.

## Phase boundary

This skill performs public-source research and local file generation only. It does not:

- connect to Unreal OS, Supabase, a CRM, OpenClaw, or an external database,
- create a recurring loop or runner,
- enrich private contact data,
- promise talent availability,
- create a real person's likeness or campaign concept,
- draft or send outreach,
- submit forms or perform external actions.

No named person, likeness, creative, or message may be produced outside the controlled rules below.

## Workflow

### 1. Validate the campaign

Run the shared campaign validator.

Confirm:

- `business_unit` is `unreal-talent`,
- buyer types include brand, agency, or both,
- likely rights territory is explicit,
- open discovery may omit verticals,
- filtered discovery includes verticals,
- talent categories are optional unless named-talent review is explicitly authorized,
- prospect limits, evidence age, cooldown, and output formats are understood,
- local history resolves.

When named-talent review is enabled, also require:

- controlled local roster data,
- explicit verticals,
- explicit talent categories,
- explicit campaign channels.

### 2. Load durable history and relationships

Load and validate local history before discovery.

History must expose:

- brand, agency, and parent identities,
- domains, aliases, and public handles,
- subsidiaries and subbrands,
- agency and brand relationships,
- existing clients, partners, and active opportunities,
- suppression and cooldown,
- prior campaign signals and decisions.

If history is missing or identity is ambiguous, stop. Do not describe an opportunity as new.

### 3. Apply roster mode

#### No approved roster

Use only:

- `none`, or
- `archetype_only`.

Do not name a real athlete, creator, musician, actor, celebrity, chef, DJ, or other talent. Do not imply availability. Mark rights review required.

#### Approved controlled roster

A named recommendation is still only an internal hypothesis. It requires:

- explicit campaign authorization,
- one exact approved roster match,
- approved status,
- reviewable availability,
- matching talent category,
- compatible brand category,
- no restricted-category conflict,
- territory coverage,
- campaign-channel coverage,
- no unresolved exclusivity conflict,
- fresh roster data,
- continued internal rights review.

Roster match is not availability, availability is not campaign approval, and campaign approval is not final asset approval.

### 4. Build a multi-bucket discovery plan

Search current public evidence for:

1. **Partnership and sponsorship:** athlete, creator, team, league, event, ambassador, music, entertainment, or licensing announcements.
2. **Product and market:** major launches, national distribution, expansion, new geography, new category, rebrand, new customer segment.
3. **Agency:** account wins, pitches, production partnerships, hiring, AI-production initiatives, public partner requests.
4. **Campaign volume:** multi-channel campaigns, localization, continuous social variants, expensive reshoots, limited assets from an existing approved relationship.
5. **Explicit demand:** public requests for talent, partnerships, campaign production, AI production, sports marketing, or entertainment marketing.

Prefer official brand and agency sites, press releases, sponsorship pages, campaign announcements, public job listings, trade publications, ad libraries, event announcements, and public professional profiles. Search snippets only locate original evidence.

### 5. Preserve and map the opportunity

Record:

- brand or agency,
- canonical domain,
- parent company,
- known agency relationships,
- current campaign trigger,
- likely buyer path,
- rights territory,
- proposed talent category or archetype,
- source URLs and dates,
- material rights, conflict, or brand-safety uncertainty.

Do not create separate unrelated leads for the brand, parent, agency, and campaign when they describe one commercial opportunity.

### 6. Normalize and classify identity

Use shared deterministic normalization and duplicate classification before deep research.

A prior company is never new. Preserve:

- new opportunities,
- existing records without a new trigger,
- valid re-engagement,
- active outreach,
- clients and partners,
- suppression,
- ambiguous duplicates,
- subbrand and parent relationships,
- agency-brand overlap.

Account protections override subbrand treatment. Ineligible relationships cannot become a qualified shortlist entry or creative handoff.

### 7. Apply the Unreal Talent qualification model

Score each dimension from 0 to 5:

- campaign and talent fit,
- budget likelihood,
- current trigger,
- rights and organizational readiness,
- brand and roster compatibility,
- decision-path reachability,
- evidence quality.

Use the shared score calculator and configured minimum score. Do not edit totals manually.

Primary stages:

- `high_intent`,
- `active_campaign_trigger`,
- `talent_extension_opportunity`,
- `strong_strategic_fit`,
- `agency_channel_opportunity`,
- `watchlist`,
- `rights_review_required`,
- `disqualified`, `duplicate`, or `reengagement`.

Budget, authority, rights readiness, and talent fit are inferences unless a cited source or controlled roster record supports them.

### 8. Perform preliminary rights and brand-safety screening

Flag or reject material issues involving:

- alcohol, nicotine, gambling, weapons, adult content,
- politics or issue advocacy,
- medical, health, financial, or performance claims,
- supplements and youth audiences,
- controversy or litigation,
- competitor endorsements,
- category or geographic exclusivity,
- morals clauses,
- union or guild requirements,
- synthetic-likeness restrictions,
- platform restrictions.

This is not legal approval. Unresolved material risk must route to human review or rejection.

### 9. Apply evidence and eligibility gates

A non-rejected qualified opportunity requires:

- canonical identity,
- official brand or agency evidence,
- a fresh campaign or trigger signal,
- a defensible talent-powered use case,
- score breakdown,
- buyer-path recommendation,
- rights territory,
- rights and brand-safety uncertainty,
- a human next action.

Only `new_prospect`, eligible `distinct_subbrand`, and `existing_new_trigger` may enter the qualified shortlist. Suppressed, duplicate, relationship-only, active-client, active-partner, and active-outreach results must be rejected for prospecting and have `future_handoff.ready: false`.

### 10. Assemble and validate the report

Preserve one decision for every raw candidate.

Include:

1. campaign scope and buyer types,
2. rights territory and talent mode,
3. search assumptions,
4. raw/new/duplicate/re-engagement/rejection counts,
5. qualified shortlist,
6. brand versus agency buyer path,
7. score breakdown,
8. campaign trigger and evidence,
9. talent archetype or controlled roster status,
10. rights and brand-safety flags,
11. uncertainty and next action,
12. limitations and validation errors,
13. future handoff readiness.

Run the shared validator before rendering. Every signal URL must be present in the discovery event. Unauthorized named talent, insufficient roster rights, unresolved exclusivity, stale roster data, or ineligible handoff state must fail validation.

### 11. Render locally

Run:

```text
scripts/generate_report.py <run-report.json> <report.md|report.html>
```

Keep the validated JSON audit record. State clearly that no likeness, creative, outreach, or external record was produced.

## Fail closed

Stop and report the blocker when:

- history cannot be loaded,
- company or relationship identity is ambiguous,
- the target count requires weak opportunities,
- a source cannot be verified,
- a campaign trigger is stale,
- rights territory is absent,
- roster authorization or compatibility is incomplete,
- exclusivity or brand-safety risk is unresolved,
- a result attempts unauthorized named talent,
- an ineligible record is marked qualified or handoff-ready,
- the task crosses Phase 1.
