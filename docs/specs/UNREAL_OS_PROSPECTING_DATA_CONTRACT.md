# Unreal OS Prospecting Data Contract

**Program phase:** Prospecting Phase 2 — contract design only
**Status:** Independently reviewed and finalized on 2026-07-17; design-only and not implemented
**Phase 1 compatibility checkpoint:** `f77236a`
**Applies to:** `unreal-media-brand-prospector` and `unreal-talent-campaign-prospector`

## 1. Authority and boundary

This document defines the future durable data contract for storing Phase 1 prospecting campaigns,
runs, accounts, evidence, decisions, contact context, and safety state in Unreal OS. It is subordinate
to the program roadmap and must be reconciled with the Unreal OS contract freeze before a later,
separately authorized implementation phase.

This is a design artifact only. It creates no SQL, migration, Supabase object, API, UI, worker,
schedule, loop, creative, likeness, contact record, or outreach. No real prospect or contact data is
included. A later implementation must use reviewed repository migrations and synthetic fixtures.

The contract reuses, rather than duplicates, these Unreal OS governance primitives:

- `os_users` and `os_roles` for authenticated identity and authorization;
- `os_approval_requests` for per-action, expiring human approval;
- `os_action_log` for the append-only action ledger;
- `os_audit_events` for structured, redacted governance/security events; and
- `os_evidence_packets` for reviewed aggregate evidence packets.

Prospecting evidence URLs belong in `os_prospecting_evidence_refs`. A reviewed run or governance
packet may additionally reference `os_evidence_packets`; the two are not interchangeable.

## 2. Contract invariants

1. Accounts, contacts, discovery events, public signals, decisions, and outreach events are distinct
   records. They must not be collapsed into a flat `leads` row.
2. Every primary key is `uuid`; every time instant is `timestamptz`; source dates without a known time
   are `date`.
3. Ingestion records `schema_version`, `source_system`, and `source_record_id`. Source identifiers are
   idempotency inputs, never trusted as authorization.
4. History is append-only or superseded. Material prior decisions, suppressions, cooldowns, scores,
   and outreach events are not overwritten or deleted.
5. Identity ambiguity fails closed. A domain, alias, public handle, or relationship collision blocks
   qualification/re-engagement until an authorized human resolves it.
6. Suppression, active-client, active-partner, and active-outreach protections outrank a subbrand or
   re-engagement classification. A distinct subbrand never bypasses account-level protection.
7. Evidence is credential-free and source-backed. Search snippets are discovery aids only; a final
   evidence reference uses an intentionally public original source when practical.
8. Scores are immutable snapshots of a named rubric version. Later corrections create a new snapshot.
9. Decisions are durable. Corrections supersede prior decisions and retain the prior record.
10. Contact data is limited to publicly presented business identity and business contact points with
    provenance and review status. Private enrichment and sensitive-trait inference are prohibited.
11. Outreach events are append-only historical facts or proposals. This contract creates no sending
    authority and stores no message body by default.
12. Exact Phase 1 replay uses an immutable artifact reference, schema version, byte length, media type,
    and integrity hash. Normalized rows alone are not the replay source.

## 3. Shared conventions

### 3.1 Common provenance fields

Every ingested entity includes the applicable subset below. Append-only entities use `recorded_at`
instead of mutable `updated_at` semantics.

| Field | PostgreSQL type | Rule |
| --- | --- | --- |
| `id` | `uuid` | Required primary key; generated server-side in a future implementation. |
| `business_unit` | `text` | Required where business-unit scope applies; `unreal-media-group` or `unreal-talent`. |
| `schema_version` | `integer` | Required, positive; version of this normalized contract. |
| `source_system` | `text` | Required for ingestion; allowlisted producer such as `phase1_json`. |
| `source_record_id` | `text` | Required for ingestion; stable identifier within source system. |
| `source_run_id` | `text` | Nullable except run-derived rows; Phase 1 `run_metadata.run_id`. |
| `created_at` / `recorded_at` | `timestamptz` | Required, server-authored for normalized storage. |
| `updated_at` | `timestamptz` | Required only on mutable current-state records; optimistic concurrency applies. |
| `supersedes_id` | `uuid` | Nullable self-reference on append/supersede records; no in-place historical rewrite. |

Unless a stricter key is named below, ingestion uniqueness is
`(source_system, source_record_id, schema_version)`. A payload reusing that key with a different
integrity hash is rejected as an idempotency conflict.

### 3.2 Controlled vocabularies

The proposed first migration uses checked text for new controlled vocabularies. An existing compatible
Unreal OS enum may be reused only after later architecture discovery proves exact compatibility.
Arbitrary imported Phase 1 status values remain text, never enums. Values cannot be silently renamed
because Phase 1 projection depends on them.

- Account type: `brand`, `agency`.
- Evidence basis: `observed`, `inferred_high_confidence`, `inferred_low_confidence`, `unknown`,
  `requires_internal_rights_check`.
- Frozen duplicate status: `new_prospect`, `existing_no_new_trigger`, `existing_new_trigger`,
  `existing_active_outreach`, `existing_client`, `existing_partner`, `suppressed`,
  `possible_duplicate_needs_review`, `distinct_subbrand`, `parent_company_relationship`,
  `agency_brand_overlap`.
- Relationship type: `owns`, `subbrand_of`, `subsidiary_of`, `represents`, `agency_of_record_for`,
  `production_partner_for`, `sponsorship_partner_for`, `same_network_as`.
- Identity type: `domain`, `company_name`, `alias`, `public_social_handle`.
- Decision kind: `duplicate`, `rejection`, `qualification`, `next_action`, `rights`, `brand_safety`,
  `identity_review`, `account_state`, `future_handoff`.
- Account-state kind: `client_status`, `partner_status`; required only when `decision_kind` is
  `account_state` and prohibited for every other decision kind.
- Suppression target: `account`, `identity`, `contact`, `contact_point`.
- Cooldown scope: `account`, `campaign`, `business_unit`, `contact`, `contact_point`.

## 4. Relationship model

```text
os_prospecting_campaigns 1 ──< os_prospecting_runs
         │                         │
         │                         ├──< os_prospecting_discovery_events >── 1 os_prospecting_accounts
         │                         ├──< os_prospecting_evidence_refs
         │                         └──< os_prospecting_decisions
         │
os_prospecting_accounts 1 ──< os_prospecting_account_identities
         │
         ├──< os_prospecting_account_relationships >── 1 os_prospecting_accounts
         ├──< os_prospecting_contacts 1 ──< os_prospecting_contact_points
         ├──< os_prospecting_signals >── 1 os_prospecting_evidence_refs
         ├──< os_prospecting_score_snapshots
         ├──< os_prospecting_decisions
         ├──< os_prospecting_outreach_events
         ├──< os_prospecting_suppressions
         └──< os_prospecting_cooldowns

os_prospecting_outreach_events ── optional refs ──> os_approval_requests / os_action_log
normalized run/evidence records ─ optional reviewed packet ref ─> os_evidence_packets
all governed mutations ── audit refs ──> os_audit_events
```

## 5. Entity contracts

### 5.1 `os_prospecting_accounts`

**Purpose and grain:** one durable commercial organization identity: brand or agency. A subbrand is an
independent account when it has an independent public identity or opportunity; ownership is an edge,
not row nesting.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id` | `uuid` | required | Primary key. |
| `canonical_company_name` | `text` | required | Non-empty display value; not a globally unique identity. |
| `account_type` | `text` | required | `brand` or `agency`. |
| `lifecycle_status` | `text` | required / `prospect` | `prospect`, `inactive`, `review_required`; BU-specific client/partner state remains separate. |
| `identity_review_status` | `text` | required / `pending` | `pending`, `confirmed`, `ambiguous`, `rejected`. |
| `source_system`, `source_record_id`, `schema_version` | `text`, `text`, `integer` | required | Ingestion key. |
| `created_at`, `updated_at` | `timestamptz` | required | Server-authored. |

**Keys/indexes:** unique ingestion key; indexes on `lifecycle_status`, `account_type`, and
`identity_review_status`. Canonical name is searchable but deliberately not unique. No mutable JSON
object on this global row stores BU-scoped client, partner, or outreach state.

**Cardinality/lifecycle/source of truth:** one global account has many identities, relationships,
events, signals, scores, decisions, contacts, suppressions, and cooldowns across authorized business
units. The row is mutable only for global identity/lifecycle review state; BU-scoped client, partner,
and outreach state exists exclusively in append-only decisions/events and authorized deterministic
projections. Authorized humans own lifecycle corrections; the ingestion service may create `pending`
rows but may not confirm ambiguous identity or protected BU state. Every material change is
action/audit logged.

**Prohibited:** contact points, message bodies, private enrichment, secrets, credentials, sensitive
traits, unsupported legal names, or embedded evidence bodies.

**Future Supabase note:** accounts are global identities; RLS derives BU visibility from authorized
campaign/run/history associations and never duplicates the account merely to scope a BU. Account merge
is a later governed workflow that preserves aliases, child history, and audit; no merge API is defined.

### 5.2 `os_prospecting_account_identities`

**Purpose and grain:** one normalized public identity claim for one account. Domains, names, aliases,
and public social handles are separate rows so collisions are explicit.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `account_id` | `uuid`, `uuid` | required | PK; FK to accounts. |
| `identity_type` | `text` | required | Controlled vocabulary. |
| `normalized_value` | `text` | required | Normalized domain/name/handle; non-empty. |
| `display_value` | `text` | required | Public presentation value. |
| `platform` | `text` | nullable | Required for a social handle. |
| `is_canonical` | `boolean` | required / `false` | At most one active canonical domain and company name per account/type. |
| `collision_status` | `text` | required / `unreviewed` | `unreviewed`, `unique`, `ambiguous`, `resolved`. |
| `evidence_ref_id` | `uuid` | nullable | FK to evidence reference supporting the identity. |
| `valid_from`, `valid_to` | `timestamptz` | required / nullable | Effective-dated; `valid_to > valid_from`. |
| provenance/common fields | mixed | required | Ingestion and audit lineage. |

**Keys/indexes:** unique active claim on `(identity_type, platform, normalized_value, account_id)`;
collision lookup on `(identity_type, platform, normalized_value)`, plus `(account_id, is_canonical)`.
An identity claimed by more than one active account is not auto-assigned: all implicated rows become
`ambiguous` and qualification stops.

**Lifecycle/actors/audit:** effective-dated and superseded, never silently moved between accounts.
Ingestion may propose claims; authorized humans resolve collisions. Resolution records a decision,
action log, and audit event.

**Prohibited:** personal handles, private profiles, authentication identifiers, cookies, tokens,
tracking IDs, or values obtained from paid/private enrichment.

**Future Supabase note:** collision detection must occur transactionally under normalized-value locks
or an equivalent serialization strategy.

### 5.3 `os_prospecting_account_relationships`

**Purpose and grain:** one typed, directed, effective-dated relationship from one account to another.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `from_account_id`, `to_account_id` | `uuid` | required | PK and account FKs; endpoints differ. |
| `relationship_type` | `text` | required | Controlled directed edge type. |
| `basis` | `text` | required | Observation/inference vocabulary. |
| `evidence_ref_id` | `uuid` | nullable | Required for confirmed observed edges. |
| `review_status` | `text` | required / `pending` | `pending`, `confirmed`, `ambiguous`, `rejected`. |
| `valid_from`, `valid_to` | `timestamptz` | required / nullable | Effective-dated. |
| `notes_redacted` | `text` | nullable | Short rationale; no private data. |
| provenance/common fields | mixed | required | Ingestion and audit lineage. |

**Keys/indexes:** unique active edge on `(from_account_id, to_account_id, relationship_type,
valid_from)`; indexes in both directions and on `(relationship_type, review_status)`. Self-edges fail.

**Cardinality/lifecycle/source:** many-to-many. Edges append/supersede. Original public evidence plus
human review is authoritative; a model inference cannot become confirmed by repetition. Brand/agency
overlap is retained as a decision, not flattened into a single lead.

**Protection precedence:** an ownership/subbrand edge never weakens suppression, client, partner, or
active-outreach protection on either implicated account.

**Prohibited:** unverified ownership presented as fact, private contractual details, secrets, or
relationship conclusions without basis and review state.

**Ownership/actors/audit:** ingestion proposes; authorized humans confirm/supersede; the original
public evidence plus recorded review is source of truth. Every confirmation/supersession is audited.

**Future Supabase note:** enforce directed endpoints, effective dates, no self-edge, and reviewed-edge
visibility with database constraints/RLS; cycle checks require a reviewed transactional strategy.

### 5.4 `os_prospecting_campaigns`

**Purpose and grain:** one immutable version of a prospecting campaign configuration. Editing a
campaign creates the next `version` under the same `campaign_family_id`.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `campaign_family_id` | `uuid` | required | PK; stable family ID. |
| `version` | `integer` | required | Positive; unique per family. |
| `business_unit`, `campaign_name`, `discovery_scope` | `text` | required | Phase 1 vocabularies. |
| `verticals`, `buyer_types`, `talent_categories`, `rights_territory` | `text[]` | required / empty | Deduplicated arrays. |
| `geography` | `jsonb` | required / `{}` | Only countries, regions, cities, languages arrays. |
| `target_prospect_count`, `deep_research_limit` | `integer` | required | Phase 1 ranges. |
| `minimum_qualification_score` | `numeric(5,2)` | required | 0–100. |
| `required_signals`, `preferred_signals`, `excluded_categories` | `text[]` | required / empty | Ordered as ingested for replay. |
| `include_companies`, `exclude_companies` | `text[]` | required / empty | Inputs only; not identity authority. |
| `reengagement_enabled` | `boolean` | required | No default across versions. |
| `cooldown_days`, `maximum_evidence_age_days` | `integer` | required | Phase 1 ranges. |
| `output_formats`, `campaign_channels` | `text[]` | required / empty | Checked formats; channels are descriptive only. |
| `prospect_history_artifact_ref` | `text` | required | Replaces local path at ingestion; no host path exposed to ordinary readers. |
| `approved_roster_artifact_ref` | `text` | nullable | Controlled internal reference, never roster contents. |
| `allow_named_talent_recommendations` | `boolean` | required / `false` | Cannot authorize rights by itself. |
| `configuration_hash` | `text` | required | Integrity hash of canonical Phase 1 campaign JSON. |
| provenance/common fields | mixed | required | Includes creator actor reference and timestamps. |

**Keys/indexes:** unique `(campaign_family_id, version)` and `(source_system, source_record_id,
schema_version)`; indexes on `(business_unit, created_at desc)` and campaign name search.

**Lifecycle/actors/audit:** immutable after first run references the version. Humans create/retire
versions; ingestion may only bind an existing exact version or propose a new one. The canonical
configuration artifact/hash is source of truth. Changes are audited.

**Prohibited:** credentials, real roster content, personal contact data, local secret-bearing paths,
or any flag granting creative/outreach authority.

**Future Supabase note:** enforce family/version uniqueness and immutability once referenced; expose
artifact/roster refs only through restricted RLS-safe views.

### 5.5 `os_prospecting_runs`

**Purpose and grain:** one accepted Phase 1 run artifact and normalized ingestion outcome bound to
exactly one campaign version.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `campaign_id` | `uuid` | required | PK; FK to immutable campaign version. |
| `business_unit` | `text` | required | Must equal the referenced campaign version. |
| `source_run_id` | `text` | required | Phase 1 run ID; unique per source system. |
| `started_at`, `completed_at` | `timestamptz` | required | Completion not before start. |
| `skill`, `source_phase` | `text`, `integer` | required | Source phase remains `1` for this contract. |
| `history_loaded` | `boolean` | required | Must be `true`; otherwise reject ingestion. |
| `search_assumptions`, `limitations`, `validation_errors` | `text[]` | required / empty | Immutable run-level findings. |
| `summary` | `jsonb` | required | Exact six non-negative Phase 1 summary counters. |
| `future_creative_handoff_readiness` | `text` | required | Snapshot only; grants no approval. |
| `artifact_ref` | `text` | required | Immutable object/repo artifact locator. |
| `artifact_media_type` | `text` | required | `application/json`. |
| `artifact_schema_id`, `artifact_schema_version` | `text`, `integer` | required | Exact validating Phase 1 schema. |
| `artifact_sha256`, `artifact_byte_length` | `text`, `bigint` | required | Lowercase SHA-256; positive byte count. |
| `artifact_classification`, `artifact_integrity_verified` | `text`, `boolean` | required | Reviewed classification; verification must be true before normalization. |
| `history_artifact_ref` | `text` | required | Opaque locator for the exact Phase 1 history input accepted with this run. |
| `history_artifact_media_type` | `text` | required | `application/json`. |
| `history_artifact_schema_id`, `history_artifact_schema_version` | `text`, `integer` | required | Exact `prospect-history` schema identity/version. |
| `history_artifact_sha256`, `history_artifact_byte_length` | `text`, `bigint` | required | Integrity metadata for artifact-backed compatibility fields. |
| `history_artifact_classification`, `history_integrity_verified` | `text`, `boolean` | required | Reviewed classification; verification must be true. |
| `history_generated_at` | `timestamptz` | required | Exact validated `history.generated_at`; observation time for imported state. |
| `reviewed_evidence_packet_id` | `uuid` | nullable | Optional FK to shared `os_evidence_packets`. |
| provenance/common fields | mixed | required | Ingestion key and recorded time. |

**Keys/indexes:** unique `(source_system, source_run_id)`; unique artifact hash within source system;
indexes on `(campaign_id, started_at desc)` and `(business_unit, completed_at desc)`.

**Lifecycle/actors/audit:** append-only. Ingestion creates one row transactionally with children; a
duplicate identical import is a no-op/duplicate result, while changed bytes under the same source run
ID fail. Workers may ingest only through the future ingestion boundary. Humans may annotate review,
not rewrite run facts. The integrity-verified artifact is replay source of truth; normalized rows are
query source of truth. Ingestion outcome and later review are audited.

**Prohibited:** embedded artifact bytes, credentials, cookies, page bodies, private datasets, raw
message bodies, or a claim that the run executed outreach/creative.

**Future Supabase note:** insert the run and all children in one transaction under a serialized source
run idempotency check; artifact bytes remain outside ordinary tables and RLS views. Rejected,
duplicate, and rolled-back attempts are safe audit/service outcomes, not misleading persisted run rows.

### 5.6 `os_prospecting_discovery_events`

**Purpose and grain:** one account encountered in one run, including raw-candidate and evaluated-result
states without pretending discovery equals qualification.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `run_id`, `account_id` | `uuid` | required | PK and FKs. |
| `discovered_at` | `timestamptz` | required | Source event time. |
| `campaign_name_snapshot` | `text` | required | Phase 1 compatibility snapshot. |
| `raw_company_name`, `raw_domain` | `text` | nullable | Required together for raw candidate rows. |
| `evaluation_state` | `text` | required | `raw`, `evaluated`, `rejected_before_evaluation`. |
| `source_url_count` | `integer` | required / `0` | Derived; non-negative. |
| provenance/common fields | mixed | required | Unique source record within run. |

**Keys/indexes:** unique `(run_id, source_record_id)`; `(account_id, discovered_at desc)` and
`(run_id, evaluation_state)`. Many events may point to one account; one run may contain many events.

**Lifecycle/source:** append-only run fact. The immutable artifact is replay authority; normalized
event rows are query authority. Ambiguous account resolution rejects the transaction rather than
attaching the event arbitrarily.

**Ownership/actors/audit:** only the ingestion boundary inserts; humans may add a superseding decision,
not edit an event. Each accepted/failed ingestion is action/audit logged.

**Prohibited:** full scraped content, private browsing data, credentials, or inferred qualification
stored as discovery fact.

**Future Supabase note:** enforce append-only grants and run/account FKs; raw candidate columns are
excluded from viewer projections.

### 5.7 `os_prospecting_evidence_refs`

**Purpose and grain:** one credential-free reference to a public source observation, or one immutable
run artifact reference. It stores lineage, not copied page content.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `run_id` | `uuid` | required | PK; run FK. |
| `account_id`, `discovery_event_id` | `uuid` | nullable | Account/event FKs when applicable. |
| `source_url` | `text` | nullable | Public HTTP(S) URL; absent only for immutable artifact refs. |
| `source_date` | `date` | nullable | Required for dated signal evidence. |
| `observed_at` | `timestamptz` | required | When the source was observed. |
| `official_source` | `boolean` | required / `false` | Observation about source ownership. |
| `basis` | `text` | required | Evidence-basis vocabulary. |
| `summary_redacted` | `text` | nullable | Short evidence summary, not a page body. |
| `freshness_days_at_run` | `integer` | nullable | Derived, non-negative. |
| `integrity_sha256` | `text` | nullable | Required for immutable artifacts; optional for URL observations. |
| `artifact_ref` | `text` | nullable | Required when `source_url` is absent. |
| `reviewed_evidence_packet_id` | `uuid` | nullable | Optional shared governance packet FK. |
| provenance/common fields | mixed | required | Ingestion identity. |

**Keys/indexes:** unique `(run_id, source_url, source_date, basis)` for URL evidence; unique
`(source_system, source_record_id, schema_version)`; indexes on account/date and artifact hash.

**Lifecycle/actors/audit:** append-only. Source disappearance does not erase the historical reference;
freshness is evaluated for each run. Ingestion writes validated references; reviewers may supersede a
classification but not edit the original observation. The public source/artifact plus recorded
integrity metadata is source of truth. Inserts/supersessions are audited.

**Prohibited:** page bodies, screenshots by default, search cookies, auth headers, session data,
credentials, private datasets, paid-enrichment payloads, personal contact data, or sensitive traits.

**Future Supabase note:** constrain HTTP(S), artifact-reference exclusivity, and source-date rules;
restrict artifact locators and summaries through RLS-safe views.

### 5.8 `os_prospecting_signals`

**Purpose and grain:** one typed account signal asserted in one run and supported by one evidence ref.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `run_id`, `account_id`, `evidence_ref_id` | `uuid` | required | PK and FKs. |
| `signal_type`, `summary` | `text` | required | Non-empty; summary is bounded and source-backed. |
| `source_date` | `date` | required | Must match evidence date. |
| `basis` | `text` | required | Controlled observation/inference label. |
| `official_source` | `boolean` | required | Must match evidence classification. |
| `freshness_status` | `text` | required | `current`, `stale`, `future_dated`, `unknown`. |
| provenance/common fields | mixed | required | Run/source identity. |

**Keys/indexes:** unique `(run_id, account_id, source_record_id)`; indexes on
`(account_id, source_date desc)`, `(signal_type, source_date desc)`, and freshness. One evidence ref may
support multiple explicitly distinct signals; a signal has one primary evidence ref.

**Lifecycle/source:** immutable run assertion. The referenced public source is evidence authority; the
basis label expresses inference. Corrections supersede rather than mutate.

**Ownership/actors/audit:** ingestion inserts validated signals; authorized reviewers supersede. Each
insert/supersession records redacted action/audit lineage.

**Prohibited:** unsupported claims, copied page bodies, secrets, personal data, or private enrichment.

**Future Supabase note:** enforce evidence/run/account consistency and append-only grants; index
freshness without treating it as qualification authority.

### 5.9 `os_prospecting_score_snapshots`

**Purpose and grain:** one immutable account score under one rubric version in one run.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `run_id`, `account_id` | `uuid` | required | PK and FKs. |
| `rubric_name`, `rubric_version` | `text`, `integer` | required | BU-specific named rubric; positive version. |
| `total` | `numeric(5,2)` | required | 0–100. |
| `dimensions` | `jsonb` | required | Object of named numeric values, each 0–5. |
| `calculation_hash` | `text` | required | Integrity hash of rubric/version/dimensions/total. |
| `supersedes_id` | `uuid` | nullable | Prior correction target; self-FK. |
| provenance/common fields | mixed | required | Append-only lineage. |

**Keys/indexes:** unique `(run_id, account_id, rubric_name, rubric_version, source_record_id)`; indexes
on `(business_unit, total desc)`, account time, and rubric/version.

**Lifecycle/actors/audit:** append-only. Ingestion writes Phase 1 snapshots. A later human override is a
new explicitly sourced snapshot, never silent editing. Rubric/version/dimensions are source of truth
for the total. Every insert/override is audited. Score is prioritization evidence, not approval.

**Prohibited:** protected/sensitive traits, opaque unversioned scores, or score values detached from
dimensions and rubric.

**Future Supabase note:** validate dimension ranges and calculation hash server-side; grant insert only
to ingestion and the governed human-override path.

### 5.10 `os_prospecting_decisions`

**Purpose and grain:** one durable prospecting decision or decision component for one account/run.
Duplicate, rejection, qualification, rights, safety, next-action, uncertainty, and handoff state remain
inspectable and supersedable.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `account_id` | `uuid` | required | PK and account FK. |
| `run_id` | `uuid` | nullable / conditional | Required for result-derived decisions; null for imported history observations and governed runless corrections. |
| `business_unit` | `text` | required | Explicit BU scope; never inferred from a JSON object key. |
| `decision_kind` | `text` | required | Controlled vocabulary. |
| `account_state_kind` | `text` | nullable | Required as `client_status` or `partner_status` iff `decision_kind = account_state`; otherwise null. |
| `status` | `text` | nullable / conditional | Required only for `duplicate`, `account_state`, and governed `identity_review`; exact source value under the materialization matrix. |
| `effective_at` | `timestamptz` | nullable / conditional | Required for every imported or governed current-state row and every run-derived decision; exact source is defined by kind below. |
| `reason` | `text` | nullable / conditional | Required for `duplicate`, governed `identity_review`, and human-authored corrections; otherwise null unless the matrix names an exact source. |
| `rejected` | `boolean` | nullable | Required for rejection kind. |
| `reasons` | `text[]` | nullable / conditional | Required as the exact array for `rejection`; otherwise null. |
| `matched_account_id` | `uuid` | nullable | Resolved Phase 1 matched prospect. |
| `matched_account_ids` | `uuid[]` | nullable / conditional | Duplicate-kind resolved matches; deduplicated. |
| `matched_source_prospect_ids` | `text[]` | nullable / conditional | Duplicate-kind lossless Phase 1 IDs for replay. |
| `reengagement` | `boolean` | nullable / conditional | Duplicate kind only; defaults false there and may be true only for `existing_new_trigger`. |
| `qualification_reason`, `important_uncertainty`, `recommended_next_action` | `text` | nullable | Phase 1 durable fields. |
| `rights_territory` | `text[]` | nullable / conditional | Rights-kind exact snapshot; empty only when Phase 1 permits it. |
| `brand_safety_flags` | `text[]` | nullable / conditional | Brand-safety-kind exact snapshot; empty array is meaningful. |
| `talent_recommendation_type` | `text` | nullable | `none`, `archetype_only`, `approved_roster`. |
| `talent_archetype`, `named_talent`, `rights_status` | `text` | nullable | Named talent requires authorized roster snapshot. |
| `approved_roster_authorization` | `boolean` | nullable / conditional | Rights kind only; Phase 1 default false when absent. Not an Unreal OS approval. |
| `recommended_buyer_path` | `text` | nullable | Phase 1 vocabulary. |
| `handoff_ready`, `human_approval_required_before_generation` | `boolean` | nullable / conditional | Required only for `future_handoff`; readiness cannot grant generation. |
| `supersedes_id`, `decided_by_user_id` | `uuid` | nullable | Self-FK and optional `os_users` FK. |
| provenance/common fields | mixed | required | Append-only lineage. |

**Keys/indexes:** run-derived uniqueness is `(run_id, account_id, business_unit, decision_kind,
coalesce(account_state_kind, 'not_account_state'), source_record_id)`. The decision kind and state-kind
partition prevent duplicate, rejection, qualification, next-action, rights, brand-safety, identity,
handoff, client-state, and partner-state components from collapsing. Runless corrections use the
common non-null `(source_system, source_record_id,
schema_version)` ingestion key, and `supersedes_id` is unique when present so correction chains cannot
fork. These rules keep client and partner state from colliding. Indexes cover frozen status,
`(account_id, recorded_at desc)`, rejected state, re-engagement, handoff readiness, and the partial
current-state order `(account_id, business_unit, account_state_kind, effective_at desc, recorded_at
desc, id desc)` where `decision_kind = account_state`.

**Lifecycle/source:** append-only/superseded. Phase 1 artifact is source for imported decisions;
authorized human review is source for later corrections. A valid runless human correction has
`run_id = null`, `source_system = human_review`, a stable unique `source_record_id`, explicit
`business_unit`, `account_state_kind`, `effective_at`, non-null `decided_by_user_id`, bounded reason,
required audit/action references, and `supersedes_id` naming the current leaf for the same account, BU,
and state kind. Its `effective_at` cannot precede the row it supersedes. Any override records who, why,
evidence, and the superseded decision. Ambiguous matches use `possible_duplicate_needs_review`, block
qualification, and cannot be force-mapped by ingestion.

For each `(account_id, business_unit, account_state_kind)` and as-of time, the authorized current-state
projection considers valid rows with `effective_at` and `recorded_at` at or before the as-of boundary,
retains superseded rows as history, and selects the greatest tuple `(effective_at, recorded_at, id)`.
The UUID `id` is the final stable ascending tie-breaker. A later-recorded import with an older
`effective_at` therefore cannot overwrite newer state. Different immutable history sources append
chronological observations without `supersedes_id`; their greatest tuple becomes current. Reuse of a
source key with identical content is a no-op, while changed content is an idempotency conflict.
`supersedes_id` is mandatory only for a governed runless human correction; that correction must target
the current leaf for the same account, BU, and state kind and cannot fork the chain.

For an imported Phase 1 account-state observation specifically, `business_unit` is copied from the
validated campaign, `account_state_kind` is selected only by the source field (`client_status` or
`partner_status`), `status` is the exact Phase 1 string, `effective_at = history.generated_at`,
`recorded_at` is server-authored, and `id` is the stable final tie-breaker. No imported observation
uses `supersedes_id`. The current imported value is therefore exactly the greatest
`(effective_at, recorded_at, id)` tuple, so an older effective observation recorded later cannot win.

**Audit:** decision insert/supersession links redacted `os_action_log` and `os_audit_events`. A future
approval for deeper work is a separate `os_approval_requests` record.

**Prohibited:** self-approval, implicit rights clearance, invented roster availability, unsupported
legal conclusions, secrets, private data, or deletion of rejected/duplicate decisions.

**Future Supabase note:** append-only RLS, exact frozen-status checks, supersession FKs, and protected
rights/roster columns are required; deeper-work approval remains in `os_approval_requests`.

#### 5.10.1 Decision-kind materialization matrix

For a run-derived result, `source_record_id` is the accepted run source ID plus the zero-based result
ordinal and decision kind. `run_id` is required, `business_unit` is the exact validated
`results[i].business_unit` and must equal the campaign/run BU, `effective_at` is the accepted
`run_metadata.completed_at`, and `recorded_at` is server-authored. Every row also requires the common
source/schema/audit fields. Imported rows have null `decided_by_user_id` and `supersedes_id`. Fields not
listed for a kind are prohibited as non-null values; required-empty arrays and documented boolean
defaults are the only defaults.

| Decision kind/component | Exact Phase 1 source and rows emitted | Required destination fields | Nullable/defaulted/prohibited fields | BU, idempotency, supersession, and rejection behavior |
| --- | --- | --- | --- | --- |
| `duplicate` | One row per `results[i]` from `duplicate_decision.status`, `.reason`, `.matched_prospect_id`, `.matched_prospect_ids[]`, and `.reengagement`. | `status` and `reason` are exact; resolved matched account/source IDs; `effective_at = run_metadata.completed_at`. | `matched_account_id` nullable; matched arrays default to the exact supplied array or the documented singleton/empty derivation; `reengagement` defaults false. Rejection/talent/handoff fields prohibited. | Result BU. Key: run + account + BU + `duplicate` + result source ID. Imported row never supersedes. Missing/invalid status or reason, unresolved required match, or contradictory re-engagement rejects the run. |
| `rejection` | One row per `results[i]` from `rejection_decision.rejected` and `.reasons[]`. | `rejected`, exact `reasons[]`, and run completion `effective_at`. | `status` and `reason` null; unrelated fields prohibited. The array remains empty only when `rejected = false`. | Result BU. Key uses `rejection`. Imported row never supersedes. Missing fields, rejected-without-reasons, or non-rejected-with-reasons rejects the run. |
| `qualification` and uncertainty | One row per `results[i]` from `reason_for_qualification` and `important_uncertainty`. | Exact `qualification_reason`, exact `important_uncertainty`, and run completion `effective_at`. | `status` and `reason` null; all duplicate, rejection, rights, action, and handoff fields prohibited. | Result BU. Key uses `qualification`. Imported row never supersedes. Missing or blank source strings reject the run; no rationale is invented from score or signals. |
| `next_action` and buyer path | One row per `results[i]` from `recommended_next_action` and, when present, `recommended_buyer_path`. | Exact `recommended_next_action` and run completion `effective_at`; Talent requires exact buyer path under Phase 1 validation. | `recommended_buyer_path` null for UMG when absent; `status` and `reason` null; other component fields prohibited. | Result BU. Key uses `next_action`. Imported row never supersedes. Missing next action, or missing/invalid Talent buyer path, rejects the run. |
| `rights` plus roster/talent state | One row for every Talent result; for UMG, one only if any rights/talent field is present. Sources are `rights_territory[]`, `talent_recommendation_type`, `talent_archetype`, `named_talent`, `approved_roster_authorization`, and `rights_status`. | Every present value is copied exactly; accepted Talent rows require territory, recommendation type, authorization boolean, rights status, and run completion `effective_at`. | Schema-defined absent UMG values remain null/empty/false. `status`, `reason`, buyer path, brand safety, and handoff fields prohibited. | Result BU. Key uses `rights`. Imported row never supersedes. Invalid roster authorization, named-talent, territory, or rights state rejects the run rather than manufacturing clearance. |
| `brand_safety` | One row for every Talent result from exact `brand_safety_flags[]`; for UMG, one only if the field is present. | Exact flags array and run completion `effective_at`. | Empty array is preserved; `status`, `reason`, rights/roster, action, and handoff fields prohibited. | Result BU. Key uses `brand_safety`. Imported row never supersedes. Non-array or unresolved material contradictions reject readiness/run under Phase 1 policy. |
| `identity_review` | Phase 1 emits zero independent rows because it has no identity-review actor, resolution, or effective-time field. `possible_duplicate_needs_review` remains on the duplicate row and sets the account/identity review path to fail closed. A later governed human review may emit one row from its explicit review form. | Human row requires exact review `status`, `reason`, `effective_at`, actor, evidence/action/audit references, and target identity/account. | All result-only decision fields prohibited. | Explicit reviewed BU scope. Human source key is unique and any correction names the same-scope prior review with `supersedes_id`. Missing actor/evidence or ambiguous target rejects; ingestion never fabricates a resolution. |
| `account_state` | Phase 1 history emits exactly two rows per prospect: `.client_status` as `client_status` and `.partner_status` as `partner_status`. `status` is the exact string; `effective_at = history.generated_at`. No result row is emitted. | Explicit account, campaign BU, state kind, exact status, history effective time, artifact/source lineage, and server `recorded_at`. | `run_id`, `reason`, decision/talent/handoff fields, and `supersedes_id` are null for imported observations. Imported values have no per-value length cap beyond the validated whole-artifact limit. | Key: history artifact hash + prospect ID + BU + state kind. Chronological imports do not supersede. Identical key/content is a no-op; changed content conflicts. A human correction requires same account/BU/kind, actor, reason, supplied effective time, and unique `supersedes_id`; future human-authored status is limited to 512 UTF-8 bytes. |
| `future_handoff` | One row per `results[i]` from `future_handoff.ready` and `.human_approval_required_before_generation`. | Exact `handoff_ready`, exact required-true approval flag, and run completion `effective_at`. | `status` and `reason` null; all other component fields prohibited. | Result BU. Key uses `future_handoff`. Imported row never supersedes. Missing values, false approval-required flag, or ready state contradicting rejection/protection rejects the run. |

This matrix is exhaustive for Phase 1 result/history decisions. It deliberately binds talent/roster
state to `rights` and handoff state to the controlled `future_handoff` kind. It never manufactures a
generic status, reason, timestamp, campaign, rubric, evidence item, or human decision to make a row fit.

### 5.11 `os_prospecting_contacts`

**Purpose and grain:** one publicly presented business person associated with an account. An account
can exist and qualify without a contact.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `account_id` | `uuid` | required | PK and account FK. |
| `display_name` | `text` | required | Public professional name; role-scoped access. |
| `business_title`, `department` | `text` | nullable | Public professional context only. |
| `public_profile_url` | `text` | nullable | Public HTTP(S), no authenticated/private URL. |
| `provenance_evidence_ref_id` | `uuid` | required | Evidence FK. |
| `classification` | `text` | required | `public_business_contact`; later classifications require separate review. |
| `visibility` | `text` | required / `restricted` | `restricted`, `noah_rob_dan`, `assigned_team`. |
| `review_status` | `text` | required / `pending` | `pending`, `confirmed`, `stale`, `rejected`. |
| `valid_from`, `valid_to` | `timestamptz` | required / nullable | Effective-dated. |
| provenance/common fields | mixed | required | Lineage and review. |

**Keys/indexes:** no global unique name. Unique source record; indexes on account, review state, and
restricted visibility. Contact identity ambiguity fails closed and never merges on name alone.

**Lifecycle/actors/audit:** mutable review metadata plus effective-dated/superseded identity. Ingestion
may propose only from intentionally public business sources; humans confirm. Access and changes are
audited without emitting contact values into general audit events. Public provenance plus human review
is source of truth.

**Prohibited:** private emails/phones, home details, scraped private profiles, sensitive traits,
personal social accounts, paid enrichment, relationship inference, credentials, or contact data in
viewer-accessible projections.

**Future Supabase note:** direct SELECT is restricted to authorized human roles; field-level protection,
retention, access auditing, and safe views must be approved before real contact data exists.

### 5.12 `os_prospecting_contact_points`

**Purpose and grain:** one public business contact point for one contact. A business email, business
phone, professional profile, or business social handle has its own provenance, validity, suppression,
and visibility. Keeping points separate prevents a contact edit from erasing do-not-contact history
and avoids duplicating a person row per channel.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `contact_id` | `uuid` | required | PK and contact FK. |
| `point_type` | `text` | required | `business_email`, `business_phone`, `professional_profile`, `business_social`. |
| `normalized_value`, `display_value` | `text` | required | Encrypted/field-protected in a future implementation; never in general logs. |
| `provenance_evidence_ref_id` | `uuid` | required | Public source evidence. |
| `classification`, `visibility`, `review_status` | `text` | required | Same strict contact access model. |
| `is_primary` | `boolean` | required / `false` | At most one active primary point per type/contact. |
| `valid_from`, `valid_to` | `timestamptz` | required / nullable | Effective-dated. |
| provenance/common fields | mixed | required | Lineage. |

**Keys/indexes:** source uniqueness; restricted lookup on a keyed digest of normalized value for
dedup/suppression checks, never a broadly readable plaintext index. Index contact/type/review state.

**Lifecycle/actors/audit:** effective-dated and superseded. Suppression remains in its own table after a
point expires. Only authorized human roles and the narrow ingestion service may access values.
Public source provenance plus authorized review is source of truth; access/change audit never includes
the value.

**Prohibited:** private/personal points, guessed patterns, paid enrichment, sensitive traits,
credentials, values in audit logs, or viewer access.

**Future Supabase note:** lookup requires a versioned keyed digest such as HMAC over the canonicalized
value. Unsalted hashes, repository-stored keys, plaintext lookup indexes, and worker/viewer digest
exposure are prohibited. Concrete encryption and key-provider selection remains a later security gate.

### 5.13 `os_prospecting_outreach_events`

**Purpose and grain:** one append-only historical/proposed outreach state transition. It supports
dedup history but creates no send path.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id`, `account_id` | `uuid` | required | PK and account FK. |
| `business_unit` | `text` | required | Explicit BU scope for every event. |
| `contact_id`, `contact_point_id` | `uuid` | nullable | Restricted FKs when known. |
| `campaign_id`, `run_id` | `uuid` | nullable | Context FKs. |
| `event_type` | `text` | required | `imported_current_status`, `drafted`, `approval_requested`, `approved`, `sent`, `replied`, `bounced`, `unsubscribed`, `held`, `cancelled`. |
| `status_value` | `text` | nullable | Required only for `imported_current_status`; exact untrimmed/untruncated Phase 1 `outreach_status`. Null for factual events. |
| `channel` | `text` | required | Descriptive channel. |
| `occurred_at` | `timestamptz` | required | Event time. |
| `external_event_ref` | `text` | nullable | Opaque provider/reference ID, never credential. |
| `content_artifact_ref` | `text` | nullable | Optional governed artifact reference; message body absent by default. |
| `approval_request_id`, `action_log_id` | `uuid` | nullable | Shared governance FKs required for governed sent events. |
| `result` | `text` | required | Bounded status, no body. |
| `record_status` | `text` | required / `active` | `active`, `superseded`, `entered_in_error`; prior rows are retained. |
| provenance/common fields | mixed | required | Append-only lineage. |

**Keys/indexes:** unique `(source_system, source_record_id, schema_version)` source event and unique
`supersedes_id` when present; indexes on `(account_id,
business_unit, occurred_at desc, recorded_at desc, id desc)`, contact point/time, event type, and
approval ref. Identical source reimport is a no-op; any changed value under the same source key fails.

**Lifecycle/source:** append-only; an erroneous event is corrected by a compensating/superseding event
for the same account and BU. A Phase 1 history snapshot is imported only as
`event_type = imported_current_status`, with `business_unit` from the authorized history scope,
`status_value` copied exactly after whole-artifact validation, `occurred_at` set to the history
artifact's `generated_at`, `channel = phase1_history`, `result = snapshot_imported`, null
contact/action/approval references, and stable artifact/prospect source lineage. This controlled
snapshot event is distinct from `sent`, `replied`, and other historical facts;
those factual events require `status_value = null`. External provider history is source when separately
authorized/imported; this contract alone cannot connect to it. Imported status values have no
per-value length limit because the frozen Phase 1 schema has none; ingestion safety comes from the
reviewed whole-artifact byte limit. Raw status values are excluded from general logs, error payloads,
viewer views, and any worker view outside its BU. Workers cannot create `sent` without a valid
action/approval reference in the later execution phase.

For each `(account_id, business_unit)` and as-of time, current outreach state is deterministic. Consider
state-bearing events whose `record_status = active` at or before the boundary and select the greatest tuple
`(occurred_at, recorded_at, id)`. For `imported_current_status`, emit the exact `status_value`; for a
later factual state event, emit its controlled `event_type`. The UUID `id` is the final stable ascending
tie-breaker. Superseded events remain queryable history, older imported snapshots never displace a
newer effective event, and no UMG event participates in a Talent projection or vice versa.

**Ownership/actors/audit:** ingestion may preserve validated historical events; a later gated executor
may append governed events. Every insert is audited by reference/result only.

**Prohibited:** message body by default, secrets, auth/provider tokens, private enrichment, or any
field granting autonomous send authority. No delete.

**Future Supabase note:** withhold UPDATE/DELETE universally and withhold `sent` INSERT until a later
approved executor exists; validate approval/action FKs for governed events.

#### BU-state reconstruction invariant

One global account may have six independent current values: UMG client, partner, and outreach state,
plus Talent client, partner, and outreach state. The client and partner values come from distinct
`account_state_kind` partitions in `os_prospecting_decisions`; outreach comes from the separately typed
state-bearing events above. Every partition includes explicit `business_unit`. The authorized projection
filters by the requested BU before ranking candidates and exposes only that BU's three values. It never
uses account-row JSON keys, joins an unscoped state row, or falls back to another BU. Missing state is
emitted as the Phase 1-compatible empty string only when the source contract permits it; another BU's
value is never used as a default. This is sufficient to reconstruct all six values without duplicating
the account or allowing one partition to overwrite or disclose another.

### 5.14 `os_prospecting_suppressions`

**Purpose and grain:** one effective-dated do-not-contact/prospecting restriction targeting an
account, identity, contact, or contact point. Suppression is policy state, not deletion.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id` | `uuid` | required | PK. |
| `target_type`, `target_id` | `text`, `uuid` | required | Exactly one valid typed target. |
| `business_unit` | `text` | nullable | Null means all business units. |
| `reason_code` | `text` | required | Controlled source/policy code; `phase1_history_flag` for an imported true flag. |
| `reason_redacted` | `text` | nullable / conditional | Exact Phase 1 reason or governed rationale; null is retained when imported Phase 1 provides none. |
| `source` | `text` | required | `phase1_history`, `outreach_event`, `human`, `policy`. |
| `effective_from`, `effective_until` | `timestamptz` | required / nullable | Null end means indefinite; end after start. |
| `review_status` | `text` | required / `active` | `active`, `superseded`, `entered_in_error`; never hard-deleted. |
| `supersedes_id`, `created_by_user_id` | `uuid` | nullable | Self-FK and `os_users` FK. |
| provenance/common fields | mixed | required | Append/supersede lineage. |

**Keys/indexes:** prevent duplicate active suppression for same target/scope/source/reason; indexes on
typed target, business unit/effective dates, and active indefinite rows.

**Lifecycle/actors/audit:** append/supersede only. Ingestion preserves Phase 1 suppression. Authorized
humans may add or supersede; workers may not deactivate. Every change is action/audit logged. Any
matching active suppression fails closed and blocks qualification/handoff/outreach regardless of
subbrand or re-engagement status. Effective append-only suppression rows are source of truth.

**Prohibited:** secret values, unnecessary private narrative, message bodies, silent deletion, or an
override flag that workers can set.

**Future Supabase note:** use typed-target validation, append-only RLS, restricted reason views, and a
transactional effective-suppression check shared by ingestion/projection and later executors.

### 5.15 `os_prospecting_cooldowns`

**Purpose and grain:** one temporary eligibility delay with explicit scope and origin. Cooldown is
separate from suppression because it expires and does not express a permanent do-not-contact rule.

| Field | Type | Required / default | Constraints |
| --- | --- | --- | --- |
| `id` | `uuid` | required | PK. |
| `scope_type`, `scope_id` | `text`, `uuid` | required | Typed target. |
| `business_unit` | `text` | nullable | Null means cross-BU. |
| `campaign_id` | `uuid` | nullable | Required for campaign scope. |
| `origin_type`, `origin_ref` | `text` | required | `phase1_history`, `campaign_rule`, `outreach_event`, `human`; stable reference. |
| `starts_at`, `ends_at` | `timestamptz` | required | End after start. |
| `reason_redacted` | `text` | nullable / conditional | Required for human/policy rows; null for Phase 1 rows that provide no reason. |
| `status` | `text` | required / `active` | `active`, `expired`, `superseded`, `entered_in_error`. |
| `supersedes_id`, `created_by_user_id` | `uuid` | nullable | Self and user FKs. |
| provenance/common fields | mixed | required | Append/supersede lineage. |

**Keys/indexes:** source idempotency; indexes on typed scope/end, business unit/end, and campaign/end.

**Lifecycle/actors/audit:** append/supersede. Expiry is time-derived; history is retained. A new trigger
does not bypass an active cooldown. Suppression is checked first and always wins. Workers may ingest or
calculate a campaign cooldown but may not shorten human/policy cooldowns. Effective append-only rows
and their recorded origin are source of truth; changes are audited.

**Prohibited:** secrets, contact values, silent date rewrites, or bypass flags.

**Future Supabase note:** enforce typed scope/origin and end-after-start checks; expose only applicable
effective dates to workers and never allow worker/service shortening of human/policy cooldowns.

## 6. Phase 1 field-level mapping matrix

### 6.1 Mapping rules

- `authoritative` means the normalized row owns future query state; `snapshot` preserves the exact
  Phase 1 assertion; `derived` is reproducible from authoritative rows. The immutable artifact remains
  authoritative for byte-exact replay.
- Optional/missing arrays become empty arrays only where Phase 1 semantics define absence as empty.
  Nullable semantic values remain null. Required missing values reject the whole ingestion.
- All result/account mappings first resolve identity. Zero or multiple confirmed accounts, conflicting
  parent/subbrand edges, or a normalized identity claimed by several accounts rejects the transaction
  as `ambiguous_identity`; it never guesses.

#### Campaign configuration

| Phase 1 JSON path | Destination | Transformation | Class | Missing/null rule | Idempotency key | Ambiguity rejection |
| --- | --- | --- | --- | --- | --- | --- |
| `campaign.business_unit` | campaigns.`business_unit` | exact enum | authoritative | required; reject | config hash | unsupported BU rejects |
| `campaign.campaign_name` | campaigns.`campaign_name` | trim only | authoritative | required; reject | family+version | same family/version with different name rejects |
| `campaign.discovery_scope` | campaigns.`discovery_scope` | exact enum | authoritative | required; reject | config hash | invalid enum rejects |
| `campaign.verticals` | campaigns.`verticals` | preserve ordered values; validate uniqueness | snapshot | missing → `[]` | config hash | conflicting non-array rejects |
| `campaign.geography` | campaigns.`geography` | retain allowed keys/arrays | snapshot | missing → `{}` | config hash | unknown keys reject |
| `campaign.buyer_types` | campaigns.`buyer_types` | exact enums | authoritative | missing → `[]` | config hash | invalid type rejects |
| `campaign.talent_categories` | campaigns.`talent_categories` | exact strings | snapshot | missing → `[]` | config hash | invalid array rejects |
| `campaign.rights_territory` | campaigns.`rights_territory` | exact strings | snapshot | missing → `[]` | config hash | contradiction with Talent rights state flags review |
| `campaign.target_prospect_count` | campaigns same field | integer | authoritative | required; reject | config hash | out-of-range rejects |
| `campaign.deep_research_limit` | campaigns same field | integer | authoritative | required; reject | config hash | out-of-range rejects |
| `campaign.minimum_qualification_score` | campaigns same field | numeric | authoritative | required; reject | config hash | out-of-range rejects |
| `campaign.required_signals` | campaigns same field | string array | snapshot | missing → `[]` | config hash | invalid array rejects |
| `campaign.preferred_signals` | campaigns same field | string array | snapshot | missing → `[]` | config hash | invalid array rejects |
| `campaign.excluded_categories` | campaigns same field | string array | snapshot | missing → `[]` | config hash | invalid array rejects |
| `campaign.include_companies` | campaigns same field | string array; no account resolution side effect | snapshot | missing → `[]` | config hash | conflicting include/exclude rejects validation |
| `campaign.exclude_companies` | campaigns same field | string array; no account resolution side effect | snapshot | missing → `[]` | config hash | conflicting include/exclude rejects validation |
| `campaign.reengagement_enabled` | campaigns same field | boolean | authoritative | required; reject | config hash | non-boolean rejects |
| `campaign.cooldown_days` | campaigns same field | integer | authoritative | required; reject | config hash | out-of-range rejects |
| `campaign.maximum_evidence_age_days` | campaigns same field | integer | authoritative | required; reject | config hash | out-of-range rejects |
| `campaign.output_formats` | campaigns same field | exact enums | snapshot | required/non-empty; reject | config hash | unsupported format rejects |
| `campaign.prospect_history_path` | campaigns.`prospect_history_artifact_ref` | resolve approved artifact; do not retain exposed local path | authoritative | required/unresolvable rejects | artifact hash | multiple artifacts reject |
| `campaign.approved_roster_path` | campaigns.`approved_roster_artifact_ref` | resolve controlled artifact reference | snapshot | missing/null → null | artifact hash | multiple/unauthorized refs reject |
| `campaign.allow_named_talent_recommendations` | campaigns same field | boolean | authoritative | missing → `false` | config hash | true without roster ref rejects |
| `campaign.campaign_channels` | campaigns same field | string array | snapshot | missing → `[]` | config hash | invalid array rejects |

#### Prospect history

| Phase 1 JSON path | Destination | Transformation | Class | Missing/null rule | Idempotency key | Ambiguity rejection |
| --- | --- | --- | --- | --- | --- | --- |
| `history.version` | runs.`history_artifact_schema_version` | exact integer | snapshot | required; reject unsupported | history artifact hash | version mismatch rejects |
| `history.generated_at` | runs.`history_generated_at` | exact timestamp | snapshot/authoritative observation time | required; reject | history artifact hash | invalid time rejects |
| `history.prospects[]` | verified history artifact plus optional resolved account link | preserve every object; bind only to one existing/resolved account, because history has no `account_type` and cannot construct an account alone | snapshot/conditional normalized | required array | history hash+prospect ID | zero/multi account match remains artifact-backed and fails normalized state projection |
| `.id` | artifact prospect source ID and child-row `source_record_id` after account binding | preserve exact string | snapshot | required; reject | history hash+prospect ID | reused ID with changed object conflicts |
| `.canonical_company_name` | artifact baseline; optional company-name identity after account binding | exact display plus normalized comparison value | snapshot/conditional normalized | required; reject | bound account+normalized name+history source | name alone never creates/merges an account |
| `.canonical_domain` | artifact baseline; optional canonical-domain identity after account binding | normalize public root domain while artifact preserves exact | snapshot/conditional normalized | required; reject | bound account+normalized domain | multi-account domain rejects binding |
| `.domains[]` | artifact baseline; optional domain identities after account binding | normalize/deduplicate for identity rows; preserve exact array in artifact | snapshot/conditional normalized | required; empty allowed | bound account+normalized domain+history source | cross-account collision rejects binding |
| `.alternate_names[]` | artifact baseline; optional alias identities after account binding | normalize/deduplicate; preserve exact array | snapshot/conditional normalized | required; empty allowed | bound account+normalized alias+history source | alias collision marks ambiguous |
| `.social_handles{}` | artifact baseline; optional public-social identities after account binding | platform key + normalized handle; preserve exact object | snapshot/conditional normalized | required; empty allowed | bound account+platform+handle+history source | cross-account collision rejects binding |
| `.parent_company` | artifact baseline; relationship row only when both endpoint accounts resolve | exact string; no parent account is created from name alone | snapshot/conditional normalized | missing/null → no edge | history hash+prospect+edge | unresolved/multiple endpoints remain artifact-backed |
| `.subsidiaries[]` | artifact baseline; relationship rows only for exactly resolved endpoints | exact ordered strings; no account type or evidence invented | snapshot/conditional normalized | missing → `[]` | history hash+prospect+edge ordinal | unresolved endpoint remains artifact-backed |
| `.subbrands[]` | artifact baseline; relationship rows only for exactly resolved endpoints | exact ordered strings; protection precedence retained | snapshot/conditional normalized | missing → `[]` | history hash+prospect+edge ordinal | unresolved endpoint remains artifact-backed |
| `.agency_relationships[]` | artifact baseline; relationship rows only for exactly resolved agency accounts | exact ordered strings; no contractual fact inferred | snapshot/conditional normalized | missing → `[]` | history hash+prospect+edge ordinal | unresolved/overlapping endpoint remains artifact-backed |
| `.previous_discovery_dates[]` | verified history artifact compatibility baseline | preserve exact ordered dates; no discovery row is emitted because run, campaign snapshot, and evaluation state are absent | snapshot | required; empty allowed | history artifact hash+prospect ID | artifact integrity/identity ambiguity rejects |
| `.previous_campaign_appearances[]` | verified history artifact compatibility baseline | preserve exact ordered strings; no campaign/run/decision is invented | snapshot | required; empty allowed | history artifact hash+prospect ID | same name is never treated as campaign identity |
| `.previous_scores[]` | verified history artifact compatibility baseline | preserve exact ordered totals; no score row is emitted without rubric, dimensions, run, and calculation hash | snapshot | required; empty allowed | history artifact hash+prospect ID | artifact conflict rejects |
| `.previous_decisions[]` | verified history artifact compatibility baseline | preserve exact ordered strings; no decision row is emitted without kind, reason, and effective source | snapshot | required; empty allowed | history artifact hash+prospect ID | values never grant eligibility |
| `.outreach_status` | outreach events.`status_value` | append `imported_current_status` with campaign BU, exact string, and `occurred_at = history.generated_at` | authoritative/derived | required; empty allowed; no per-value cap | history hash+prospect+BU+event kind | protected active status fails closed; cross-BU source rejects |
| `.client_status` | account-state decision.`status` | append `account_state`/`client_status` with campaign BU and `effective_at = history.generated_at` | authoritative/derived | required; empty allowed; no per-value cap | history hash+prospect+BU+state kind | changed source reuse conflicts; cross-BU source rejects |
| `.partner_status` | account-state decision.`status` | append `account_state`/`partner_status` with campaign BU and `effective_at = history.generated_at` | authoritative/derived | required; empty allowed; no per-value cap | history hash+prospect+BU+state kind | changed source reuse conflicts; cross-BU source rejects |
| `.suppressed` | suppressions | true emits a source-faithful Phase 1 suppression observation; false emits no row and never deletes another source | authoritative | required boolean | history hash+prospect+BU+suppression flag | contradictory source reuse rejects |
| `.suppression_reason` | suppressions.`reason_redacted` | preserve exact string when present; retain null when Phase 1 supplies null | snapshot | nullable; never synthesize a reason | suppression source key | false never removes another active reason |
| `.cooldown_until` | cooldowns.`ends_at` | inclusive date → exclusive next-day `00:00:00Z`; `starts_at = history.generated_at` | authoritative | missing/null → no row | history hash+prospect+BU+cooldown | earlier observation never shortens later cooldown |
| `.prior_signals[]` | verified history artifact compatibility baseline | preserve exact ordered objects; no signal/evidence row is emitted because Phase 1 legacy objects do not require type, summary, basis, official-source, or evidence fields | snapshot | required; empty allowed | history artifact hash+prospect ID | invalid artifact shape rejects; values are not current evidence |
| `.prior_rejection_reasons[]` | verified history artifact compatibility baseline | preserve exact ordered strings; no rejection decision is invented without rejected state, run, and effective source | snapshot | required; empty allowed | history artifact hash+prospect ID | invalid types reject |

##### Legacy history constructibility and compatibility baseline

The accepted run records the exact input history artifact locator, media type, schema ID/version,
SHA-256, byte length, and `history.generated_at`. The whole artifact is validated before any child row
is emitted. For each normalized legacy child, common required fields are sourced—not invented—as
follows: `account_id` comes from one exact resolved account; `business_unit` comes from the validated
campaign; `schema_version` comes from `history.version`; `source_system = phase1_history` is a
provenance label; `source_record_id` is the history hash, prospect ID, field path, and ordinal;
`recorded_at` is server-authored; and the immutable history artifact reference is retained. If an
exact account or required target cannot be resolved, the value remains only in the verified artifact
baseline and no partial normalized row is emitted.

| Legacy field | Materialization ruling | Exact normalized requirements or artifact retrieval rule |
| --- | --- | --- |
| `previous_discovery_dates[]` | Artifact-backed baseline only. | A date lacks the required discovery `run_id`, campaign-name snapshot, evaluation state, and event source. Projection reads the exact ordered dates from the latest authorized baseline artifact; later normalized run discoveries strictly after that baseline may be appended as dates. |
| `previous_campaign_appearances[]` | Artifact-backed baseline only. | A string is not a campaign identity/version or run. Projection reads the exact ordered strings; later accepted runs after the baseline may append their exact campaign-name snapshot without retroactively creating campaigns. |
| `previous_scores[]` | Artifact-backed baseline only. | A number lacks rubric name/version, dimensions, calculation hash, and run. Projection reads exact ordered totals; later normalized score rows after the baseline may append their exact totals. |
| `previous_decisions[]` | Artifact-backed baseline only. | An arbitrary string lacks kind, reason, actor, run, and effective source. Projection returns exact strings from the baseline and does not derive new arbitrary strings from normalized decisions. |
| `prior_signals[]` | Artifact-backed baseline only. | Legacy objects do not require the signal/evidence entity's type, summary, URL, date, basis, official-source flag, freshness, or run. Projection returns the exact ordered objects; later fully sourced normalized signals may be appended in Phase 1 shape. |
| `prior_rejection_reasons[]` | Artifact-backed baseline only. | Strings alone do not establish `rejected`, a run, or effective time. Projection returns the exact ordered strings; later normalized rejection reasons may be appended only from a complete result decision. |
| `client_status` / `partner_status` | Two normalized `account_state` observations after exact account binding. | Required fields are account, campaign BU, matching state kind, exact untrimmed/untruncated status, `effective_at = history.generated_at`, artifact/source identity, and server `recorded_at`; imported `run_id`, `reason`, and `supersedes_id` are null. |
| `outreach_status` | One normalized `imported_current_status` event after exact account binding. | Required fields are account, campaign BU, exact status, `occurred_at = history.generated_at`, `channel = phase1_history`, `result = snapshot_imported`, active record status, artifact/source identity, and server `recorded_at`; contact, campaign/run action, approval, and supersession refs are null. |
| `suppressed` / `suppression_reason` | A true flag emits one normalized suppression observation; false emits none. | Required fields are account target, campaign BU, `reason_code = phase1_history_flag`, exact nullable reason, `source = phase1_history`, `effective_from = history.generated_at`, no end, artifact/source identity, and server record time. No reason text is synthesized. |
| `cooldown_until` | A non-null date emits one normalized cooldown observation. | Required fields are account scope, campaign BU, `origin_type = phase1_history`, stable artifact/prospect origin ref, `starts_at = history.generated_at`, exclusive `ends_at` at next-day `00:00:00Z`, nullable reason, artifact/source identity, and server record time. |

For deterministic compatibility projection, choose the authorized history baseline with the greatest
`(history_generated_at, run.recorded_at, run.id)` at or before the as-of time. Return its artifact-backed
arrays exactly, then append only constructible normalized events whose effective time is strictly later
than the baseline and whose Phase 1 representation is defined above. This prevents duplicate replay and
never fills missing legacy semantics with fabricated runs, campaigns, rubrics, dimensions, reasons, or
evidence.

#### Prospect results

| Phase 1 JSON path | Destination | Transformation | Class | Missing/null rule | Idempotency key | Ambiguity rejection |
| --- | --- | --- | --- | --- | --- | --- |
| `results[].company_name` | accounts.`canonical_company_name` | bind after identity resolution | snapshot | required; reject | run+result ordinal | conflicts with resolved identity reject |
| `.company_type` | accounts.`account_type` | exact enum | authoritative | required; reject | account+run | conflicting existing type flags review |
| `.business_unit` | account/run scope | exact enum | authoritative | required; reject | run+account | must equal campaign BU |
| `.identity.canonical_company_name` | name identity/account | normalize | authoritative | required; reject | normalized identity | collision fails closed |
| `.identity.canonical_domain` | canonical domain identity | normalize | authoritative | required; reject | normalized domain | collision fails closed |
| `.identity.aliases[]` | alias identities | normalize/deduplicate | authoritative | missing → `[]` | identity key | collision marks ambiguous |
| `.identity.social_handles{}` | public social identities | platform+normalized handle | authoritative | missing → `{}` | identity key | collision fails closed |
| `.identity.parent_company` | relationship edge | resolve pending/confirmed with evidence | snapshot | missing/null → none | run+account+edge | multi-match rejects |
| `.identity.subbrand_of` | relationship edge | resolve independent account edge | snapshot | missing/null → none | run+account+edge | protection precedence enforced |
| `.discovery_event.discovered_at` | discovery events.`discovered_at` | parse timestamp | authoritative | required; reject | run+result | invalid/future policy violation rejects |
| `.discovery_event.campaign_name` | discovery events snapshot | exact string | snapshot | required; reject | run+result | mismatch with campaign rejects |
| `.discovery_event.source_urls[]` | evidence refs | one row per URL | authoritative | required/non-empty | run+URL+date/basis | non-HTTP(S)/credential URL rejects |
| `.signals[].type` | signals.`signal_type` | exact string | authoritative | required | run+result+signal ordinal | conflicting duplicate source record rejects |
| `.signals[].summary` | signals.`summary` | bounded text | snapshot | required | same | unsupported claim flags/rejects |
| `.signals[].source_url` | evidence refs.`source_url` | validate HTTP(S) | authoritative | required | run+URL+date/basis | credential/private URL rejects |
| `.signals[].source_date` | evidence/signals.`source_date` | date | authoritative | required | run+URL+date/basis | future/stale state cannot qualify silently |
| `.signals[].basis` | signals/evidence.`basis` | exact enum | authoritative | required | same | invalid enum rejects |
| `.signals[].official_source` | signals/evidence same field | boolean | snapshot | required | same | classification conflict rejects |
| `.score_snapshot.total` | scores.`total` | numeric | authoritative | required | run+account+rubric | range mismatch rejects |
| `.score_snapshot.dimensions{}` | scores.`dimensions` | numeric object | authoritative | required | calculation hash | missing/invalid dimension rejects |
| `.duplicate_decision.status` | decisions.`status` | exact frozen enum | authoritative | required | run+account+duplicate kind | ambiguous identity permits only review status |
| `.duplicate_decision.reason` | decisions.`reason` | bounded text | snapshot | required | same | status/reason contradiction rejects |
| `.duplicate_decision.matched_prospect_id` | decisions matched source/account IDs | resolve source ID | snapshot | missing/null allowed | same | unresolved or multi-match rejects |
| `.duplicate_decision.reengagement` | decisions.`reengagement` | boolean | authoritative | missing → `false` | same | must match `existing_new_trigger` only |
| `.duplicate_decision.matched_prospect_ids[]` | decisions matched arrays | resolve all, preserve source IDs | snapshot | missing → derived singleton/`[]` | same | any ambiguous match rejects |
| `.rejection_decision.rejected` | decisions.`rejected` | boolean | authoritative | required | run+account+rejection kind | eligibility contradiction rejects |
| `.rejection_decision.reasons[]` | decisions.`reasons` | string array | authoritative | required | same | rejected true with empty reasons rejects validation |
| `.reason_for_qualification` | decisions.`qualification_reason` | exact bounded text | snapshot | required; empty allowed per schema | qualification key | qualification on protected account rejects readiness |
| `.important_uncertainty` | decisions same field | exact bounded text | snapshot | required | decision key | omitted uncertainty rejects |
| `.recommended_next_action` | decisions same field | exact bounded text | snapshot | required | decision key | grants no action authority |
| `.rights_territory[]` | decisions.`rights_territory` | string array | snapshot | optional → `[]` | rights decision key | contradiction flags rights review |
| `.talent_recommendation_type` | decisions same field | exact enum | authoritative | optional → null | Talent decision key | named talent without approved roster rejects |
| `.talent_archetype` | decisions same field | text/null | snapshot | optional/null retained | Talent decision key | named-person-like archetype flags review |
| `.named_talent` | decisions same field | text/null, restricted | snapshot | optional/null retained | Talent decision key | non-null without authorization rejects whole run |
| `.approved_roster_authorization` | decisions same field | boolean | authoritative snapshot | optional → `false` | Talent decision key | true without roster artifact rejects |
| `.rights_status` | decisions same field | text/null | snapshot | optional/null retained | rights decision key | never upgraded by inference |
| `.brand_safety_flags[]` | decisions same field | string array | authoritative snapshot | optional → `[]` | safety decision key | unresolved material flag blocks readiness |
| `.recommended_buyer_path` | decisions same field | exact enum | snapshot | optional → null | decision key | conflicting agency graph flags review |
| `.future_handoff.ready` | decisions.`handoff_ready` | boolean | snapshot | required | handoff decision key | protected/rejected/ambiguous result cannot be ready |
| `.future_handoff.human_approval_required_before_generation` | decisions same field | must be true | authoritative policy snapshot | required; reject false | handoff key | false rejects whole run |

#### Run report and raw candidates

| Phase 1 JSON path | Destination | Transformation | Class | Missing/null rule | Idempotency key | Ambiguity rejection |
| --- | --- | --- | --- | --- | --- | --- |
| `run_metadata.run_id` | runs.`source_run_id` | exact string | authoritative | required | source system+run ID | reused ID with changed hash rejects |
| `.started_at` / `.completed_at` | runs same fields | parse timestamps | authoritative | required | run ID | invalid order rejects |
| `.skill` | runs.`skill` | allowlisted skill name | snapshot | required | run ID | unknown producer rejects |
| `.phase` | runs.`source_phase` | exact integer `1` | snapshot | required | run ID | non-1 rejects this ingestion contract |
| `campaign` | campaign version | full mapping above | authoritative | required | configuration hash | unresolved version rejects |
| `history_loaded` | runs same field | exact true | authoritative | required true | run ID | false/missing rejects |
| `search_assumptions[]` | runs same field | string array | snapshot | required; empty allowed | run ID+artifact | invalid type rejects |
| `raw_candidates[].company_name` | discovery events.`raw_company_name` | trim only | snapshot | required | run+raw ordinal | no account merge on name alone |
| `raw_candidates[].domain` | discovery event raw domain + identity proposal | normalize for resolution; preserve raw in artifact | snapshot | required | run+raw ordinal | domain collision blocks event attachment |
| `raw_candidates.*` additional fields | immutable artifact only | preserve byte-exact JSON; do not normalize unknown fields | snapshot | allowed by Phase 1 schema | artifact hash | never treated as authority |
| `results[]` | account/run child entities | full mapping above | authoritative/snapshot | required array | run+result ordinal | any ambiguous identity rolls back transaction |
| `summary.raw_candidate_count` | runs.`summary` | non-negative integer | snapshot/derived check | required | run ID | mismatch with raw rows rejects |
| `.new_unique_prospects` | runs.`summary` | integer; recompute check | snapshot/derived | required | run ID | mismatch rejects |
| `.duplicates` | runs.`summary` | integer; recompute check | snapshot/derived | required | run ID | mismatch rejects |
| `.reengagement_prospects` | runs.`summary` | integer; recompute check | snapshot/derived | required | run ID | mismatch rejects |
| `.rejections` | runs.`summary` | integer; recompute check | snapshot/derived | required | run ID | mismatch rejects |
| `.qualified_shortlist` | runs.`summary` | integer; recompute check | snapshot/derived | required | run ID | protected/ineligible shortlist rejects |
| `limitations[]` | runs same field | string array | snapshot | required | run ID | invalid type rejects |
| `validation_errors[]` | runs same field | string array | snapshot | required | run ID | non-empty may be accepted only if report remains schema-valid and policy-safe; otherwise reject |
| `future_creative_handoff_readiness` | runs same field | exact string | snapshot | required | run ID | cannot grant approval/generation |

## 7. Exact replay and Phase 1 history projection

### 7.1 Exact replay

An accepted ingestion stores logical references for both the run report and its exact history input.
Each reference contains an opaque locator, media type, schema ID/version, SHA-256, byte length,
classification, and integrity-verification result; the run also records source run ID and configuration
hash. Replay reads the artifact, verifies all integrity metadata, and validates it against the recorded
Phase 1 schemas before rendering. It does not reconstruct byte-exact JSON from normalized tables. A
hash, length, or schema mismatch fails closed and emits a redacted audit failure.

### 7.2 Future Phase 1 history read projection

The future projection service reconstructs a valid `prospect-history.schema.json` object as follows:

- root `version` is `1`; `generated_at` is the projection time;
- one row is emitted per authorized, non-merged account identity within the requested BU scope;
- canonical name/domain and active domains, aliases, and public social identities come from reviewed
  identity rows;
- parent, subsidiaries, subbrands, and agency relationships come only from active confirmed edges;
- legacy discovery dates, campaign appearances, score totals, decisions, prior signals, and prior
  rejection reasons come from the deterministic verified artifact baseline; only later constructible
  normalized rows defined in the legacy matrix are appended;
- outreach/client/partner status is selected from append-only history for the requested BU using the
  documented effective-time, recorded-time, and UUID tie-breakers; no account-row status map exists;
- any active matching suppression yields `suppressed: true`; its authorized redacted reason is used;
- the latest applicable active cooldown supplies `cooldown_until` without weakening suppression;
- run-derived signals and rejection reasons after the artifact baseline come only from fully sourced
  normalized signal/decision rows; and
- every Phase 1-required array/object is emitted even when empty.

Projection fails instead of emitting history when identity is ambiguous, required identity is absent,
relationship cycles make parentage inconsistent, suppression state conflicts, a current-state snapshot
cannot be supported by history, or the caller lacks access to the requested scope. Contact values,
contact points, internal suppression detail, approval payloads, and audit detail never appear in this
projection.

## 8. Phase 2 finalization rulings

1. **Controlled vocabularies:** use checked text for new vocabularies in the proposed first migration.
   Reuse an existing compatible Unreal OS enum only after later architecture discovery proves exact
   compatibility. Arbitrary imported Phase 1 statuses remain text, not enums.
2. **Contact-point lookup:** require a versioned keyed digest such as HMAC over a canonicalized value.
   Unsalted hashes, repository-stored keys, plaintext indexes, and worker/viewer digest exposure are
   prohibited. Concrete encryption and key-provider selection is a later security-review prerequisite,
   and real contact storage remains blocked until it is approved.
3. **Artifact reference:** the finalized logical reference is an opaque locator plus media type, schema
   ID/version, SHA-256, byte length, classification, and a required integrity-verification result.
   Physical storage selection is deferred to authorized Unreal OS architecture work; this does not
   defer the logical mapping or exact replay contract.
4. **Account merge:** Phase 2 defines no merge API. Ambiguity fails closed. Any later separately
   authorized merge workflow must preserve aliases, child history, provenance, suppression, and audit;
   it may not use name-only or latest-row-wins reconciliation.
5. **Date-only values:** preserve source dates as dates. When a timestamp is operationally required,
   use the exact documented UTC conversion. An inclusive Phase 1 `cooldown_until` date maps to the
   exclusive next-day `00:00:00Z` boundary; no local timezone inference is allowed.
6. **Retention:** do not invent retention periods. Real contact storage remains blocked until policy
   approval. Contact expiry or later retention action must not erase suppression, provenance, or
   required action/audit history.
7. **Status compatibility:** imported Phase 1 `outreach_status`, `client_status`, and `partner_status`
   values are preserved exactly without trimming, truncation, enum conversion, or per-value length
   rejection. Safety relies on the reviewed whole-artifact byte limit. A separate 512 UTF-8-byte limit
   applies only to future human-authored Phase 2 account-state values. Raw status values never appear in
   general logs, error payloads, viewer views, or cross-BU worker views.

Concrete encryption providers, key custody, physical artifact storage, and executable database
mechanisms remain later security/architecture prerequisites. They are not unresolved Phase 2 mapping
semantics and cannot weaken these rulings or create external-action authority.
