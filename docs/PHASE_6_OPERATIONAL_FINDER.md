# Phase 6 Operational Finder

## Outcome

Phase 6 is the completed Unreal Media Group finder/researcher skill. It extends the original Phase 1 contracts instead of replacing them with a second runtime:

```text
campaign + durable local history
              |
              v
public-business discovery
              |
              v
identity normalization + history classification
              |
              v
optional evidence-backed opportunity filter
              |
              v
qualification + broad public-business research
              |
              v
validated JSON -> Markdown / HTML -> human review
```

The visible release is called Phase 6. Existing run JSON retains `run_metadata.phase: 1` as a compatibility version for the frozen report contract; that value does not enable or refer to the retired Phase 6 runtime.

## Opportunity filter

UMG campaigns may use:

```json
{
  "opportunity_filter": {
    "include_any": ["product_photography", "product_video"],
    "exclude": ["ugc_ad"]
  }
}
```

The controlled vocabulary is exactly:

- `product_photography`
- `product_video`
- `ugc_ad`

The campaign filter is search intent, not proof of demand. Each qualified result must carry one or more `opportunity_matches` with a controlled kind, an observed or confidence-labeled basis, a reason, and evidence URLs already present in its signal list. At least one included kind must match; any excluded kind makes the result ineligible for that campaign. Excluded and rejected decisions remain in the audit report.

History loads before filtering, so an already discovered, suppressed, client, partner, active-outreach, or ambiguous company cannot bypass protections merely because it matches the requested opportunity.

## Research coverage

For each eligible shortlist result, the skill examines all material public business facts that affect qualification:

- company and brand identity,
- products, services, audience, and positioning,
- current launches, campaigns, and visual/content patterns,
- owned channels and material public activity,
- growth, operational, partnership, and hiring signals,
- public business leadership roles and company contact routes,
- contradictions, uncertainty, source dates, and evidence gaps.

The report preserves those facts as linked, dated signals and labels observations separately from inferences. It records unknowns instead of guessing. It does not collect private emails, private phone numbers, sensitive traits, paid-enrichment data, or authenticated-source data.

## Ready-to-run example

The installer includes:

- `examples/campaigns/umg-product-visuals-no-ugc.json`
- `examples/history/starter-prospect-history.json`

Their relative paths work when the `campaigns/` and `history/` folders are copied together. Keep real history and reports outside the repository. Complete installation and invocation commands are in [UNREAL_README.md](../UNREAL_README.md).

## Local validation and rendering

From a repository checkout:

```bash
python3 shared/prospecting-core/scripts/validate_campaign.py fixtures/prospecting/campaigns/umg-product-visuals-no-ugc.json
python3 shared/prospecting-core/scripts/validate_results.py fixtures/prospecting/expected/umg-sample-run.json
python3 shared/prospecting-core/scripts/render_report.py fixtures/prospecting/expected/umg-sample-run.json /tmp/umg-phase6-report.html
```

No third-party runtime dependency, database, daemon, deployment platform, or API credential is required. The complete development suite additionally uses `PyYAML` only because Codex's official skill validator imports it; setup is documented in [UNREAL_README.md](../UNREAL_README.md).

## Explicit non-goals

Phase 6 does not contain or authorize:

- the retired dossier, live-proof, source-plan, claim-projector, approval, or graph-package systems,
- an autonomous crawler or recurring live-research scheduler,
- private-person enrichment,
- creative, image, video, likeness, or advertisement generation,
- outreach drafting or sending,
- CRM, Unreal OS, downstream-agent, or other external writes.

Its output is a local, validated research report for a human or a separately governed downstream system to consume later.
