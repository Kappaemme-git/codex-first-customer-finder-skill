# Unreal Media Group Brand Prospecting Skill

**Working name:** `unreal-media-brand-prospector`
**Business unit:** Unreal Media Group
**Document status:** Product and operating specification
**Compatibility baseline:** Phase 1 defines the frozen local campaign, history, result, and report contracts
**Current release:** Phase 6 adds the operational finder/researcher and controlled product-photo/video filter described in `docs/PHASE_6_OPERATIONAL_FINDER.md`
**Outside this repository:** Autonomous research scheduling, speculative ad generation, outbound delivery, and reply handling

---

## 1. Executive Summary

The Unreal Media Group Brand Prospecting Skill will be a customized Codex skill that repeatedly finds, researches, qualifies, and records brands that are plausible customers for Unreal Media Group's AI-native creative services.

The skill will begin as a controlled research and qualification system. It will not initially generate ads, send cold outreach, or operate without review. Its first responsibility is to produce a high-quality, evidence-backed pipeline of unique brands that Unreal can decide to pursue.

The skill must improve on a generic first-customer finder in five important ways:

1. It must understand Unreal Media Group's actual services, ideal customers, disqualifiers, and sales motion.
2. It must load prior prospect history before every run so it does not repeatedly present the same brands as new.
3. It must support both unrestricted discovery and optional vertical-specific campaigns.
4. It must distinguish a merely relevant brand from a brand with a current reason to buy creative.
5. It must save structured results that future agents can use for deeper research, ad concepts, previews, approval, and outreach.

The long-term system will support a weekly process such as:

```text
Select campaign scope
    ↓
Load prior prospect history
    ↓
Discover candidate brands
    ↓
Normalize and deduplicate identities
    ↓
Qualify against UMG's ICP and current buying signals
    ↓
Save all accepted, rejected, and duplicate findings
    ↓
Deep-research the strongest candidates
    ↓
Prepare future creative-agent handoff records
    ↓
Human review
```

This document defines the complete desired behavior of the skill and the phased path toward the later automated creative workflow.

---

## 2. Business Context

Unreal Media Group is an AI-native creative studio that helps brands create premium marketing campaigns, advertising content, social assets, product visuals, UGC-style content, and multiple creative variations without relying on a traditional production process for every asset.

The prospecting skill should treat the following as core UMG capabilities:

- AI video advertisements
- AI product photography
- UGC-style advertisements
- AI creator content
- Paid-social creative
- Product launch creative
- Short-form vertical video
- Social media asset libraries
- Multiple hooks, angles, scenes, and format variations
- Product placement in environments that would be expensive or difficult to shoot traditionally
- Faster creative testing and production
- Creative packages for TikTok, Instagram, Meta, YouTube, Shorts, Reels, Shopify, Amazon, and other digital channels

The skill is not looking for any company that could theoretically use marketing. It is looking for brands that are likely to benefit specifically from Unreal's ability to create more visual content, test more concepts, reduce production logistics, and produce campaign-ready assets quickly.

---

## 3. Primary Objective

The skill's primary objective is:

> Produce a repeatable, evidence-backed list of unique brands that have a plausible current need, budget, and use case for Unreal Media Group's creative services.

A successful run should answer:

- Which brands should Unreal consider contacting?
- Why does each brand fit UMG?
- What current evidence suggests the timing may be good?
- What product, campaign, or creative problem could Unreal address?
- Has Unreal already discovered, researched, contacted, rejected, or worked with this brand?
- What should happen next?
- Which findings are observed facts, and which are model inferences?

The skill should optimize for sales usefulness, not list length.

---

## 4. Non-Goals for Phase 1

Phase 1 will not:

- Send emails, DMs, connection requests, comments, or form submissions
- Generate finished advertisements
- Impersonate brand representatives
- Use private, leaked, gated, or sensitive data
- Scrape platforms in ways that bypass their access controls or terms
- Automatically purchase enrichment data
- Claim that a brand is interested
- Treat industry fit alone as proof of buying intent
- overwrite prior prospect history
- hide duplicates instead of recording how they were handled
- create speculative claims about a brand's revenue, budget, or advertising performance
- select or use real celebrity, athlete, or influencer likenesses

Later phases may add controlled automation, but outbound activity will remain behind human approval.

---

## 5. Operating Modes

The skill must support multiple operating modes. A run may use one mode or combine compatible options.

### 5.1 Open Discovery Mode

Use when Unreal wants the skill to find the strongest brands across all supported industries.

Example:

```text
Find 30 new U.S. brands that are strong candidates for Unreal Media Group.
Do not restrict the vertical. Exclude any brand already recorded in the prospect database.
```

The skill should search broadly but still prioritize industries with strong visual products and repeatable creative demand.

### 5.2 Vertical-Focused Mode

Use when Unreal wants a campaign focused on a specific industry or category.

Examples:

- Fitness and activewear
- Fashion and apparel
- Beauty and skincare
- Supplements and wellness
- Food and beverage
- Consumer packaged goods
- Hospitality and travel
- Restaurants
- Sports products
- Jewelry and watches
- Technology accessories
- Real estate and developments
- Events and entertainment

A vertical is an optional filter, not a required field.

Example:

```text
Find 25 new fitness and activewear brands for UMG.
Prioritize brands with recent product drops or active paid-social creative.
```

### 5.3 Multi-Vertical Mode

Use when one weekly run should cover several related categories.

Example:

```text
Search fitness apparel, supplements, sports drinks, and training equipment.
Return no more than 10 brands from any one category.
```

### 5.4 Trigger-Focused Mode

Use when the campaign should prioritize a certain buying event rather than an industry.

Examples:

- Recent product launches
- Seasonal collections
- New market expansion
- Rebrand
- Funding announcement
- New retail distribution
- New e-commerce site
- New paid-social campaign
- Hiring for growth, paid media, content, or creative roles
- Existing campaign receiving weak or repetitive creative treatment
- Major event, holiday, or launch window
- New partnership or sponsorship

### 5.5 Geography-Focused Mode

The skill must optionally filter by:

- Country
- State or region
- City
- Language
- Shipping market
- Local, national, or global reach

The default should not assume that Miami-only brands are the best targets. UMG can serve remote brands, so geography should be used only when it contributes to the campaign strategy.

### 5.6 Re-Engagement Mode

This mode reviews brands already in the database and identifies those with a new meaningful trigger.

A prior brand should only return as a re-engagement candidate when:

- The cooldown period has expired
- A materially new public signal exists
- The reason for reconsideration is recorded
- Previous outcomes are visible
- The skill does not label it as a new discovery

### 5.7 Research Depth

The skill should retain configurable depth modes:

- `quick`: up to 10 qualified prospects
- `standard`: up to 25 qualified prospects
- `deep`: up to 50 qualified prospects with repeated-pattern analysis
- `watchlist`: save plausible brands without expensive deep research
- `reengagement`: inspect existing records for new triggers

These limits may be adjusted later based on research cost and output quality.

---

## 6. Required Campaign Input

Every run should be represented by a campaign configuration rather than an unstructured prompt alone.

Suggested configuration:

```yaml
campaign_name: "Fitness Brands - Week 1"
business_unit: "unreal-media-group"
mode: "vertical"
verticals:
  - "fitness"
  - "activewear"
geography:
  countries:
    - "United States"
language: "English"
target_new_prospects: 30
deep_research_limit: 12
minimum_qualification_score: 72
include_existing_for_reengagement: false
cooldown_days: 120
required_signals:
  - "active ecommerce presence"
preferred_signals:
  - "recent product launch"
  - "active paid social"
  - "frequent short-form content"
excluded_categories:
  - "regulated or prohibited products"
  - "inactive businesses"
output_formats:
  - "json"
  - "markdown"
  - "html"
```

### 6.1 Required Inputs

At minimum:

- Business unit
- Run name
- Target number of qualified leads
- Open discovery or filtered discovery
- Geographic scope
- Minimum score
- Whether prior brands may be reconsidered
- Output location

### 6.2 Optional Inputs

- Vertical or industry
- Product category
- Company size
- Estimated marketing maturity
- Price point
- E-commerce platform
- Recent trigger type
- Excluded categories
- Excluded companies
- Included companies
- Required source types
- Maximum age of evidence
- Desired contact role
- Campaign offer
- Prospect count by category
- Cooldown period
- Research budget
- Generation budget for later phases

### 6.3 Default Behavior

When no vertical is supplied, the skill should not ask for one unless the ambiguity prevents meaningful research. It should run open discovery using the UMG ICP and current strongest signals.

---

## 7. UMG Ideal Customer Profile

### 7.1 Primary ICP

The primary UMG prospect is a consumer-facing or visually marketable brand that:

- Has a product, location, experience, or offering that can be demonstrated visually
- Uses or should use paid social, organic short-form content, product photography, launch creative, or UGC
- Needs recurring creative rather than a single static design
- Can benefit from multiple hooks, scenes, formats, or variations
- Has an active website and identifiable current offering
- Shows signs of spending money on marketing, growth, creators, advertising, content, or product launches
- Has a realistic decision-maker or professional contact path
- Is not disqualified by legal, ethical, brand-safety, or practical concerns

### 7.2 Strong Prospect Characteristics

The skill should increase confidence when a brand has:

- A recent or upcoming product launch
- Multiple SKUs or collections
- Frequent promotions
- An active Meta Ad Library presence or other visible advertising activity
- High posting frequency but repetitive or weak visual creative
- Existing creator or UGC content
- Strong products but inconsistent presentation
- A premium price point that can support customer acquisition spending
- Recent funding or rapid expansion
- New retail placement
- New geographic expansion
- Hiring for content, paid media, growth, e-commerce, or creative production
- Seasonal campaign needs
- An obvious need for product photography across many environments
- Visual products that can be convincingly represented through AI-assisted production
- Existing use of traditional production that could benefit from additional variation

### 7.3 Adjacent ICP

The adjacent ICP may include:

- Hospitality groups
- Restaurants
- Resorts
- Events
- Real estate developments
- Service businesses with strong visual transformation potential
- Agencies that need production capacity
- Brands whose products are not inherently visual but whose customer outcome can be shown visually

Adjacent prospects should require stronger evidence of need because they are less naturally suited to UMG's core product-led creative model.

### 7.4 Disqualifiers

The skill should reject or downgrade brands when:

- The business appears inactive
- The website is broken, unfinished, or obviously abandoned
- The brand has no clear product or service
- There is no plausible visual use case
- The likely budget is too small for the intended offer
- The brand only needs basic local posting rather than campaign production
- The company is a direct competitor without a partnership rationale
- The product category creates unacceptable safety, legal, reputational, or platform risk
- The brand relies on misleading health, financial, or performance claims
- The brand is associated with counterfeit products or unauthorized intellectual property
- The only evidence is a generic directory listing
- The source is stale and there is no current activity
- The brand has already declined and the cooldown or re-engagement rules are not satisfied
- Unreal already has an active relationship with the brand and the record should be handled as an account, not a lead
- Product accuracy would be too difficult to preserve in a speculative concept
- The company requires geographic production that UMG cannot realistically provide

---

## 8. Discovery Strategy

The skill must search by evidence category rather than repeatedly issuing generic queries such as "best clothing brands."

### 8.1 Discovery Buckets

#### Product and Launch Signals

- New collection
- New product
- Seasonal launch
- Product restock
- New packaging
- New flavor, color, model, or SKU
- Crowdfunding success
- Retail expansion
- New direct-to-consumer store

#### Marketing Activity Signals

- Active social campaigns
- Frequent short-form posting
- Creator partnerships
- Influencer gifting
- Paid-social advertisements
- Product launch countdowns
- Brand ambassador programs
- New campaign announcements

#### Creative Need Signals

- Repetitive product photography
- Inconsistent product visuals
- Weak hook variety
- Limited UGC
- Heavy reliance on static assets
- Large catalog with sparse lifestyle content
- Strong products shown in low-quality environments
- Inconsistent visual identity across channels

These are observations, not insults. The report should use neutral language.

#### Growth and Timing Signals

- Funding
- Expansion
- Hiring
- New leadership
- New retail placement
- New geography
- Partnership
- Sponsorship
- Website relaunch
- New sales channel
- Upcoming event

#### Explicit Demand Signals

- Public request for UGC creators
- Public request for video production
- Public request for paid-social creative
- Agency request for production support
- Job post indicating urgent creative demand
- Founder discussing content bottlenecks
- Brand asking how to create more content

### 8.2 Source Types

Allowed public sources may include:

- Official brand websites
- Official product pages
- Official company blogs and press pages
- Public company social profiles
- Public professional profiles
- Public job listings
- Public ad libraries
- Public creator or ambassador pages
- Public crowdfunding pages
- Public retail announcements
- Public interviews
- Public reviews when relevant to product messaging
- Public business databases that permit access
- Search engine results only as discovery paths, not final evidence

The original source must be opened whenever practical.

---

## 9. Durable Prospect History

The skill must not depend on Codex memory or prior chat history.

Before discovery, it must load durable prospect history from the approved source of truth, expected to be Supabase through Unreal OS.

The history must include at least:

- Every previously discovered brand
- Every normalized domain
- Known social handles
- Known alternate names
- Parent company
- Discovery dates
- Campaigns in which the brand appeared
- Qualification decisions
- Contact attempts
- Replies
- Meetings
- Rejections
- Client status
- Cooldown date
- Suppression status
- Prior evidence and triggers
- Previous scores
- Notes and ownership

If the database cannot be loaded, the run should fail closed or clearly mark itself as a non-deduplicated test run. It should not silently continue and claim all results are new.

---

## 10. Identity Normalization and Deduplication

### 10.1 Canonical Identity

The strongest identity key should be the registrable root domain.

Examples:

```text
https://www.example.com/products/item
shop.example.com
example.com
```

All normalize to:

```text
example.com
```

### 10.2 Additional Identity Signals

The skill should compare:

- Canonical domain
- Company name
- Normalized company name
- Parent company
- Subsidiary
- Instagram handle
- LinkedIn company URL
- TikTok handle
- Shopify or storefront domain
- Contact page domain
- Legal business name
- Brand aliases

### 10.3 Duplicate Decisions

Each candidate should be classified as one of:

- `new_prospect`
- `existing_no_new_trigger`
- `existing_new_trigger`
- `existing_active_outreach`
- `existing_client`
- `suppressed`
- `possible_duplicate_needs_review`
- `distinct_subbrand`
- `parent_company_relationship`

### 10.4 Distinct Subbrands

Subbrands may be treated separately only when:

- They have independent websites or social identities
- They market different products
- They likely have separate decision-makers or budgets
- A separate campaign opportunity exists

The parent-child relationship must still be recorded.

### 10.5 Re-Discovery Rules

A previously recorded brand should not be returned as new.

It may be returned as a re-engagement candidate only when:

- A new trigger exists
- The evidence is dated and linked
- The prior outreach status allows reconsideration
- The cooldown has expired or a human overrides it
- The record explains why this is a new opportunity

### 10.6 Database Constraint

The database should eventually enforce uniqueness through canonical identity fields while still allowing multiple discovery events.

Suggested conceptual model:

```text
prospect
    one durable brand identity

prospect_identity
    domains, handles, aliases, parent relationships

prospect_discovery_event
    every time the brand is found in a campaign

prospect_signal
    dated public evidence

prospect_score
    scoring snapshot for a specific campaign

outreach_event
    drafted, approved, sent, replied, rejected, won

suppression
    do-not-contact and exclusion rules
```

---

## 11. Qualification Framework

A brand should not qualify merely because it belongs to a supported vertical.

### 11.1 Score Dimensions

Score each dimension from 0 to 5.

| Dimension | Weight | Meaning |
|---|---:|---|
| Creative need | 20% | Evidence that the brand needs more, better, faster, or more varied creative |
| Product and visual fit | 20% | How convincingly UMG can create useful content for the offering |
| Budget likelihood | 15% | Public indicators that the brand can purchase professional creative |
| Marketing activity | 15% | Evidence of active growth, advertising, creators, launches, or content |
| Timing | 15% | Strength and freshness of a current trigger |
| Reachability | 10% | Presence of a relevant public business contact path |
| Evidence quality | 5% | Reliability, specificity, and freshness of the supporting sources |

Formula:

```text
score =
  creative_need / 5 * 20
  + visual_fit / 5 * 20
  + budget_likelihood / 5 * 15
  + marketing_activity / 5 * 15
  + timing / 5 * 15
  + reachability / 5 * 10
  + evidence_quality / 5 * 5
```

### 11.2 Score Interpretation

- `85–100`: Priority candidate
- `72–84`: Qualified candidate
- `60–71`: Watchlist or needs more evidence
- `45–59`: Weak fit
- `<45`: Reject

The exact thresholds should be validated against actual reply and meeting data.

### 11.3 Required Minimum Evidence

A primary qualified record must have:

- At least one official company source
- At least one current fit, need, or timing signal
- A canonical domain
- A stated reason UMG can help
- A stated uncertainty or caution
- A score breakdown
- A discovery date
- A source date when available

### 11.4 Observed Versus Inferred

Every important field should be labeled internally as:

- `observed`
- `inferred_high_confidence`
- `inferred_low_confidence`
- `unknown`

Example:

```json
{
  "marketing_activity": {
    "value": "The brand is actively running paid social.",
    "basis": "observed",
    "source_url": "..."
  },
  "budget_likelihood": {
    "value": "Likely mid-market creative budget.",
    "basis": "inferred_low_confidence",
    "reason": "Premium pricing and multi-channel retail presence, but no budget is public."
  }
}
```

The skill must not present inferred budget as fact.

---

## 12. Prospect Stages

The skill should assign one of these research stages:

- `high_intent`: The company is publicly requesting creative, production, UGC, or related help.
- `active_trigger`: A current launch, expansion, campaign, or growth event creates urgency.
- `creative_gap`: Strong product and marketing activity with an identifiable creative opportunity.
- `strong_icp_fit`: Strong fit, but no immediate trigger.
- `watchlist`: Plausible future fit that needs more evidence.
- `disqualified`: Does not meet requirements.
- `duplicate`: Existing identity without a qualifying new event.
- `reengagement`: Existing brand with a new evidence-backed reason to revisit.

Only the first three should normally reach the highest-priority review queue.

---

## 13. Research Record Required for Every Candidate

Each accepted or rejected candidate should produce a structured record.

```json
{
  "company_name": "Example Brand",
  "canonical_domain": "example.com",
  "business_unit": "unreal-media-group",
  "campaign_id": "uuid",
  "discovery_status": "new_prospect",
  "qualification_stage": "active_trigger",
  "vertical": "fitness and activewear",
  "company_summary": "Observed company description",
  "primary_products": ["Product A", "Product B"],
  "hero_product": "Product A",
  "geography": ["United States"],
  "signals": [
    {
      "type": "product_launch",
      "summary": "The company launched a new collection.",
      "source_url": "https://...",
      "source_date": "2026-07-01",
      "basis": "observed"
    }
  ],
  "creative_opportunity": "A 9:16 product-led launch concept with multiple hooks.",
  "why_umg": "UMG can produce multiple launch assets without a traditional reshoot.",
  "score": 82,
  "score_dimensions": {
    "creative_need": 4,
    "visual_fit": 5,
    "budget_likelihood": 4,
    "marketing_activity": 4,
    "timing": 5,
    "reachability": 3,
    "evidence_quality": 4
  },
  "recommended_next_action": "deep_research",
  "cautions": [
    "Budget is inferred, not confirmed."
  ],
  "created_at": "2026-07-16T00:00:00Z"
}
```

Rejected and duplicate records should also be saved with a reason. This prevents the same weak brands from being repeatedly reconsidered.

---

## 14. Outputs

### 14.1 Structured Data

The primary machine-readable output should be JSON that can be written into Supabase.

### 14.2 Human Review Report

Each run should generate a report containing:

1. Campaign scope
2. Search assumptions
3. Source coverage
4. Number of raw candidates
5. Number of new unique brands
6. Number of duplicates
7. Number of re-engagement candidates
8. Number rejected
9. Qualified shortlist
10. Score breakdowns
11. Evidence links
12. Repeated market patterns
13. Recommended next actions
14. Research limitations
15. Estimated research cost
16. Errors or inaccessible sources

### 14.3 Rejection Report

The report should summarize why prospects were rejected:

- Already discovered
- Existing client
- Suppressed
- No current activity
- Weak visual fit
- No evidence of budget
- No current trigger
- Unsupported category
- Low source quality
- Possible duplicate
- Compliance or brand-safety risk

### 14.4 Future Creative Handoff

Phase 1 should prepare, but not execute, a future handoff record:

```json
{
  "prospect_id": "uuid",
  "creative_research_ready": true,
  "recommended_product": "Product A",
  "recommended_campaign_goal": "Launch awareness",
  "recommended_asset_type": "10-second vertical preview",
  "source_assets_to_review": [
    "official product page",
    "official brand guide",
    "official social profile"
  ],
  "approval_required_before_generation": true
}
```

---

## 15. Weekly Operating Workflow

### 15.1 Before the Run

A human chooses:

- Open or focused discovery
- Vertical, when desired
- Geography
- Number of brands
- Minimum score
- Campaign offer
- Whether re-engagement is allowed
- Research depth

### 15.2 Skill Execution

The skill:

1. Validates the campaign configuration.
2. Loads UMG positioning and ICP rules.
3. Loads the durable prospect history.
4. Loads suppression and cooldown rules.
5. Builds multiple discovery query buckets.
6. Finds candidate brands.
7. Opens and validates original sources.
8. Normalizes each company identity.
9. Checks for duplicates before expensive research.
10. Saves the discovery event.
11. Applies qualification rules.
12. Scores accepted candidates.
13. Saves rejections and duplicate reasons.
14. Produces the shortlist and report.
15. Prepares future creative handoff fields.
16. Stops before generating assets or sending outreach.

### 15.3 Human Review

A reviewer can:

- Approve for deeper research
- Reject
- Add to watchlist
- Merge duplicate identities
- Mark as existing relationship
- Suppress
- Adjust vertical
- Adjust score
- Assign an owner
- Record a comment

---

## 16. Learning and Feedback Loop

The skill should eventually use outcomes to improve prospect ranking.

Metrics to track by:

- Vertical
- Signal type
- Brand size
- Offer
- Source type
- Score range
- Outreach channel
- Creative type
- Assigned sender

Outcomes:

- Approved for research
- Preview generated
- Outreach approved
- Sent
- Delivered
- Replied
- Positive reply
- Meeting booked
- Proposal
- Won
- Lost
- No response
- Do not contact

The system should not automatically retrain or rewrite its own qualification rules. It should produce recommendations such as:

> Brands with recent product launches and existing creator content produced more positive replies than brands selected only for visual fit.

Humans then decide whether to change weights or campaign strategy.

---

## 17. Compliance and Brand Protection

The skill must:

- Use intentionally public business information
- Respect access controls and site restrictions
- Avoid personal or sensitive information
- Avoid unauthorized private contact enrichment
- Preserve source links
- Label uncertainty
- Avoid defamatory descriptions
- Avoid unsupported performance claims
- Never imply the brand commissioned a speculative concept
- Avoid fake testimonials, certifications, or endorsements
- Flag regulated or high-risk categories
- Keep outreach and creative generation behind later approval gates

Any future speculative preview should be labeled internally and externally as a concept that was not commissioned by the featured brand.

---

## 18. Failure Handling

The skill must fail visibly when:

- Prospect history cannot be loaded
- The database write fails
- A source cannot be verified
- A domain cannot be normalized
- A brand appears to match multiple existing records
- The requested target count cannot be reached without lowering quality
- Research results are stale
- A campaign configuration is contradictory
- The selected vertical has insufficient public evidence
- The model cannot separate fact from inference

It is better to return 12 strong brands than fabricate or weaken the standard to reach 30.

---

## 19. Phase Plan

## Phase 1: Customize the Prospecting Skill

This is the immediate focus.

Deliverables:

- Fork and rename the original skill
- Replace generic startup ICP logic with UMG-specific ICP logic
- Add campaign configuration
- Add optional vertical and geography filters
- Add open-discovery behavior
- Add durable prospect-history loading
- Add domain and identity normalization
- Add duplicate, re-engagement, suppression, and cooldown rules
- Add UMG-specific scoring
- Add structured JSON output
- Save rejected and duplicate candidates
- Generate a human-readable report
- Add test fixtures
- Run manual test campaigns
- Document install and usage

Phase 1 is complete when the skill can repeatedly run against the same test set and reliably avoid presenting prior brands as new.

## Phase 2: Scheduled Research Runner

Future scope:

- Create an agent or scheduled workflow that starts approved campaigns
- Manage retries, logs, costs, and run state
- Write results into Supabase
- Surface runs in Mission Control
- Require human approval before deeper research
- Prevent concurrent duplicate campaigns

## Phase 3: Brand Enrichment and Creative Brief Agent

Future scope:

- Inspect approved official websites and public marketing
- Extract products, brand voice, visuals, offers, claims, and campaign activity
- Recommend a campaign concept
- Produce a source-backed creative brief
- Require human approval before asset generation

## Phase 4: Speculative Preview Generation

Future scope:

- Create still frames first
- Validate product accuracy
- Generate a short preview only after approval
- Run visual, claim, intellectual-property, and brand-safety QA
- Store asset lineage and generation settings
- Add an Unreal concept-preview disclosure

## Phase 5: Outreach Approval and Sending

Future scope:

- Draft channel-appropriate messages
- Attach or link approved assets
- Require a human to approve the exact message and asset package
- Initially keep sending manual
- Record every outbound event and reply
- Use official APIs only where permitted
- Never enable unrestricted automatic cold DM activity

---

## 20. Phase 1 Acceptance Criteria

The customized skill is ready for use when all of the following are true:

- It can run with no vertical filter.
- It can run with one or more vertical filters.
- It can accept include and exclude lists.
- It loads historical prospects before research.
- It canonicalizes domains.
- It recognizes aliases and possible parent-company relationships.
- It does not label an existing brand as new.
- It can identify a prior brand with a new trigger.
- It records duplicate decisions.
- It records rejected brands and reasons.
- It provides linked, dated public evidence.
- It separates observations from inferences.
- It scores prospects using the UMG framework.
- It produces valid structured output.
- It produces a human-readable report.
- It creates no outreach and no creative asset.
- It stops safely when history or persistence is unavailable.
- It can be tested with deterministic fixtures.
- It supports manual review in the future Mission Control interface.

---

## 21. Proposed Skill Folder

```text
unreal-media-brand-prospector/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── unreal-media-positioning.md
│   ├── ideal-customer-profile.md
│   ├── discovery-framework.md
│   ├── qualification-framework.md
│   ├── deduplication-framework.md
│   ├── compliance-rules.md
│   ├── campaign-config.md
│   └── report-artifact.md
├── schemas/
│   ├── campaign-config.schema.json
│   ├── prospect.schema.json
│   ├── prospect-signal.schema.json
│   └── run-report.schema.json
├── scripts/
│   ├── normalize_domain.py
│   ├── normalize_company_name.py
│   ├── check_duplicates.py
│   ├── validate_campaign.py
│   ├── validate_output.py
│   └── generate_report.py
├── fixtures/
│   ├── existing-prospects.json
│   ├── duplicate-cases.json
│   ├── sample-campaigns/
│   └── expected-results/
└── README.md
```

The skill instructions should control research behavior. Deterministic operations such as normalization, schema validation, duplicate checks, and report rendering should be handled by scripts rather than left entirely to model judgment.

---

## 22. Example Phase 1 Invocation

Open discovery:

```text
Use $unreal-media-brand-prospector with campaign config
campaigns/2026-07-open-discovery.yaml.

Find up to 25 new qualified brands for Unreal Media Group.
Load prior prospect history before discovery.
Do not generate creative or send outreach.
Save accepted, rejected, duplicate, and re-engagement records.
```

Vertical discovery:

```text
Use $unreal-media-brand-prospector for a fitness and activewear campaign.

Prioritize recent product launches, active paid social, creator content,
and brands that need multiple visual variations.
Return only brands not previously recorded as new.
Do not generate assets or send messages.
```

Re-engagement:

```text
Use $unreal-media-brand-prospector in reengagement mode.

Review existing UMG prospects for meaningful public triggers from the last
60 days. Respect suppression and cooldown rules. Do not present any existing
brand as a new discovery.
```

---

## 23. Final Product Principle

The skill should not be judged by how many names it produces.

It should be judged by whether Unreal's team can open the report and quickly understand:

- why a brand belongs in the pipeline,
- why the timing matters,
- whether the brand is genuinely new,
- what evidence supports the opportunity,
- what uncertainties remain, and
- whether the brand deserves the cost of deeper research and creative production.

The prospecting skill is the qualification layer of the larger system. It should create clean, durable, reviewable inputs for later agents rather than trying to automate the entire sales process at once.

---

## Reference Sources

- Original Codex skill repository: https://github.com/Kappaemme-git/codex-first-customer-finder-skill
- Unreal Media Group: https://unrealmediagrp.com/
