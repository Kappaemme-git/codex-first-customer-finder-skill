# Unreal OS Prospecting Migration Plan

**Program phase:** Prospecting Phase 2 — future plan only
**Status:** Independently reviewed and finalized on 2026-07-17; future plan only, with no migration authorized or present
**Contract inputs:** [data contract](UNREAL_OS_PROSPECTING_DATA_CONTRACT.md) and
[RLS/service boundary](UNREAL_OS_PROSPECTING_RLS_AND_SERVICE_BOUNDARY.md)

## 1. Purpose and hard boundary

This document sequences a future, separately approved implementation of the prospecting data
contracts. It contains no SQL and authorizes no Supabase command, migration execution, production
connection, data import, API, UI, worker, schedule, loop, creative, likeness use, advertisement, or
outreach.

All later database changes must be forward-only repository migration files. Existing migration files
must never be edited. Production import, legacy reconciliation, destructive cleanup, cutover, and
rollback actions require their own explicit approvals. Real prospect/contact data must never enter Git.

## 2. Preconditions before migration authoring

Migration authoring may start only after all of the following are recorded:

1. Independent review/finalization of all three Phase 2 contract documents.
2. An explicit Unreal OS roadmap phase authorizing schema implementation; this prospecting program
   roadmap does not renumber or advance the Unreal OS migration tracker.
3. Confirmed target environment and sanitized inventory of existing prospecting/lead-related tables,
   views, policies, functions, indexes, grants, and relevant application callers.
4. Confirm implementation prerequisites against the finalized Phase 2 rulings: checked-text
   vocabularies, logical artifact-reference fields, versioned keyed contact digest, no Phase 2 merge
   API, exact UTC date conversion, no invented retention period, and imported-status compatibility.
   Physical artifact storage, encryption provider/key custody, and real-contact retention policy still
   require their named later architecture/security approvals.
5. Approved identity binding for `os_users`/`os_roles` and named narrow ingestion/projection services.
6. Synthetic fixtures covering both business units, every duplicate status, relationships, ambiguity,
   suppression, cooldown, rights/roster rules, and valid/invalid reports.
7. A reviewed RLS test matrix and rollback/forward-fix runbook.
8. Confirmation that no migration or import requires a secret value in repository files, logs, chat,
   fixtures, or commands.

Failure of any prerequisite stops implementation; it is not bypassed with guessed schema or direct
database edits.

## 3. Versioning strategy

- Version the normalized data contract independently from Phase 1 artifact schemas.
- Record `schema_version`, `source_system`, `source_record_id`, source run ID, and artifact schema
  version on ingested records as specified by the contract.
- Treat every accepted Phase 1 JSON artifact as immutable, integrity-addressed input.
- Add new compatible columns/values before any writer uses them. Do not remove/rename a field until all
  readers, projections, artifacts, and retention obligations have a reviewed replacement.
- Use additive migrations and forward fixes. Never rewrite an applied migration.
- Keep Phase 1 local skill schemas functional throughout the first Unreal OS increment.

## 4. Proposed additive migration sequence

Each numbered increment is a future repository migration plus its tests/evidence. Later increments do
not begin until the prior increment passes in an approved non-production environment.

### Increment 1 — shared types and immutable artifact prerequisites

1. Add reviewed checked-text constraints for new controlled vocabularies; reuse an existing enum only
   after architecture discovery proves exact compatibility. Never enum-constrain arbitrary imported
   Phase 1 status text.
2. Add any reviewed immutable artifact-reference primitive that is not already supplied by Unreal OS.
3. Add schema-version/source/idempotency validation helpers only if they are demonstrably shared and
   authorized; avoid a speculative framework.
4. Verify no new type conflicts with existing `os_*` names and no existing enum is silently changed.

### Increment 2 — accounts and identity graph

Create in dependency order:

1. `os_prospecting_accounts`;
2. `os_prospecting_account_identities`; and
3. `os_prospecting_account_relationships`.

Then add foreign keys, uniqueness/check constraints, collision indexes, directional relationship
indexes, effective-date checks, and identity serialization/locking support. Test self-edge rejection,
parent cycles, domain/handle collisions, alias ambiguity, distinct subbrands, and protection precedence.

### Increment 3 — campaign and run spine

Create:

1. `os_prospecting_campaigns` with immutable versioning; and
2. `os_prospecting_runs` with exact artifact integrity and source-run idempotency.

Add campaign-family/version, source-run, artifact-hash, and BU/time indexes. Verify a campaign version
cannot change after a run references it; every run records the exact logical history-input artifact
locator, media type, schema ID/version, SHA-256, byte length, classification/integrity result, and
`history.generated_at`; and an identical retry is a no-op while conflicting source-run/artifact reuse
fails.

### Increment 4 — discovery, evidence, signals, scores, and decisions

Create in order:

1. `os_prospecting_discovery_events`;
2. `os_prospecting_evidence_refs`;
3. `os_prospecting_signals`;
4. `os_prospecting_score_snapshots`; and
5. `os_prospecting_decisions`.

Add FKs first as not-yet-used schema dependencies, then indexes for run/account timelines, evidence
freshness, signal types, rubric/version, frozen duplicate statuses, re-engagement, rejection, and
handoff readiness. Add the explicit decision BU, account-state-kind discriminator, run-derived and
runless-correction uniqueness rules, per-kind conditional field checks, `future_handoff` kind,
supersession-chain constraint, and deterministic current-state index. Verify every row in the
decision-kind materialization matrix, append/supersede behavior, every frozen Phase 1 duplicate
status, and governed runless human corrections without making `status`, `reason`, `effective_at`, or
`run_id` universally required.

### Increment 5 — restricted contacts and contact points

Only after field protection, visibility, provenance, retention, and keyed-digest decisions are approved:

1. create `os_prospecting_contacts`;
2. create `os_prospecting_contact_points`;
3. apply field protection and restricted lookup mechanism; and
4. prove general audit/error/telemetry paths cannot reveal values.

Use synthetic public-business identities only. Do not import real contact data in this increment.

### Increment 6 — outreach history and protection state

Create:

1. `os_prospecting_outreach_events`;
2. `os_prospecting_suppressions`; and
3. `os_prospecting_cooldowns`.

Add append-only constraints/grants, typed target validation, effective-date checks, source event
idempotency, explicit BU, the controlled `imported_current_status` shape, exact imported
`status_value`, whole-artifact byte enforcement, and account/BU/current-order timeline indexes. Do not
add a per-value limit to imported Phase 1 status text; apply the separate 512 UTF-8-byte limit only to
future human-authored account state. A `sent` event remains
import/history-only until a later outreach execution phase exists; this increment creates no executor.
Test that imported snapshots remain distinct from factual sent/replied events, no actor can delete
history, and no worker/service can deactivate/shorten protection.

### Increment 7 — foreign keys, indexes, RLS, grants, and shared audit links

For each table, use this order:

1. validate existing synthetic rows against checks;
2. add/validate foreign keys;
3. add required indexes and verify query plans for named query purposes;
4. enable and force RLS;
5. add deny-by-default role policies and column-safe views;
6. grant the smallest operations to human roles and the two narrow services;
7. explicitly withhold update/delete from append-only entities;
8. link governed writes to `os_action_log`/`os_audit_events`; and
9. test every allowed and denied matrix cell, including cross-BU and contact-column denials.

The UI and workers receive no service-role key. A failed audit append must roll back the governed write.

### Increment 8 — ingestion and projection boundaries

Implement only the two reviewed service purposes:

- fully validated, atomic Phase 1 report ingestion; and
- authorized, deterministic Phase 1 history projection.

Do not add a generic prospecting CRUD API, browser/enrichment capability, schedule, runner, loop,
creative generator, approval decider, or outreach executor. Validate payload limits, composed schemas,
hashes, transaction rollback, typed safe errors, and audit redaction.

### Increment 9 — compatibility adapter/read view

Add the smallest reviewed compatibility view or adapter needed for existing Unreal OS consumers while
they transition from provisional flat `leads` assumptions. It must:

- read from normalized accounts/events rather than duplicate source-of-truth state;
- exclude contacts/contact points and restricted suppression detail unless an authorized consumer
  explicitly requires them;
- expose provenance/freshness and never imply that a discovery is an outreach-ready lead;
- remain read-only; and
- have a removal criterion after all callers migrate.

Do not drop or repurpose an existing flat `leads` table in the first increment.

## 5. Synthetic validation plan

Before any real-data discussion, run synthetic tests for:

- UMG and Talent campaign versions, open and filtered scope;
- one global account associated with both BUs, with no duplicated account identity;
- different client and partner status values within the same BU;
- different UMG and Talent client, partner, and outreach values with no cross-BU disclosure;
- exact round-trip of empty and arbitrarily long Phase 1 outreach/client/partner status strings within
  the approved whole-artifact byte limit, with no trimming, truncation, value logging, or enum cast;
- rejection of a future human-authored account-state value over 512 UTF-8 bytes without exposing it;
- deterministic current-state tie-breaking by effective/occurred time, recorded time, then UUID;
- all nine decision-kind/component matrix rows, including conditional status/reason/effective fields,
  Talent rights/roster binding, zero imported identity-review rows, and one future-handoff row;
- constructibility audit proving legacy discovery dates, campaign appearances, scores, decisions,
  prior signals, and prior rejection reasons remain verified-artifact-backed while normalized legacy
  state/suppression/cooldown rows supply every required field;
- every required/optional durable Phase 1 campaign, history, result, and run-report field;
- all 11 frozen duplicate statuses and matched single/multiple IDs;
- same-run retry, identical reimport, conflicting source-key reuse, and partial transaction rollback;
- a governed runless human correction that supersedes the current same-account/BU/state-kind leaf;
- an older imported account/outreach state recorded later without overwriting newer effective state;
- domain/name/alias/handle collisions and zero/multiple account resolution;
- parent/subbrand/agency edges, cycles, conflicting parents, and relationship evidence review;
- client, partner, active-outreach, suppression, and cooldown precedence across related accounts;
- stale, future-dated, unofficial, inferred, and missing evidence;
- rubric/version/dimension score validation and superseding human overrides;
- Talent archetype-only behavior, authorized roster snapshot, named-talent rejection, rights status,
  and brand-safety flags;
- restricted contact/point visibility and audit/log redaction;
- append-only/no-delete behavior for runs, evidence, signals, scores, decisions, outreach,
  suppressions, and cooldowns;
- every RLS role and service operation cell, including worker/viewer/service denial on every direct
  state path, cross-BU denial, and column/view restriction;
- projection returning only the requested authorized BU and failing rather than using another BU as a
  fallback;
- exact artifact integrity failure and safe typed errors; and
- Phase 1 history projection schema validity and deterministic ordering.

## 6. Phase 1 dry-run ingestion and round-trip gate

Using only synthetic Phase 1 artifacts:

1. Validate each artifact with the unchanged Phase 1 schemas/tools.
2. Ingest it into an approved non-production database through the narrow ingestion boundary.
3. Confirm atomic row counts, relationships, source IDs, hashes, and audit/action references.
4. Reimport the identical artifact and prove no duplicate normalized records are created.
5. Reuse the source run ID with changed bytes and prove the import is rejected.
6. Import an older synthetic state snapshot after a newer one and prove deterministic current state is
   unchanged without supersession; then append a governed human supersession within the same
   account/BU/state kind and prove the old rows remain queryable and the chain cannot fork.
7. Project Phase 1 history for the same BU/as-of scope and prove the other BU's three state values are
   neither returned nor used as fallback.
8. Validate projected JSON against `prospect-history.schema.json`.
9. Compare identity, relationship, discovery, score, decision, suppression/cooldown, and prior-signal
   semantics with the source expectations.
10. Replay the immutable run artifact and verify SHA-256, byte length, media type, and schema version.
11. Record evidence containing only synthetic IDs, counts, statuses, paths, hashes, and result types.

Any semantic field loss, ambiguous identity guess, protection bypass, non-deterministic projection,
contact disclosure, or audit failure blocks the next step.

## 7. Provisional flat-lead reconciliation

Existing Unreal OS documentation describes provisional `leads`, `lead_events`, `suppression_list`, and
outreach tables whose live production shapes remain subject to inventory/reconciliation. The new
prospecting model must not silently replace or mutate them.

A future reconciliation phase must:

1. Inventory actual tables, columns, constraints, policies, grants, views, functions, row counts, and
   application callers using a sanitized, read-only method.
2. Classify each field as account, identity, contact, contact point, event, decision, suppression,
   cooldown, or unsupported/private data.
3. Define deterministic source IDs and ambiguity queues before copying any row.
4. Preserve every sent/contacted/replied/suppressed event required for deduplication.
5. Keep the flat source readable during the first normalized increment.
6. Use a read-only compatibility adapter/view for consumers that cannot migrate immediately.
7. Reconcile duplicates and ambiguous identities through explicit human review, never by name-only
   merge or latest-row-wins.
8. Keep real PII/business data out of Git; store only sanitized plans, schemas, and aggregate evidence.
9. Treat production import as a separate, exact, time-bounded approval with dry-run evidence.
10. Defer destructive cleanup, drop, rename, archival, or source retirement to a later separately
    approved action after parity and retention review.

## 8. Production import and cutover gates

Neither action is authorized by this plan.

### Production import prerequisites

- independently finalized contracts and applied non-production migrations;
- passed synthetic and Phase 1 round-trip gates;
- approved sanitized inventory and deterministic mapping;
- approved data classification, retention, encryption, contact access, and suppression rules;
- exact import scope, counts, owner, runtime cap, stop conditions, rollback/forward-fix plan, and
  per-action human approval;
- verified backups/recovery appropriate to the target; and
- monitoring/evidence plan that cannot expose PII, credentials, or message bodies.

### Cutover prerequisites

- old and new read models reconciled for agreed counts/semantics;
- all callers enumerated and tested against the compatibility/new projection;
- RLS/role tests and denial paths passed in the target environment;
- duplicate ambiguity queue reviewed by humans;
- suppression/cooldown and outreach-history parity demonstrated;
- audit/action/evidence references complete;
- owner, maintenance window, abort thresholds, and human approvals recorded; and
- a proven forward-fix/recovery path that does not erase history.

## 9. Observability and evidence

Future migration evidence records only:

- migration identifier and reviewed commit/reference;
- environment class (never credentials or connection values);
- start/end timestamps, actor role, approval reference where required;
- schema object names, counts, constraint/index/RLS test statuses;
- synthetic fixture IDs and aggregate reconciliation counts;
- error class and affected path/type/reference, not raw row content;
- artifact integrity hashes and schema versions; and
- rollback/forward-fix decision and result.

No evidence packet or log may contain real prospect/contact values, source page bodies, message bodies,
imported or authored status values, tokens, keys, passwords, cookies, connection strings, or unredacted
database output.

## 10. Failure, rollback, and forward-fix policy

- Before an unapplied migration is released, fix it in review and rerun all checks.
- After a migration is applied to any shared environment, do not edit it. Add a forward-fix migration.
- Transactional schema/data failures roll back the current transaction when safe; record only redacted
  result metadata.
- Never roll back by deleting append-only runs, decisions, evidence, outreach, suppression, cooldown,
  action log, or audit history.
- Never use `DROP`, `TRUNCATE`, bulk delete, history rewrite, or destructive reconciliation as an
  automatic recovery step.
- If a new reader is faulty, disable/route the reader through an approved reversible control while
  preserving stored history; do not mutate data to hide the failure.
- If production import produces ambiguity or protection conflict, stop the import, keep the source
  authoritative, quarantine only by reference/status, and require human reconciliation.
- Any destructive corrective action is a new proposal with exact scope and separate approval.

## 11. Human approval points

Separate explicit authorization is required for each of these future actions:

1. Finalize the Phase 2 contracts after independent review (completed on 2026-07-17; design finalization does not authorize implementation).
2. Author Unreal OS migrations in the tracker-authorized implementation phase.
3. Apply migrations to a development/staging project.
4. Provision identity bindings or narrow service credentials without exposing values.
5. Inspect/import any real business/contact data.
6. Apply migrations or import to production.
7. Resolve ambiguous account/contact/relationship mappings with business impact.
8. Cut over readers/writers.
9. Retire a compatibility view or old caller.
10. Archive, drop, rename, delete, or otherwise destructively reconcile legacy structures.

Approval for one item is not standing approval for another. Workers/services never approve, and the
proposer cannot self-approve.

## 12. Exit gate for the future migration program

The future implementation is complete only when:

- all reviewed entities, constraints, indexes, RLS policies, grants, and audit links exist through
  repository migrations;
- synthetic and Phase 1 round-trip/idempotency/projection tests pass;
- contacts and protection state remain correctly restricted;
- no field in the Phase 1 mapping matrix is lost;
- existing callers have a verified compatibility or normalized path;
- production reconciliation/cutover, if separately authorized, has evidence and human sign-off; and
- no schedule, loop, creative/likeness generation, advertisement, or outreach authority was introduced
  by the data migration.

Phase 1 local JSON artifacts remain the operational contract. Phase 2 design is finalized; executable
implementation remains unauthorized until a later explicitly authorized phase begins.
