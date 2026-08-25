# Unreal OS Prospecting RLS and Service Boundary

**Program phase:** Prospecting Phase 2 — contract design only
**Status:** Independently reviewed and finalized on 2026-07-17; design-only, not SQL or live policy
**Companion:** [UNREAL_OS_PROSPECTING_DATA_CONTRACT.md](UNREAL_OS_PROSPECTING_DATA_CONTRACT.md)

## 1. Scope and inherited governance

This contract defines the future authorization and service boundaries around the proposed
`os_prospecting_*` entities. It does not deploy RLS, grant a role, create a service identity, connect to
Supabase, ingest data, export history, or authorize outreach.

The future implementation must bind authenticated identities through shared `os_users` and `os_roles`
and reuse `os_approval_requests`, `os_action_log`, `os_audit_events`, and `os_evidence_packets`.
Workers and non-human services are never approvers. No UI or worker receives a Supabase service-role
key. Every prospecting table has RLS enabled with deny-by-default grants.

The role contract is:

- `noah`: broad operational read and governed human review; cannot self-approve.
- `rob` / `dan`: business, brand, client, legal, money, and rights-scoped human review; cannot
  self-approve or act outside scope.
- `worker`: narrow campaign/run research worker; proposes and appends validated work only.
- `viewer`: safe aggregate and non-sensitive read-only projections.
- `prospecting_ingestion_service`: future non-human identity limited to the ingestion transaction.
- `prospecting_projection_service`: future non-human identity limited to authorized Phase 1 history
  projection.

The service roles are narrower than a general Unreal OS `service` role, are never usable in browser
code, and hold no approval, outreach, creative, scheduling, or arbitrary-table capability.

## 2. Universal RLS invariants

1. RLS is enabled and forced on every `os_prospecting_*` table. Absence of a matching allow policy
   denies the operation.
2. Business-unit scope is checked from an authoritative actor assignment and row associations, not a
   client-supplied claim. A scoped row with null, contradictory, or unrecognized scope fails closed.
3. `noah`, `rob`, and `dan` remain subject to RLS and column restrictions. Human role does not imply
   unrestricted database ownership.
4. `worker` may not approve, self-approve, change protected account state, resolve identity collisions,
   weaken suppression/cooldown, create a `sent` event, or read restricted contact values.
5. `viewer` has no direct access to contacts, contact points, internal suppression reasons, raw
   evidence summaries, approval payloads, or source artifacts. Viewer reads use explicit safe views.
6. Append-only rows have no `UPDATE` or `DELETE` policy. Correction uses a superseding/compensating
   insert by an authorized actor.
7. Mutable rows use column allowlists, optimistic concurrency, and audit. A generic row update is not
   permitted.
8. Suppression cannot be bypassed by a campaign, relationship, subbrand, worker, service, score, or
   approval. Only an authorized human may add a superseding correction; prior state remains.
9. Approved actions are per-action and expire. An approval record never becomes a standing grant.
10. Ingestion has no outreach, browsing, enrichment, approval, creative, generation, scheduling,
    runner, loop, or external-write capability.
11. Projection has no mutation or action capability. It fails on inconsistent or unauthorized state.
12. Secrets, credentials, private datasets, page bodies, message bodies, and sensitive traits are
    rejected before storage. Audit records paths/types/references/statuses only, never values.
13. A failure to append the required action/audit record rolls back the governed transaction.
14. A client/partner current-state change appends a BU-scoped, typed account-state decision; an
    outreach current-state change appends a BU-scoped state-bearing outreach event. Current state is a
    deterministic authorized projection, never mutable account JSON.

## 3. Role and scope rules

### 3.1 Human roles

`noah` may read all prospecting operational state, including restricted contacts, when business need
and policy permit. He may perform governed identity/account/suppression/cooldown review through future
owned application paths. He may not approve a request he proposed and cannot bypass hard policy.

`rob` and `dan` may read prospecting operational state needed for commercial, brand-safety, rights,
client, and legal review. Their governed writes are limited to that scope. They cannot approve their
own requests or Noah-only technical/external actions.

Human review of a prospect, identity, relationship, score, or handoff is not permission to generate
creative, use a likeness, contact a person, or send outreach. Each later action remains a separate
phase and approval.

### 3.2 Worker role

The worker may read approved campaign versions, its assigned BU-scoped non-sensitive history
projection, and the status of its own run/ingestion proposal. It may submit a complete hashed
Phase 1 report to the ingestion boundary when that service exists. It has no direct table mutation
grant for normalized prospecting state.

The worker never reads contact-point values, internal suppression narratives, another business unit's
restricted state, source artifact bytes outside its assignment, approval payloads, or credentials.

### 3.3 Viewer role

Viewer access is limited to explicit projections such as campaign/run counts, non-sensitive account
summaries, score/status distributions, and evidence freshness. Direct table reads are denied where a
row or column could reveal contact data, restricted rights/roster context, detailed suppression
reasons, or internal evidence text. Viewer can never insert, update, delete, propose, approve, or act.

### 3.4 Narrow non-human roles

Each service authenticates as its own non-human identity. It is bound to one transaction purpose,
allowlisted schema versions, explicit columns, and required audit correlation. Neither identity may be
used from a browser or handed to a general worker. Neither is an approver.

## 4. Entity permission matrix

`S`, `I`, `U`, and `D` mean `SELECT`, `INSERT`, `UPDATE`, and `DELETE`. `None` means no operation is
granted. A qualifier such as `S (safe view)` narrows that operation; it does not grant direct base-table
access. Every operation not written in a cell is explicitly denied. Every listed operation is still
BU-scoped where applicable, column-allowlisted, validated, audited, and available only through the
owned future application/service path. These are 15 entities by seven principals: 105 explicit
authorization decisions.

| Entity | `noah` | `rob` | `dan` | `worker` | `viewer` | `prospecting_ingestion_service` | `prospecting_projection_service` | Restrictions and denial behavior |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `os_prospecting_accounts` | S, I, U | S, I, U | S, I, U | S (safe assigned identity view) | S (safe identity view) | S, I | S (identity columns only) | One global identity row; U is limited to global lifecycle/identity-review columns. No BU state columns exist. State is denied here and obtained only from the authorized BU projection. |
| `os_prospecting_account_identities` | S, I | S, I | S, I | S (confirmed assigned view) | S (confirmed safe view) | S, I | S (confirmed required rows) | Append-only/superseded; U and D denied to all. Collision detail is human-only. Services cannot resolve collisions. |
| `os_prospecting_account_relationships` | S, I | S, I | S, I | S (confirmed assigned view) | S (confirmed safe view) | S, I | S (confirmed required rows) | Append-only/superseded; U and D denied to all. Pending/ambiguous edges are hidden from worker/viewer/projection output. |
| `os_prospecting_campaigns` | S, I | S, I | S, I | S (assigned active-version view) | S (safe config view) | S, I | S (required version columns) | Immutable version rows; U and D denied after insert. Artifact/roster refs and include/exclude internals are hidden from worker/viewer. |
| `os_prospecting_runs` | S | S | S | S (own-run view) | S (safe summary view) | S, I | S (required history rows/artifact metadata) | Append-only; I is ingestion-only and U/D are denied to all. Artifact bytes are never exposed; opaque history locator/integrity fields are available only inside the authorized projection boundary. |
| `os_prospecting_discovery_events` | S | S | S | S (own-run view) | S (aggregate view) | S, I | S (required BU rows) | Append-only; I is ingestion-only and U/D are denied to all. Viewer cannot see raw company/domain. |
| `os_prospecting_evidence_refs` | S, I | S, I | S, I | S (authorized redacted view) | S (freshness/source view) | S, I | S (required redacted rows) | Corrections are superseding inserts; U/D denied to all. Restricted summaries and artifact refs are excluded from worker/viewer and unnecessary projection columns. |
| `os_prospecting_signals` | S, I | S, I | S, I | S (authorized history view) | S (redacted signal view) | S, I | S (required BU rows) | Append-only/superseded; U/D denied to all. Sensitive/protected factors and stale-as-current inference are prohibited. |
| `os_prospecting_score_snapshots` | S, I | S, I | S, I | S (authorized history view) | S (aggregate/factor-safe view) | S, I | S (required BU rows) | Append-only; overrides are new rows. U/D denied to all. Rubric/version/dimensions remain required. |
| `os_prospecting_decisions` | S, I | S, I | S, I | S (authorized BU prior-state view) | S (redacted non-state view) | S, I | S (requested-BU projection columns) | Append-only/superseded; U/D denied to all. Worker/viewer cannot directly read account-state rows. Rights, roster, uncertainty, matched IDs, and internal reasons remain restricted. |
| `os_prospecting_contacts` | S, I, U | S, I, U | S, I, U | None | None | S, I | None | Restricted assigned-human access only; U is an allowlisted review/visibility change with audit. Worker/viewer/projection have no row or column path. Values never enter general logs. D denied to all. |
| `os_prospecting_contact_points` | S, I | S, I | S, I | None | None | S, I | None | Field-protected restricted view for humans; append/effective replacement by insert. U/D denied to all. Worker/viewer/projection receive neither plaintext nor digest. |
| `os_prospecting_outreach_events` | S, I | S, I | S, I | S (coarse requested-BU eligibility view) | S (aggregate counts only) | S, I | S (requested-BU state columns only) | Append-only/compensating; U/D denied to all. `status_value` is hidden from viewer and from any worker request outside its BU. No current Phase 2 `sent` insertion path exists. |
| `os_prospecting_suppressions` | S, I | S, I | S, I | S (effective boolean/safe-code view) | None | S, I | S (effective boolean/safe code only) | Append-only/superseded; U/D denied to all. Target values and internal reasons remain human-restricted; services cannot deactivate or shorten. |
| `os_prospecting_cooldowns` | S, I | S, I | S, I | S (applicable end/status view) | S (safe aggregate view) | S, I | S (applicable requested-BU rows) | Append-only/superseded; U/D denied to all. Worker/services cannot shorten human/policy cooldown. |

The state projection joins a global account only to `account_state` decisions and state-bearing outreach
events after filtering both sources to the caller's authorized requested BU. It then filters by
`account_state_kind` and applies the deterministic effective/recorded/UUID order. Base account reads
cannot reveal BU state because the account has no such columns. Direct access, safe views, and the
projection service have no fallback or join path to another BU's client, partner, or outreach value.

### 4.1 Shared governance entity use

- Any future governed human correction records `os_action_log` and `os_audit_events` in the same
  transaction or fails.
- Any later action needing approval references one exact, unexpired `os_approval_requests` row. The
  worker/service cannot transition approval status.
- `os_evidence_packets` is readable only under its existing policy; a prospecting reference does not
  broaden access.
- Audit events contain actor/reference/action/result/path/type metadata only. Contact values, message
  bodies, source page bodies, credentials, and approval payload contents are excluded.

## 5. Future service boundary 1 — Phase 1 report ingestion

### 5.1 Sole purpose

Accept one complete Phase 1 run report artifact, validate it fully, and atomically record the immutable
artifact reference plus normalized prospecting rows. The boundary is a transactional ingestion
adapter, not a research agent or generic CRUD service.

### 5.2 Required inputs

- authenticated narrow ingestion identity and assigned business unit;
- immutable artifact reference, media type, byte length, SHA-256, schema ID/version;
- Phase 1 run report conforming to the recorded schema set;
- exact campaign configuration/version and history artifact references; and
- audit correlation ID and source-system/source-record idempotency values.

No credential, service-role key, browser session, page body, private dataset, message body, or contact
enrichment payload is accepted.

### 5.3 Validation sequence

1. Authorize the service identity and business-unit assignment.
2. Verify artifact integrity, allowlisted media/schema version, and byte limits.
3. Validate the whole report and composed Phase 1 schemas before any write.
4. Require `history_loaded: true`, an allowed skill/BU match, source phase `1`, valid time order, and
   internally consistent summary counts.
5. Resolve the exact immutable campaign version or insert a new valid version under governed rules.
6. Resolve identities transactionally. Any collision, conflicting parent/subbrand relationship, or
   zero/multiple account match rolls back; no partial account guessing.
7. Validate every account-state row has explicit campaign BU and `client_status` or `partner_status`,
   and every imported outreach snapshot has `event_type = imported_current_status`, the same explicit
   BU, exact status text, and `history.generated_at` as its effective/event time. Imported Phase 1
   statuses have no per-value length cap; validate the reviewed whole-artifact byte limit instead.
   Reject missing kinds, cross-BU values, invalid runless rows, or source-key conflicts before writes.
   Apply the separate 512 UTF-8-byte limit only to future human-authored account-state values.
8. Apply client/partner/active-outreach/suppression/cooldown precedence and reject an ineligible ready
   handoff.
9. Validate evidence URLs/dates/basis/freshness and reject prohibited content classes.
10. Validate score rubric/version/ranges and every frozen duplicate/rejection/handoff rule.
11. Validate Talent roster/rights invariants: named talent requires an approved roster artifact and
    explicit authorization; readiness still requires later human approval.
12. Check the source run ID and artifact hash idempotency pair. Identical reimport returns the existing
    outcome without duplicates; conflicting reuse fails.
13. Insert run and all normalized children in one transaction, append redacted action/audit records,
    and commit only if audit succeeds.

### 5.4 Explicit exclusions

The ingestion service cannot browse, search, enrich, generate creative, use likenesses, draft or send
outreach, decide/approve, create a schedule or loop, call an external CRM, modify unrelated Unreal OS
state, expose artifacts, resolve ambiguity, or weaken suppression/cooldown. It has no arbitrary SQL,
table selection, delete, or general update ability.

## 6. Future service boundary 2 — Phase 1 history projection

### 6.1 Sole purpose

Read authorized normalized prospecting state and return one valid Phase 1
`prospect-history.schema.json` document for a specific business unit and as-of time. It performs no
state change and no external action.

### 6.2 Required inputs and authorization

- authenticated caller and authorized business-unit/campaign scope;
- requested history schema version (`1`);
- as-of timestamp and optional campaign-family reference; and
- audit correlation/reference metadata that contains no contact values.

### 6.3 Projection behavior

The service filters account-state decisions and state-bearing outreach events to the requested
authorized BU before ranking them, then applies the documented effective/recorded/UUID ordering. It
selects the deterministic verified history-artifact baseline and reads its compatibility-only arrays
inside the service boundary; locators, hashes, and raw artifact content are never returned to callers.
It then appends only later normalized rows whose Phase 1 representation is constructible under the
data-contract matrix. It
emits required root fields and every required per-prospect field, preserving canonical identity,
relationships, discovery/campaign history, score/decision history, that BU's current outreach/client/
partner status, active suppression, latest applicable cooldown, prior signals, and rejection reasons.
It uses confirmed current identities/relationships and append-only history. It never includes contacts,
contact points, private data, detailed suppression narrative, approval payloads, or audit details.

The output is deterministic for the same authorized database snapshot, schema version, scope, and
as-of timestamp. It includes projection schema/version metadata out of band and may be stored as an
immutable campaign input artifact by a later approved workflow.

### 6.4 Fail-closed conditions

Projection returns no partial history when a required identity is missing/ambiguous, parentage is
cyclic or contradictory, protected state conflicts, current snapshots lack supporting history,
suppression targets cannot be resolved, schema version is unsupported, or caller scope is insufficient.
It does not repair, merge, or infer through the conflict.

### 6.5 Explicit exclusions

The projection service cannot insert/update/delete, approve, create campaigns/runs, browse/enrich,
return contact values, trigger a worker, generate creative, draft/send outreach, or contact an external
system.

## 7. Error contract

Errors are typed, bounded, and safe to log. They include an error class, correlation ID, affected
source/table/reference type, retryability, and redacted remediation hint. They never echo raw payloads,
imported or authored status values, contact values, URLs with credentials, page bodies, secrets,
tokens, or message bodies.

| Error class | Meaning | Transaction/result behavior |
| --- | --- | --- |
| `invalid_schema` | JSON fails the recorded composed schema. | Roll back/reject; non-retryable until corrected. |
| `unsupported_schema_version` | Report/history/data contract version not allowlisted. | Reject before writes. |
| `business_unit_mismatch` | Caller, campaign, skill, result, target, or state-history BU conflicts. | Reject and audit scoped denial; disclose no other-BU state. |
| `invalid_account_state` | Account-state kind/BU/effective source is missing or incompatible, a human-authored value exceeds its separate limit, or a runless correction lacks governed supersession fields. | Reject before writes; preserve prior state. Imported Phase 1 text is never rejected for per-value length. |
| `invalid_outreach_state` | Imported snapshot shape/BU/effective source is invalid or a factual event carries snapshot-only state. | Reject before writes; preserve prior events. Do not echo the status value. |
| `history_not_loaded` | Phase 1 fail-closed history flag is absent/false or artifact unavailable. | Reject whole run. |
| `ambiguous_identity` | Identity maps to zero/multiple conflicting accounts or collision unresolved. | Roll back; human identity review required. |
| `duplicate_run` | Exact source run/artifact already accepted. | Idempotent existing-result response; no duplicate inserts. |
| `idempotency_conflict` | Same source key has different content/hash. | Reject and audit integrity conflict. |
| `stale_or_future_evidence` | Evidence violates campaign date/freshness rules. | Reject qualification or whole inconsistent report. |
| `invalid_relationship` | Self-edge, cycle, unsupported type, contradictory parent, or missing evidence for confirmation. | Roll back affected ingestion. |
| `suppression_conflict` | Result/handoff contradicts active suppression or protected related account. | Reject whole inconsistent report. |
| `cooldown_conflict` | Re-engagement/readiness contradicts active cooldown. | Reject whole inconsistent report. |
| `rights_or_roster_conflict` | Named talent/rights assertion lacks authorized source or safety consistency. | Reject whole run; no partial Talent data. |
| `rls_denied` | Actor/scope/column/operation not allowed. | No data disclosure or mutation; safe audit event. |
| `artifact_integrity_failure` | Hash, byte length, media type, or immutable reference mismatch. | Reject before normalization. |
| `transaction_rolled_back` | Any normalized write failed after validation. | No partial rows; retry only if underlying cause is retryable. |
| `audit_write_failed` | Required action/audit append failed. | Roll back governed operation. |
| `projection_inconsistent_state` | Required Phase 1 history cannot be safely reconstructed or deterministic current selection is impossible. | Return no partial history; human review. |

## 8. Security review checklist for later implementation

This checklist applies when implementation is separately authorized; it does not activate a new OWASP
or application-security surface in this design phase.

- Prove RLS is enabled/forced and deny-by-default on every table.
- Test every role and every SELECT/INSERT/UPDATE/DELETE denial in the matrix, including cross-BU access.
- Prove no browser bundle, UI, worker, or log contains a service-role key or credential value.
- Validate composed schemas, content/byte/depth limits, URL schemes, timestamps, enums, and hashes
  server-side before mutation.
- Serialize identity resolution and test collision/race behavior.
- Test identical retry, conflicting retry, transaction rollback, and mandatory audit rollback.
- Test exact round-trip of imported statuses beyond 512 bytes within the approved artifact limit, plus
  rejection of over-limit future human-authored state without logging either value.
- Prove suppression/client/partner/active-outreach precedence across parent/subbrand/agency edges.
- Prove workers/services cannot approve, self-approve, shorten protections, create sent events, or read
  contacts/contact points beyond scope.
- Prove append-only tables have no update/delete path and supersession retains history.
- Prove audit/error/telemetry output is path/type/reference only and contains no contact values, raw
  source content, approval payloads, message bodies, credentials, or private data.
- Prove projection is deterministic, schema-valid, authorization-scoped, and fails closed on every
  inconsistent-state case.
- Use synthetic fixtures only until a separately approved data-import phase.

## 9. Review and activation gate

This RLS/service boundary is not final until independently reviewed with the data contract and future
migration plan. Review completion still authorizes no SQL, Supabase command, service, endpoint, UI,
worker, schedule, loop, creative, likeness, real data, or outreach. Each requires its roadmap phase and
explicit approval.
