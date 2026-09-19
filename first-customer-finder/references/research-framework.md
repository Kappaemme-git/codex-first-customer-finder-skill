# Research and Qualification Framework

Use this framework to keep prospect research evidence-based, current, and respectful.

## Research sequence

### Product brief

Define:

- product and promised outcome
- primary user and economic buyer
- urgent job to be done
- current alternative or workaround
- likely adoption trigger
- geography or language constraint
- clear disqualifiers

Do not begin broad lead collection until this brief is specific enough to reject weak matches.

### Query buckets

Search several buckets rather than repeating one query:

1. **Explicit demand:** “looking for,” “recommend a tool,” “alternative to,” “does anything exist.”
2. **Pain:** “takes hours,” “manual,” “frustrating,” “hate,” “difficult,” “keeps breaking.”
3. **Workaround:** spreadsheets, copy-paste, virtual assistants, scripts, templates, or repeated manual steps.
4. **Switching:** cancellation, migration, missing feature, pricing complaint, or competitor frustration.
5. **Timing:** public launch, hiring, expansion, new workflow, regulation, integration, or process change relevant to the product.

Adapt wording to the audience's language. Search the original public page and do not qualify from a search snippet alone.

### Source mix

Useful public sources include:

- forums and public community discussions
- public social posts and replies
- product reviews and app marketplace reviews
- GitHub issues and public feature requests
- public company pages, job posts, changelogs, or announcements
- public “looking for a tool” posts and directories

Avoid private groups, gated communities, data brokers, scraped contact databases, and sources that prohibit access.

## Qualification score

Score every dimension from 0 to 5:

- **Pain strength (25%)** — directness, severity, repetition, and cost of the stated problem.
- **Product fit (25%)** — how directly the startup solves the evidenced job.
- **Timing (20%)** — freshness and presence of a current trigger.
- **Public reachability (15%)** — a natural, relevant public or professional contact path exists.
- **Evidence quality (15%)** — specificity, source reliability, and confidence that the signal belongs to the prospect.

Calculate:

```text
score = pain_strength/5*25
      + product_fit/5*25
      + timing/5*20
      + reachability/5*15
      + evidence_quality/5*15
```

Interpretation:

- **80–100:** strong first-customer candidate
- **65–79:** promising, validate quickly
- **50–64:** plausible but missing a material signal
- **Below 50:** do not include in the primary shortlist

An old explicit request can still be relevant, but reduce timing and label the date. A company that merely matches the industry without an evidenced trigger is not a qualified prospect.

Record `checked_at` separately from `signal_date`. Checking an old post today does not make its demand new. With an unknown publication date, timing must be at most 2/5 unless another dated, cited signal supports it (use that as the primary source). With no verified suitable contact route, reachability must be at most 1/5. Scores are prioritization judgments, not conversion probabilities. The v2 generator calculates the weighted score from the dimensions.

Only sources actually opened and inspected can have `evidence_status: "verified"`; this means the public source was inspected, not that the person intends to buy. Unavailable, snippet-only, ambiguous-author, resolved, and contradictory signals belong in research limits or rejected candidates, not the primary shortlist. Recheck context and replies when they could show the problem is already solved.

## Prospect stages

- **High intent:** publicly requesting a solution or actively switching.
- **Problem aware:** clearly describing the pain or expensive workaround.
- **Trigger present:** a current business event makes the product relevant.
- **Potential fit:** ICP match with incomplete evidence; keep outside the primary shortlist.

## Outreach rules

Draft one opener using this shape:

1. mention the public context naturally
2. connect it to the buyer's exact problem in their language
3. offer a concrete next step the founder can realistically provide
4. ask one low-friction CTA that can be accepted, declined, or forwarded

Good: “Should I send a two-minute walkthrough of the reminder workflow?” or “Is the owner the right person to ask about membership billing?” Weak: “Would this be useful?” without saying what happens next. Do not invent a completed teardown, integration, testimonial, or business result to make the offer stronger.

Record the target role/function (`role_basis`: `observed` or `inferred`), a concrete `next_step`, the `cta`, and the likely objection in `caution`. Include the exact CTA in the draft. Prefer a context-appropriate public reply or official contact route; identify the route's URL, supporting page, date checked, and suitability. Community rules can make a visible reply box inappropriate for promotion. Mark `not_found` instead of guessing a business email, URL path, or permission to contact. A generic home page is not evidence of a contact mechanism.

Keep it under 90 words by default. Never claim the message was sent. Do not include private emails, phone numbers, personal addresses, family information, or sensitive traits.

## Evidence ledger

For each qualified prospect record:

- displayed company, project, or public professional name
- source title and URL
- visible publication date or “date unavailable”
- source type
- concise pain or timing signal
- observed evidence versus inference
- score breakdown
- freshness warning when relevant

Use citations in the chat response whenever web research was performed.
