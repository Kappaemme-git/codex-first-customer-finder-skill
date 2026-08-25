# UMG report artifact

Validate the full run report before rendering. Include scope, assumptions, raw count, new unique, duplicates, re-engagement, rejections, shortlist, score breakdowns, evidence links, observed/inferred labels, next actions, rejection reasons, limitations, validation errors, and future creative-handoff readiness. When an opportunity filter is active, every qualified result must include controlled `opportunity_matches` whose evidence URLs are already present in the result signals.

Generate Markdown or HTML through `scripts/generate_report.py`. Keep the JSON audit record. Rendered reports must escape untrusted text and allow only credential-free HTTP(S) links.
