# Report artifact

Default: native Markdown plus CSV. Optional: the existing standalone HTML report. Use the bundled generator; it validates v2 records, calculates weighted scores, sorts prospects, and exports all formats from the same included shortlist. The scripts require Python 3.9+ and no third-party packages. They do not search the web or verify a URL by themselves: Codex must inspect evidence before writing `verified`.

## Generate

Resolve scripts from the installed skill folder. Use a fresh run folder; the generator refuses to overwrite existing reports or use the same path for input/output/history.

```bash
python3 scripts/generate_report.py analysis.json outputs/first-customer-finder/example/run-01/report.md --csv outputs/first-customer-finder/example/run-01/prospects.csv --state outputs/first-customer-finder/example/state.json
```

Add `--html outputs/first-customer-finder/example/run-01/report.html` for the standalone visual version. Add `--new-only` when looking for additional, previously unseen prospects. For ephemeral research omit `--state` and keep analysis temporary. Keep research files out of version control and public packages.

Legacy invocation remains supported:

```bash
python3 scripts/generate_report.py analysis.json report.html
```

Legacy data without `schema_version: 2` gets an explicit validation warning. It cannot update history. New runs must use v2.

Return the Markdown report as a clickable absolute file link. If the current Codex environment provides a file-opening tool, open that report in the current task. Include CSV/HTML links only when useful; keep the chat handoff concise.

## V2 input example

This example is fictional. Never reuse its identities or evidence in real research. `demo: true` produces a prominent notice in Markdown, HTML, CSV (including an empty CSV), and segregated history. For real research use `demo: false` and actually inspect all sources.

```json
{
  "schema_version": 2,
  "demo": true,
  "project_key": "demo-membership-tool",
  "title": "First Customer Finder · Demo",
  "product": "Example membership tool",
  "product_url": "https://example.com/product",
  "target_customer": "Independent gym owners",
  "search_scope": "Fictional fixture; no live research",
  "generated_at": "2026-07-12",
  "verdict": "One invented candidate demonstrates the output format.",
  "prospects": [
    {
      "name": "Example Gym (fictional)",
      "entity_url": "https://example.com/gym",
      "type": "Company",
      "stage": "Problem aware",
      "pain_signal": "Fictional owner describes manual membership follow-ups.",
      "evidence": "Invented demo evidence, not a real public statement.",
      "evidence_status": "verified",
      "why_fit": "The demo product addresses the described workflow.",
      "why_now": "The fictional scenario concerns a recent request.",
      "source_title": "Fictional membership workflow discussion",
      "source_url": "https://example.com/discussion",
      "source_type": "Fictional public forum",
      "signal_date": "2026-07-10",
      "checked_at": "2026-07-12",
      "target_role": "Owner responsible for membership billing",
      "role_basis": "inferred",
      "suggested_channel": "Relevant public discussion, if its rules permit",
      "contact_route": {
        "status": "verified",
        "label": "Fictional discussion reply",
        "url": "https://example.com/discussion",
        "source_url": "https://example.com/discussion",
        "checked_at": "2026-07-12",
        "note": "Demo-only route, not a real contact channel."
      },
      "next_step": "Offer a short workflow walkthrough after confirming interest.",
      "cta": "Should I send a two-minute walkthrough?",
      "opener": "You mentioned manual membership follow-ups. We are testing a reminder workflow for small gyms. Should I send a two-minute walkthrough?",
      "caution": "Fictional example. In a real run verify that the problem is still unresolved.",
      "dimensions": {
        "pain_strength": 5,
        "product_fit": 5,
        "timing": 4,
        "reachability": 4,
        "evidence_quality": 4
      }
    }
  ],
  "patterns": [],
  "outreach_plan": {
    "angle": "Validate the workflow before pitching.",
    "first_step": "Review the strongest signal and confirm a suitable route.",
    "follow_up": "Offer a walkthrough only after interest is expressed.",
    "success": "A useful conversation is a validation target, not a promised outcome."
  },
  "limits": ["All identities, statements, and routes in this fixture are fictional."]
}
```

## Field rules

- `project_key` is stable and product-specific. A different key cannot write into an existing product's history.
- `entity_url` establishes the stable `p_...` ID; do not supply a fabricated identity or use a shared platform root. Duplicate identities are rejected rather than silently overwriting evidence. The renderer also adds P1/P2 ranks; they are local to each report.
- `score` is derived from all five numeric dimensions (0–5); any supplied total is replaced. Below-50 candidates must be kept outside the qualified input.
- `stage` is `High intent`, `Problem aware`, or `Trigger present`. Incomplete “Potential fit” records belong in limits, not `prospects`.
- `evidence_status` must be `verified` for primary records, meaning Codex inspected the source. This is not verification of purchase intent. Report blocked sources in `limits` instead.
- `signal_date` is `YYYY-MM-DD` or null. `checked_at` is the real date inspected; a recent check does not refresh an old signal. Unknown signal dates require timing <= 2/5. Dates cannot be in the future relative to the report/check date.
- `role_basis` is `observed` or `inferred`. Do not turn an inferred function into a supposedly verified named person.
- `contact_route.status` is `verified` or `not_found`. A verified route needs its URL, label, supporting public URL, check date, and suitability note. A missing route needs an honest note, no URL, and reachability <= 1/5; retain a concrete manual next step such as finding the official support route. A visible form is not consent or proof of suitability.
- `next_step`, `cta`, `opener`, and `caution` are required. Include the exact `cta` in `opener`. A draft can be prepared for a missing route but must not imply it is ready to send there.
- Optional `additional_sources`: array of `{ "url": "https://...", "note": "What this supports" }`. Include corroboration/counter-evidence when it materially affects qualification.
- Optional `patterns`: `{title, count, insight}` records. Counts refer only to included prospects. If history filtering removes inputs, the generator drops stale pattern counts and resets the plan/verdict to the remaining shortlist; revise the actual analysis if richer conclusions are needed.
- Reports label missing routes, previously seen entities, history exclusions, and uncertainty. CSV escapes formula-leading values; its `status`/`feedback` columns are snapshots. Editing CSV does not sync changes back: tell Codex the outcome so it can update local history explicitly.
- The helper validates data structure, not the truth of web statements, legal permission to contact, or semantic quality of drafts. Manually inspect the generated report before handing it off.
