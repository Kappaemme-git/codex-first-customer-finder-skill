# Report Artifact

Create a standalone HTML report from the final qualified prospect data. Use the bundled generator instead of writing report markup manually.

## Generate

```bash
python3 scripts/generate_report.py analysis.json outputs/first-customer-finder-report.html
```

Return a clickable absolute file link in Codex. Keep the JSON in a work or temporary directory unless the user asks for raw data.

## JSON schema

```json
{
  "title": "First Customer Finder",
  "product": "Example product",
  "product_url": "https://example.com",
  "target_customer": "Independent gym owners",
  "search_scope": "Public English-language sources, last 12 months",
  "generated_at": "2026-07-12",
  "verdict": "The strongest early demand comes from owners manually chasing failed membership payments.",
  "prospects": [
    {
      "name": "Example Gym",
      "type": "Company",
      "stage": "Problem aware",
      "score": 82,
      "pain_signal": "The owner publicly described manually following up on overdue memberships.",
      "evidence": "A recent public post describes the workflow and time cost.",
      "why_fit": "The product automates the exact reminder and payment step.",
      "why_now": "The post is recent and asks how other owners handle the process.",
      "source_title": "How do you handle failed payments?",
      "source_url": "https://example.com/public-post",
      "source_type": "Public forum",
      "signal_date": "2026-07-01",
      "suggested_channel": "Reply to the public discussion",
      "opener": "Saw your question about failed-payment follow-up. We are testing a checklist for reducing manual payment chasing. Worth sending to whoever owns membership billing?",
      "caution": "Confirm the workflow is still active before pitching.",
      "dimensions": {
        "pain_strength": 5,
        "product_fit": 5,
        "timing": 4,
        "reachability": 4,
        "evidence_quality": 4
      }
    }
  ],
  "patterns": [
    {
      "title": "Manual follow-up",
      "count": 4,
      "insight": "Owners rely on spreadsheets and messaging apps after payments fail."
    }
  ],
  "outreach_plan": {
    "angle": "Offer a manual concierge test before asking for software adoption.",
    "first_step": "Contact the three highest-scoring prospects with one source-based question.",
    "follow_up": "Share a two-minute mockup only after they confirm the pain.",
    "success": "Three conversations and one design-partner commitment within seven days."
  },
  "limits": [
    "These are potential customers inferred from public signals, not confirmed buyers.",
    "Verify current relevance before any outreach and keep contact manual."
  ]
}
```

Normal mode should contain up to ten qualified prospects. Every primary prospect must include a valid public source URL and a score from 0 to 100.

Use `opener` for a short source-grounded message with a concrete manual CTA. Avoid vague CTAs such as "would this be useful?" when a sharper routing ask is available.
