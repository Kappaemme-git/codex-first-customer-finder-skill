# Unreal Talent Brand and Agency Prospecting Skill

**Working name:** `unreal-talent-campaign-prospector`  
**Business unit:** Unreal Talent  
**Document status:** Product and operating specification  
**Current build focus:** Phase 1, customize the Codex skill for repeatable brand and agency discovery, qualification, deduplication, filtering, and reporting  
**Deferred until later phases:** Automated research agents, speculative campaign generation, likeness use, outbound delivery, and reply handling

---

## 1. Executive Summary

The Unreal Talent Campaign Prospecting Skill will be a customized Codex skill that repeatedly finds, researches, qualifies, and records brands and agencies that may be strong buyers of licensed, talent-powered, AI-produced advertising campaigns.

This skill must be separate from the Unreal Media Group prospecting skill. The two businesses share infrastructure and some target industries, but they have different offers, budgets, risks, decision-makers, and qualification requirements.

Unreal Media Group can sell creative production to a wide range of brands. Unreal Talent requires a stronger campaign opportunity:

- A brand or agency that can realistically fund a talent-led campaign
- A product or message that benefits from recognizable talent
- A current launch, sponsorship, event, market expansion, or campaign need
- A plausible match to an approved talent category or roster
- A professional buying process
- Clear licensing, approval, and usage-right requirements
- Strong brand-safety compatibility

The skill's first responsibility is to build a clean pipeline of unique opportunities. It will not initially choose real talent, generate likeness-based previews, or send outreach.

The long-term workflow will be:

```text
Select campaign scope
    ↓
Load prior brand, agency, and relationship history
    ↓
Discover candidate campaign buyers
    ↓
Normalize and deduplicate companies and parent relationships
    ↓
Identify current campaign or sponsorship triggers
    ↓
Assess budget, talent fit, rights readiness, and brand safety
    ↓
Record qualified, rejected, duplicate, and re-engagement findings
    ↓
Prepare a future campaign-concept handoff
    ↓
Human review
```

Any later use of real talent must remain subject to documented rights and frame-by-frame approval.

---

## 2. Business Context

Unreal Talent is a talent-powered campaign platform that connects brands and agencies with licensed athletes, creators, celebrities, artists, and other talent, then produces approved advertising assets through AI-assisted production.

The prospecting skill should treat the following as core Unreal Talent capabilities:

- Matching brands or agencies to licensed talent
- AI-produced campaigns without a traditional photoshoot
- Producing multiple assets and formats from an approved campaign direction
- Faster turnaround than traditional talent production
- Reduced travel, studio, scheduling, and production constraints
- Structured likeness licensing
- Talent approval
- Frame-by-frame approval
- Brand-safety controls
- Defined usage rights
- Campaign production for digital, social, e-commerce, and broader brand use

This is not a general influencer list-building skill. It is a buyer-opportunity finder for brands and agencies that may purchase licensed talent campaigns.

---

## 3. Primary Objective

The skill's primary objective is:

> Produce a repeatable, evidence-backed list of unique brands and agencies that have a plausible current reason, budget, and campaign use case for an Unreal Talent engagement.

A successful run should answer:

- Which brands or agencies may be planning a campaign that benefits from talent?
- What current public trigger supports that conclusion?
- What kind of talent would fit the campaign?
- Is the proposed fit based on an approved roster option, a talent category, or an unverified assumption?
- What budget or organizational indicators suggest the opportunity is commercially realistic?
- Has Unreal already discovered, contacted, partnered with, rejected, or worked with the company?
- Are there brand-safety, rights, category-conflict, or exclusivity concerns?
- What should a human review next?

The skill should prioritize a smaller number of serious opportunities over a large list of ordinary consumer brands.

---

## 4. Non-Goals for Phase 1

Phase 1 will not:

- Generate content depicting any real athlete, celebrity, creator, musician, actor, chef, DJ, or other person
- Assume Unreal has rights to a person's likeness
- Represent that a person has approved a campaign
- Select a named talent without checking the approved roster and rights status
- Send cold messages
- Submit forms
- Enrich private contact information
- Bypass platform access controls
- Scrape private profiles
- Create fake endorsements
- Create misleading examples suggesting an existing partnership
- Promise campaign pricing or talent availability
- Ignore category conflicts, exclusivity, morals clauses, union rules, or jurisdictional requirements
- Treat ordinary influencer gifting as proof that a brand can fund a licensed talent campaign
- overwrite prior relationship history
- present existing opportunities as new

Later phases may generate campaign previews, but only with approved inputs and human authorization. Generic, non-identifiable placeholders may be used during concept development. Real likeness use requires documented permission.

---

## 5. Operating Modes

### 5.1 Open Campaign-Buyer Discovery

Use when Unreal wants the strongest opportunities across supported industries.

Example:

```text
Find 20 new U.S. brands or agencies that are plausible buyers of licensed,
talent-powered campaigns. Do not restrict the vertical. Exclude companies
already recorded in the Unreal Talent prospect database.
```

### 5.2 Vertical-Focused Discovery

Optional vertical filters may include:

- Sports apparel
- Athletic equipment
- Sports drinks
- Supplements and wellness
- Fashion and luxury
- Jewelry and watches
- Footwear
- Consumer electronics
- Gaming
- Entertainment
- Food and beverage
- Automotive
- Hospitality and travel
- Financial technology
- Retail
- Beauty
- Events
- Media
- Youth culture and lifestyle brands

A vertical is optional. The skill should support strong open discovery without forcing a category.

### 5.3 Talent-Category Discovery

The skill may optionally search for opportunities suited to a talent category:

- Athlete
- Musician
- Actor
- Creator
- Chef
- DJ
- Broad cultural personality
- Multiple-talent ensemble

This mode should use a category or archetype unless a current approved roster is loaded.

Example:

```text
Find campaigns that would benefit from a licensed athlete.
Do not name or imply availability of any athlete unless that talent appears
in the approved roster data loaded for this run.
```

### 5.4 Agency Mode

Find agencies that:

- Manage national or regional brand campaigns
- Need additional production capacity
- Work with talent or endorsements
- Need rapid asset variation
- Have clients in supported verticals
- Announce new accounts or campaign wins
- Hire for production, innovation, AI creative, social, or influencer roles
- Publicly seek production or talent partners

Agency records should identify the agency and, when public and appropriate, the client campaign opportunity. The system must distinguish between selling to the agency and selling directly to the client.

### 5.5 Trigger-Focused Mode

Prioritize:

- Major product launch
- Sponsorship announcement
- Athlete partnership
- League or event activation
- Seasonal national campaign
- New market entry
- New brand platform
- Rebrand
- Funding or expansion
- Agency-of-record change
- New agency client win
- Major retail distribution
- Upcoming sports or cultural moment
- Existing endorsement campaign that needs more asset volume
- Public campaign-production request

### 5.6 Geography and Market Mode

Optional filters:

- Country
- Region
- City
- Campaign market
- Language
- National versus regional campaign
- Rights territory

Geography matters more for Unreal Talent because licensing, market use, exclusivity, and talent relevance may vary by territory.

### 5.7 Re-Engagement Mode

Review existing companies for new campaign triggers.

Existing companies may return only when:

- There is a materially new trigger
- Prior outreach and relationship history is loaded
- Suppression and cooldown rules permit review
- The opportunity is labeled re-engagement
- The new campaign rationale is documented

### 5.8 Research Depth

Suggested modes:

- `quick`: up to 5 high-confidence opportunities
- `standard`: up to 15 qualified opportunities
- `deep`: up to 30 opportunities with campaign-pattern analysis
- `agency`: agency-specific research
- `roster-fit`: opportunities matched to approved talent categories or roster data
- `watchlist`: plausible future campaign buyers
- `reengagement`: existing companies with new triggers

---

## 6. Required Campaign Input

Suggested configuration:

```yaml
campaign_name: "Sports and Fitness Campaign Buyers - Week 1"
business_unit: "unreal-talent"
mode: "vertical"
buyer_types:
  - "brand"
  - "agency"
verticals:
  - "sports apparel"
  - "sports beverage"
talent_categories:
  - "athlete"
geography:
  countries:
    - "United States"
rights_territory:
  - "United States"
target_new_opportunities: 15
deep_research_limit: 8
minimum_qualification_score: 78
include_existing_for_reengagement: false
cooldown_days: 180
required_signals:
  - "active campaign or launch trigger"
preferred_signals:
  - "existing talent marketing"
  - "national or multi-market distribution"
excluded_categories:
  - "brand-safety prohibited"
  - "rights conflict"
approved_roster_source: null
allow_named_talent_recommendations: false
output_formats:
  - "json"
  - "markdown"
  - "html"
```

### 6.1 Required Inputs

- Business unit
- Run name
- Buyer type
- Open or filtered discovery
- Geography and likely rights territory
- Target count
- Minimum score
- Re-engagement setting
- Output location

### 6.2 Optional Inputs

- Vertical
- Talent category
- Approved roster source
- Agency-only or brand-only
- Company-size preference
- Campaign type
- Estimated budget floor
- Event or season
- Geographic rights
- Media channels
- Current category conflicts
- Excluded companies
- Included companies
- Cooldown
- Maximum evidence age
- Required signal types
- Roster availability
- Existing client or partner exclusions
- Restricted industries
- Desired decision-maker roles

### 6.3 Default Behavior

When no vertical or talent category is supplied, the skill should search broadly for the strongest current campaign opportunities. It should not invent a roster match.

---

## 7. Unreal Talent Ideal Customer Profile

### 7.1 Primary Brand ICP

The primary brand prospect:

- Has a consumer-facing product or service
- Has enough marketing maturity to run meaningful campaigns
- Has a plausible budget for licensed talent and professional production
- Benefits from trust, aspiration, culture, credibility, status, performance, or audience association
- Has an upcoming or active campaign trigger
- Uses or has used athletes, creators, celebrities, ambassadors, or sponsorships
- Operates in a category compatible with available talent
- Has a professional legal, marketing, or agency process
- Can define campaign usage, channels, territory, duration, and approval requirements

### 7.2 Primary Agency ICP

The primary agency prospect:

- Represents brands with meaningful campaign budgets
- Produces talent, influencer, social, sports, entertainment, or integrated campaigns
- Needs rapid production, asset volume, or AI-production capability
- Has a new client, campaign win, pitch, launch, or production need
- Can manage or participate in rights, approvals, and brand review
- Has identifiable decision-makers in production, creative, partnerships, influencer, innovation, or account leadership

### 7.3 Strong Prospect Characteristics

Increase confidence when the company:

- Already uses celebrity, athlete, creator, or influencer endorsements
- Sponsors teams, leagues, events, athletes, artists, or creators
- Announces a new partnership
- Launches nationally or across multiple markets
- Has high media visibility
- Has many campaign formats and channels
- Needs rapid localization or asset variation
- Has an upcoming event or seasonal moment
- Has a product tied to identity, aspiration, performance, lifestyle, or fandom
- Has strong retail distribution
- Has national paid-media activity
- Works through a recognized agency
- Has a history of professional advertising production
- Is hiring in influencer, partnerships, sports marketing, brand, production, or innovation
- Is publicly exploring AI production or virtual production
- Needs to extend the value of an existing approved talent relationship

### 7.4 Adjacent ICP

Adjacent opportunities may include:

- Regional brands seeking a recognizable local or category-relevant talent
- Agencies pitching new campaign ideas
- Event organizers
- Tourism organizations
- Sports organizations
- Entertainment properties
- Consumer brands moving from creator gifting into structured paid campaigns

Adjacent prospects should require stronger evidence of budget and campaign readiness.

### 7.5 Disqualifiers

Reject or downgrade when:

- The company appears unable to support the likely campaign budget
- There is no current campaign use case
- The brand seeks unpaid exposure-only arrangements
- The company has no professional marketing presence
- The proposed category is likely incompatible with roster rights
- The opportunity would require unauthorized likeness use
- The product or campaign would create serious reputational risk
- The category is prohibited, heavily restricted, deceptive, or unsafe
- The brand has unresolved controversies that create unacceptable talent risk
- The campaign appears political or issue-based without explicit policy approval
- The brand relies on unsupported medical, financial, or performance claims
- The company is inactive
- The source is stale
- The only evidence is a generic directory
- Unreal already has an active relationship that should be handled through account management
- Prior outreach resulted in suppression or an active cooldown
- The campaign conflicts with a known exclusive category
- The opportunity requires talent not on the approved roster and no category-level concept is useful
- The company cannot define usage rights or approval responsibilities

---

## 8. Approved Roster and Rights Context

The skill must treat roster and rights information as controlled data.

### 8.1 No Roster Loaded

When no approved roster is loaded:

- Recommend only a talent category or archetype
- Do not name a real person
- Do not imply availability
- Do not create a likeness-based concept
- Label roster fit as hypothetical

Example:

```text
Recommended talent archetype: active professional athlete with strong
fitness and lifestyle credibility.
```

### 8.2 Approved Roster Loaded

When approved roster data is available, the skill may evaluate fit only within the data's documented scope.

Required roster fields should eventually include:

- Talent ID
- Public or internal display name
- Talent category
- Approved brand categories
- Restricted categories
- Geographic rights availability
- Channel rights
- Duration constraints
- Exclusivity conflicts
- Approval status
- Current availability status
- Minimum commercial requirements
- Notes
- Data freshness

A match should still be labeled a recommendation, not a commitment.

### 8.3 Rights Readiness

The skill should score whether a prospect appears able to participate in a rights-managed process. It should consider:

- Professional marketing organization
- Agency involvement
- Legal or brand-review process
- History of endorsements
- Clear campaign channels
- Clear market and duration
- Reasonable brand-safety profile

It should not assume that public marketing sophistication means legal approval has already been secured.

---

## 9. Discovery Strategy

### 9.1 Campaign Trigger Buckets

#### Partnership and Sponsorship Signals

- New athlete partnership
- New creator partnership
- Team sponsorship
- League sponsorship
- Event sponsorship
- Ambassador announcement
- Music or entertainment collaboration
- Licensing partnership

#### Product and Market Signals

- National product launch
- Major collection
- New retail distribution
- Market expansion
- New geography
- New category
- Rebrand
- New customer segment

#### Agency Signals

- New account win
- New campaign pitch
- New production partnership
- Hiring
- Public request for partners
- Campaign case study
- Innovation initiative
- AI-production initiative

#### Campaign Volume Signals

- Existing endorsement with limited assets
- Large multi-channel campaign
- Multiple regional versions
- Frequent seasonal campaigns
- Need for continuous social variations
- Existing talent footage that cannot cover every format
- High cost or logistics of reshoots

#### Explicit Demand Signals

- Public request for talent
- Public request for influencer marketing
- Public request for campaign production
- Public request for AI production
- Job listing describing an immediate campaign need
- Request for sports marketing or entertainment partnerships

### 9.2 Source Types

Allowed public sources:

- Official brand websites
- Official agency websites
- Official press releases
- Official campaign announcements
- Official sponsorship pages
- Public ad libraries
- Public professional profiles
- Public job listings
- Public trade publications
- Public interviews
- Public event and league announcements
- Public social accounts
- Official roster and rights data supplied by Unreal
- Search results only as discovery paths

The skill should prioritize original announcements and official campaign material.

---

## 10. Durable Prospect and Relationship History

The skill must load permanent records before discovery.

It must include:

- Brands
- Agencies
- Parent companies
- Subsidiaries
- Existing clients
- Existing prospects
- Existing partners
- Existing talent relationships
- Prior campaign discussions
- Prior outreach
- Replies
- Meetings
- Proposals
- Wins and losses
- Suppression
- Cooldown
- Category conflicts
- Exclusivity notes
- Known agency-of-record relationships
- Previous roster-fit analysis
- Prior triggers
- Prior scores

If history cannot be loaded, the skill must not claim that a company is new.

---

## 11. Identity Normalization and Deduplication

### 11.1 Company Identity

Use:

- Canonical root domain
- Company name
- Parent company
- Subsidiary
- Agency network
- Social handles
- LinkedIn company identity
- Legal name
- Brand aliases

### 11.2 Relationship Identity

The same commercial opportunity may involve:

- Brand
- Parent company
- Agency of record
- Media agency
- Influencer agency
- Talent agency
- Production partner
- Sponsorship partner

The skill should avoid creating five unrelated leads for one campaign.

It should record a relationship graph:

```text
Parent company
    owns → Brand

Agency
    represents → Brand

Brand
    sponsors → Event

Campaign opportunity
    belongs to → Brand
    may be purchased through → Agency
```

### 11.3 Duplicate Classifications

- `new_brand_opportunity`
- `new_agency_opportunity`
- `existing_no_new_trigger`
- `existing_new_campaign_trigger`
- `existing_active_relationship`
- `existing_client`
- `existing_partner`
- `suppressed`
- `possible_duplicate_needs_review`
- `same_campaign_different_source`
- `related_parent_or_subbrand`
- `agency_brand_overlap`

### 11.4 Re-Engagement

An existing company may re-enter only when:

- A new campaign trigger exists
- Previous relationship context is visible
- Cooldown permits it
- Category conflict does not prohibit it
- The system labels it re-engagement
- The skill explains why the opportunity changed

---

## 12. Qualification Framework

### 12.1 Score Dimensions

Score each dimension from 0 to 5.

| Dimension | Weight | Meaning |
|---|---:|---|
| Campaign and talent fit | 20% | How strongly recognizable talent improves the campaign |
| Budget likelihood | 20% | Public indicators that the buyer can fund licensing and production |
| Current trigger | 20% | Strength and freshness of a launch, partnership, event, or campaign need |
| Rights and organizational readiness | 15% | Likelihood that the buyer can handle licensing, approvals, territory, and usage |
| Brand and roster compatibility | 10% | Category fit and absence of obvious conflicts |
| Decision-path reachability | 10% | Presence of a relevant professional contact or agency route |
| Evidence quality | 5% | Reliability, specificity, and freshness |

Formula:

```text
score =
  campaign_talent_fit / 5 * 20
  + budget_likelihood / 5 * 20
  + current_trigger / 5 * 20
  + rights_readiness / 5 * 15
  + brand_roster_compatibility / 5 * 10
  + decision_path / 5 * 10
  + evidence_quality / 5 * 5
```

### 12.2 Score Interpretation

- `88–100`: Priority campaign opportunity
- `78–87`: Qualified opportunity
- `65–77`: Watchlist or requires validation
- `50–64`: Weak commercial fit
- `<50`: Reject

These thresholds should later be tuned using actual meetings, proposals, and wins.

### 12.3 Required Minimum Evidence

A qualified opportunity must include:

- Official company or agency source
- Current campaign, partnership, launch, or growth signal
- Plausible talent-powered use case
- Budget indicators or a clear budget uncertainty
- Brand-safety and rights caution
- Buyer-path recommendation
- Canonical identity
- Score breakdown
- Source links and dates

### 12.4 Observed Versus Inferred

Every important field should be labeled:

- `observed`
- `inferred_high_confidence`
- `inferred_low_confidence`
- `unknown`
- `requires_internal_rights_check`

No talent availability, budget, category clearance, or licensing right may be stated as observed unless the approved source explicitly supports it.

---

## 13. Opportunity Stages

- `high_intent`: Buyer is publicly seeking talent, partnerships, campaign production, or related services.
- `active_campaign_trigger`: Strong current launch, sponsorship, event, or campaign signal.
- `talent_extension_opportunity`: Existing talent use could benefit from more assets or faster production.
- `strong_strategic_fit`: Strong brand and budget fit without an urgent trigger.
- `agency_channel_opportunity`: Agency could buy or introduce the service.
- `watchlist`: Plausible future fit.
- `rights_review_required`: Commercial opportunity exists but internal rights or conflict review is necessary.
- `disqualified`
- `duplicate`
- `reengagement`

Priority should favor high intent, active triggers, and talent-extension opportunities.

---

## 14. Research Record Required for Every Opportunity

```json
{
  "company_name": "Example Brand",
  "company_type": "brand",
  "canonical_domain": "example.com",
  "parent_company": "Example Holdings",
  "agency_relationships": [],
  "business_unit": "unreal-talent",
  "campaign_id": "uuid",
  "discovery_status": "new_brand_opportunity",
  "opportunity_stage": "active_campaign_trigger",
  "vertical": "sports beverage",
  "geography": ["United States"],
  "rights_territory": ["United States"],
  "campaign_signal": {
    "type": "partnership_announcement",
    "summary": "The brand announced a new sports partnership.",
    "source_url": "https://...",
    "source_date": "2026-07-01",
    "basis": "observed"
  },
  "talent_use_case": "A multi-format campaign featuring a licensed athlete archetype.",
  "talent_recommendation_type": "archetype_only",
  "talent_archetype": "professional athlete with performance credibility",
  "named_talent": null,
  "rights_status": "requires_internal_rights_check",
  "brand_safety_status": "preliminary_pass",
  "score": 84,
  "score_dimensions": {
    "campaign_talent_fit": 5,
    "budget_likelihood": 4,
    "current_trigger": 5,
    "rights_readiness": 4,
    "brand_roster_compatibility": 3,
    "decision_path": 4,
    "evidence_quality": 4
  },
  "recommended_buyer_path": "brand_direct",
  "recommended_next_action": "internal_review",
  "cautions": [
    "No named talent should be proposed until roster and conflicts are checked.",
    "Budget is inferred, not confirmed."
  ],
  "created_at": "2026-07-16T00:00:00Z"
}
```

Rejected and duplicate opportunities must also be saved with reasons.

---

## 15. Brand Safety and Conflict Review

The skill should perform a preliminary screen and mark anything requiring human review.

Possible flags:

- Alcohol
- Nicotine
- Gambling
- Weapons
- Adult content
- Political activity
- Medical or health claims
- Financial claims
- Supplements
- Youth audiences
- Controversial products
- Labor or human-rights controversy
- Environmental controversy
- Active litigation
- Existing competitor endorsement
- Category exclusivity
- Geographic exclusivity
- Morals-clause concern
- Union or guild implications
- Synthetic likeness restriction
- Platform restriction

The skill does not make final legal decisions. It marks known risks and routes the opportunity for human review.

---

## 16. Outputs

### 16.1 Structured Data

Primary JSON output for Supabase and Unreal OS.

### 16.2 Human Review Report

The report should contain:

1. Campaign scope
2. Buyer types
3. Talent category, when selected
4. Rights territory
5. Source coverage
6. Raw candidate count
7. New unique opportunities
8. Duplicates
9. Re-engagement opportunities
10. Qualified shortlist
11. Brand versus agency path
12. Score breakdown
13. Campaign triggers
14. Talent archetype fit
15. Roster and rights status
16. Brand-safety flags
17. Recommended next action
18. Limitations
19. Research errors
20. Estimated research cost

### 16.3 Relationship View

The output should show when multiple entities relate to one opportunity:

```text
Brand: Example Brand
Parent: Example Holdings
Agency: Example Creative
Campaign trigger: New national launch
Recommended route: Agency introduction
```

### 16.4 Future Campaign-Concept Handoff

Phase 1 should prepare, but not execute:

```json
{
  "opportunity_id": "uuid",
  "campaign_concept_ready": true,
  "approved_for_concept_research": false,
  "talent_mode": "archetype_only",
  "talent_category": "athlete",
  "named_talent_allowed": false,
  "rights_check_required": true,
  "brand_safety_review_required": true,
  "recommended_campaign_goal": "national product launch",
  "recommended_preview_type": "storyboard with generic placeholder",
  "human_approval_required_before_generation": true
}
```

---

## 17. Weekly Operating Workflow

### 17.1 Before the Run

A human selects:

- Open or filtered discovery
- Brand, agency, or both
- Vertical
- Talent category, if desired
- Territory
- Campaign event or trigger
- Target count
- Minimum score
- Re-engagement setting
- Approved roster source, if any
- Exclusions and conflicts

### 17.2 Skill Execution

The skill:

1. Validates the campaign configuration.
2. Loads Unreal Talent positioning.
3. Loads current ICP and disqualifier rules.
4. Loads durable brand, agency, relationship, and outreach history.
5. Loads suppression, cooldown, conflict, and rights rules.
6. Loads approved roster data if supplied.
7. Builds multiple discovery query buckets.
8. Finds candidate buyers.
9. Opens original sources.
10. Normalizes company identities.
11. Maps brand, parent, and agency relationships.
12. Checks duplicates before expensive research.
13. Saves discovery events.
14. Assesses campaign and talent fit.
15. Performs preliminary brand-safety and conflict screening.
16. Scores opportunities.
17. Saves accepted, rejected, duplicate, and re-engagement results.
18. Prepares future concept-handoff fields.
19. Produces the report.
20. Stops before likeness use, creative generation, or outreach.

### 17.3 Human Review

A reviewer may:

- Approve for deeper campaign research
- Reject
- Add to watchlist
- Merge identities
- Correct agency relationships
- Mark existing partner
- Mark existing client
- Add conflict
- Add roster note
- Request legal review
- Suppress
- Assign owner
- Adjust score
- Approve archetype-only concept development

---

## 18. Learning and Feedback Loop

Track performance by:

- Brand versus agency
- Vertical
- Campaign trigger
- Talent category
- Score range
- Budget indicator
- Rights-readiness score
- Source type
- Buyer role
- Outreach channel
- Campaign concept
- Assigned sender

Outcomes:

- Approved for research
- Rights reviewed
- Roster match found
- Concept approved
- Preview generated
- Outreach approved
- Sent
- Positive reply
- Meeting
- Roster discussion
- Proposal
- Campaign won
- Lost
- No response
- Conflict
- Do not contact

The system should report patterns but not automatically modify legal, rights, or brand-safety policies.

---

## 19. Compliance and Rights Principles

The skill must enforce these principles:

1. No real person's likeness is used without documented authorization.
2. Public availability of an image does not create commercial usage rights.
3. A roster match is not the same as talent availability.
4. Talent availability is not the same as campaign approval.
5. Campaign approval is not the same as final asset approval.
6. Every use must be governed by scope, territory, duration, channels, and approvals.
7. No output may imply a brand or talent relationship that does not exist.
8. Speculative concepts must be clearly labeled.
9. Outreach stays behind human approval.
10. Final legal and rights decisions belong to authorized humans.

---

## 20. Failure Handling

The skill must fail visibly when:

- Durable history cannot be loaded
- Approved roster data is requested but unavailable
- A named-talent request lacks permission
- Rights territory is undefined for a rights-sensitive task
- The database write fails
- A company identity maps to conflicting records
- An agency and brand appear to represent the same opportunity
- The source is stale or cannot be verified
- The target count cannot be met without weak leads
- A category conflict cannot be resolved
- Brand-safety risk is material
- A campaign would depend on unsupported claims
- The model cannot distinguish observation from inference

It should return fewer opportunities rather than inventing fit.

---

## 21. Phase Plan

## Phase 1: Customize the Prospecting Skill

This is the immediate focus.

Deliverables:

- Fork and rename the original skill
- Replace generic startup logic with Unreal Talent buyer logic
- Add brand and agency modes
- Add optional vertical filters
- Add optional talent-category filters
- Add rights-territory input
- Add durable history loading
- Add company, parent, agency, and campaign identity resolution
- Add duplicate and re-engagement rules
- Add suppression and cooldown rules
- Add campaign-trigger research
- Add talent-archetype logic
- Prevent named-talent output unless approved roster data allows it
- Add brand-safety and conflict flags
- Add Unreal Talent scoring
- Add structured output and reports
- Save rejections and duplicate findings
- Add tests

Phase 1 is complete when repeated runs do not present the same brand, agency, or campaign as new and no output can imply unauthorized talent availability.

## Phase 2: Scheduled Research Runner

Future scope:

- Start approved recurring campaigns
- Manage run state, retries, logs, and cost
- Store results in Supabase
- Surface campaigns in Mission Control
- Require approval before deeper campaign research
- Prevent overlapping research on the same opportunity

## Phase 3: Campaign Enrichment Agent

Future scope:

- Research the approved brand, campaign, audience, product, agency, and existing talent use
- Inspect official sources
- Build a source-backed campaign brief
- Recommend talent archetypes or approved roster matches
- Request rights and conflict review
- Stop before creative generation

## Phase 4: Speculative Campaign Preview

Future scope:

- Default to generic or non-identifiable placeholders
- Use named talent only after documented authorization
- Generate storyboards or still concepts first
- Obtain human approval
- Produce a short preview
- Run brand-safety, likeness, product, claim, and approval checks
- Clearly label speculative work
- Keep full asset lineage

## Phase 5: Outreach Approval and Sending

Future scope:

- Draft brand-direct and agency messages
- Include the approved concept or preview
- Require human approval of recipient, message, assets, and rights statements
- Initially send manually
- Record every outbound event
- Use official APIs only where permitted
- Never create unrestricted cold-DM automation

---

## 22. Phase 1 Acceptance Criteria

The skill is ready when:

- It supports open discovery.
- It supports optional vertical filtering.
- It supports brand-only, agency-only, or combined discovery.
- It supports optional talent categories.
- It requires or records likely rights territory.
- It loads existing prospects and relationships.
- It canonicalizes company domains.
- It maps parent and agency relationships.
- It avoids duplicate campaign opportunities.
- It never labels an existing company as new.
- It supports evidence-backed re-engagement.
- It records rejection and duplicate reasons.
- It separates facts from inferences.
- It uses current public sources.
- It provides UMG-independent Unreal Talent scoring.
- It flags brand-safety and conflict issues.
- It never names talent without approved roster authorization.
- It never implies availability or approval.
- It outputs valid JSON.
- It produces a human-readable report.
- It generates no likeness-based creative.
- It sends no outreach.
- It fails safely when history, roster, or persistence is unavailable.
- It can be tested with fixtures representing brand, agency, parent, and campaign duplicates.

---

## 23. Proposed Skill Folder

```text
unreal-talent-campaign-prospector/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── unreal-talent-positioning.md
│   ├── brand-ideal-customer-profile.md
│   ├── agency-ideal-customer-profile.md
│   ├── campaign-trigger-framework.md
│   ├── qualification-framework.md
│   ├── relationship-and-deduplication.md
│   ├── roster-and-rights-rules.md
│   ├── brand-safety-rules.md
│   ├── campaign-config.md
│   └── report-artifact.md
├── schemas/
│   ├── campaign-config.schema.json
│   ├── opportunity.schema.json
│   ├── relationship.schema.json
│   ├── signal.schema.json
│   ├── roster-reference.schema.json
│   └── run-report.schema.json
├── scripts/
│   ├── normalize_domain.py
│   ├── normalize_company_name.py
│   ├── resolve_relationships.py
│   ├── check_duplicates.py
│   ├── validate_campaign.py
│   ├── validate_rights_constraints.py
│   ├── validate_output.py
│   └── generate_report.py
├── fixtures/
│   ├── existing-opportunities.json
│   ├── brand-agency-relationships.json
│   ├── duplicate-cases.json
│   ├── roster-restriction-cases.json
│   ├── sample-campaigns/
│   └── expected-results/
└── README.md
```

Deterministic operations such as normalization, relationship resolution, duplicate checking, schema validation, and report generation should be handled by code. The model should handle research, synthesis, and evidence-based judgment within explicit rules.

---

## 24. Example Phase 1 Invocations

Open discovery:

```text
Use $unreal-talent-campaign-prospector with the current Unreal Talent ICP.

Find up to 15 new brand or agency campaign opportunities in the United States.
Do not restrict the vertical. Load prior history first. Use talent archetypes
only. Do not generate creative and do not send outreach.
```

Vertical and talent category:

```text
Use $unreal-talent-campaign-prospector for sports apparel and sports beverages.

Prioritize active national launches and brands that already use athlete
marketing. Recommend an athlete archetype only unless the approved roster
source explicitly permits named recommendations.
```

Agency mode:

```text
Use $unreal-talent-campaign-prospector in agency mode.

Find agencies with recent client wins, sports or entertainment accounts,
talent campaign experience, or a public need for rapid production.
Map the agency to the relevant brand opportunity when evidence exists.
```

Re-engagement:

```text
Use $unreal-talent-campaign-prospector in reengagement mode.

Review prior brand and agency records for new campaign, sponsorship, launch,
or partnership triggers from the last 90 days. Respect suppression, cooldown,
rights, and conflict rules.
```

---

## 25. Final Product Principle

This skill should not behave like a generic celebrity endorsement generator.

It should behave like the first qualification layer of a rights-managed campaign business.

A strong output allows Unreal's team to quickly understand:

- why this buyer may be ready,
- why talent adds value,
- what current trigger creates urgency,
- whether the company is truly new,
- whether the sales path is direct or through an agency,
- what rights and conflicts require review,
- what is known versus inferred, and
- whether the opportunity deserves deeper campaign research.

The skill should create clean, defensible, durable opportunities for later agents. It must never trade rights safety or brand credibility for automation speed.

---

## Reference Sources

- Original Codex skill repository: https://github.com/Kappaemme-git/codex-first-customer-finder-skill
- Unreal Talent: https://unreal-talent.com/
- Unreal Media Group: https://unrealmediagrp.com/
