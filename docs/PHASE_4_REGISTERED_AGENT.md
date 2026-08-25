# Phase 4 Registered Prospecting Agent

**Status:** Independently reviewed and finalized at current-lineage commit `b7892aed5ad9ab0dcb9d900d95d6971332582ef8`

Phase 4 moves manual fixture execution behind one locally registered, governed worker:
`brand-prospecting-agent`. Execution remains manual, synthetic, fixture-only, and loopback-only.
There is no scheduler, recurring loop, network client, credential, creative, likeness, or outreach
capability, and no external system is touched. Phase 5 subsequently adds a separate, human-enabled
local shadow-loop control plane without changing this finalized Phase 4 worker contract.

## Start locally

From the repository root:

```bash
PYTHONPATH=apps/prospecting-mission-control \
  python3 -m mission_control --port 8765
```

Open `http://127.0.0.1:8765`. The server binds to loopback only. Campaign and prospect review state
is still process-local and resets on restart; registered worker-run state is durable in a local
SQLite file.

## Local durable state

- Default path: `apps/prospecting-mission-control/local_state/phase4-state.sqlite3` (gitignored).
- The operator may select another explicitly local file with `--state-path PATH`; path selection is
  server-owned and never accepted from a browser client.
- Tests always inject temporary paths; no runtime state file may ever be committed.
- The finalized Phase 4 schema used `schema_version` 1. Phase 5 upgrades the same file additively to
  version 2 without altering or deleting these Phase 4 tables or rows. There
  is no destructive reset, `DROP`, `TRUNCATE`, or delete-and-recreate path.
- Every governed multi-record change (run creation, attempt claim, success commit, failure commit,
  cancellation, startup recovery) is one serialized `BEGIN IMMEDIATE` transaction with foreign keys
  on; if a required audit insert fails, the governed state change rolls back with it.
- To reset local development state, stop the server and delete the `local_state/` directory
  manually. The application never deletes it.

## Registered agent

| Field | Value |
| --- | --- |
| Agent ID | `brand-prospecting-agent` |
| Contract version | `1.0.0` |
| Trigger | manual human form only |
| UMG binding | `unreal-media-brand-prospector@1.0.0-phase1-frozen` |
| Talent binding | `unreal-talent-campaign-prospector@1.0.0-phase1-frozen` |
| Skill integrity | SHA-256 manifest over the reviewed skill directory, recorded per run |
| Max concurrency | 1 |
| Timeout | 10 s server-owned (bounds 1–30 s; clients cannot change it) |
| Cost cap | exactly $0; a positive executor cost fails closed |
| Max attempts | 3 (one initial execution plus at most two manual retries) |
| Capabilities absent | credentials, scheduler, recurring loop, network, creative, likeness, outreach |

Business-unit skill routing is server-owned. The manual-run boundary accepts only the campaign
family, exact immutable version, initiating human actor, and idempotency key; a client can never
supply a skill name, import path, executable, file path, command, or version.

## Manual run workflow

1. A human creates an immutable campaign version (`/campaigns/new`).
2. The campaign detail page's **Start fixture dry run** form delegates to the registered agent:
   a durable logical run is created (`queued`), then one bounded one-shot attempt executes the
   existing Phase 3 deterministic fixture adapter cooperatively in that request's thread.
3. Every attempt — first execution or manual retry — replays the run's **durable validated input**:
   the persisted immutable configuration snapshot is hash-checked, revalidated by the frozen Phase 1
   validator, checked against the server-owned business-unit skill binding and the recorded skill
   integrity manifest, and only then rehydrated into the process-local adapter. A retry therefore
   works after a real process restart with no in-memory Phase 3 state, and corrupted or mismatched
   durable input fails closed (`invalid_input` / `unsupported_skill_version`) without executing. The
   fixture evaluation is prepared without mutating Phase 3 run, prospect, idempotency, or manual-run
   audit collections. The executor return is then treated as untrusted: success requires a real
   integer zero cost and a complete bounded result shape. A representable positive integer cost is
   recorded on the failed run and attempt; negative, Boolean, non-integer, or SQLite-out-of-range
   values fail closed without cost metadata. Malformed or oversized results become visible retryable
   `executor_failure` transitions instead of leaving an attempt `running`. A repository-owned
   non-mutating validator checks the concrete `ManualRun`, audit, every prospect projection, and
   fixture/result consistency before durable success; `commit_prepared_run` reuses the same validator.
   The valid process-local `existing_run` form is accepted and settles the durable worker run without
   duplicating a Phase 3 run, prospect, idempotency entry, or manual-run audit.
4. On success, one atomic transaction persists the output manifest (schema identity, content hash,
   byte length, fixture sources, result IDs, cost, errors, stop reason, validated synthetic result
   snapshot), completes the attempt, marks the run `succeeded`, creates exactly one pending human
   review task, and appends the audit references. Non-mutating preparation includes the prospect's
   existing business-unit-scoped append-only review events, so later snapshots carry the same
   effective review projection as the live queue without changing or duplicating those events.
5. Only after that durable success commits, the prepared result is projected exactly once into the
   same-process Phase 3 queue for governed review actions. Cancellation, validation or cost rejection,
   and rolled-back output/review-task transactions expose no Phase 3 run or prospects.
6. Worker runs, attempt history, output manifests, audit history, and review tasks are inspected at
   `/worker-runs`, `/worker-runs/{id}`, `/review-tasks`, and `/review-tasks/{id}`; the registry is
   at `/registry` and `/registry/brand-prospecting-agent`.

The loopback server handles each request on a bounded thread (no scheduler, poller, or background
worker), so a human can open the run detail or submit a cancellation while an attempt is running.
Server shutdown joins every request thread before returning; attempts always terminate
cooperatively by success, failure, timeout, or cancellation, so no worker survives the process. The
process-local fixture repository is serialized behind a reentrant lock under this bounded
concurrency.

## Durable review inspection after restart

Worker-run and review-task pages render a **read-only durable result projection** directly from the
persisted validated snapshot, so a pending review task and its output remain inspectable —
business-unit scoped — after an application restart. Governed review actions (identity resolution,
suppression, deeper-research approval, rejection, assignment, notes) still operate on the
process-local Phase 3 prospect queue populated by the server process that executed the run; after a
restart those actions are unavailable for that run's results, and the durable snapshot is the
review record. Every read verifies the exact stored snapshot bytes against both the persisted byte
length and SHA-256 content hash before parsing or rendering; a mismatch returns a safe bounded error
without changing the terminal run or durable history. Durable rows display the effective governed
decision, including prior rejection or approval, and give effective suppression the highest visible
disposition precedence rather than relabeling protected work as pending or eligible. The pages state
the post-restart action limitation explicitly instead of dead-linking the user.

## Run state machine

States: `queued`, `running`, `succeeded`, `failed_retryable`, `failed_terminal`, `timed_out`,
`cancelled`. A successful run with a pending review task is displayed as `succeeded · review
pending`; the review-task status is the single source of truth for review state.

| From | To | Trigger |
| --- | --- | --- |
| (new request) | `queued` | validated manual request |
| `queued` | `running` | atomic attempt claim (appends attempt N) |
| `queued` | `cancelled` | manual cancellation before execution |
| `running` | `succeeded` | atomic output + review-task + audit commit |
| `running` | `failed_retryable` | executor/storage interruption |
| `running` | `failed_terminal` | validation/policy/cost failure |
| `running` | `timed_out` | cooperative deadline exceeded |
| `running` | `cancelled` | cooperative cancellation checkpoint |
| `failed_retryable` / `timed_out` | `running` | manual retry while attempt budget remains (appends attempt N+1) |

Every transition is a conditional atomic update; a double claim or a success/cancel race has
exactly one winner. Terminal states never silently return to running, and `succeeded`,
`failed_terminal`, and `cancelled` accept no further execution.

## Timeout, cost, retries, cancellation, idempotency

- **Timeout** — server-owned; checked cooperatively between bounded executor steps against an
  injected clock. A timed-out attempt commits no output or review task and is manually retryable
  while budget remains. Python is not claimed to forcibly kill arbitrary code; the authorized
  executor is cooperative and bounded.
- **Cost** — the cap is exactly zero dollars. A SQLite-representable positive integer reported by the
  executor fails closed with no output or process-local projection and is recorded exactly and
  atomically on both the logical run and attempt. Invalid or SQLite-unrepresentable cost reports fail
  closed with those fields unset.
- **Retries** — `max_attempts` is 3 in total; retries are always manual, create append-only
  attempts under the same logical run, and never duplicate outputs, discovery records, review
  tasks, or logical runs (the deterministic adapter's idempotency guarantees single discovery).
  Exhaustion is visible and blocks further attempts. The atomic retry claim clears stale
  terminal-only metadata (completion time, failure class, retryability, remediation) while
  preserving the first-start time and all earlier attempt rows, and the `retry_accepted` audit
  commits inside the same claim transaction — a lost claim race can never leave a stale acceptance
  fact, and an audit fault rolls the whole claim back.
- **Cancellation** — queued work cancels immediately; running work receives a cooperative request
  through the real loopback HTTP surface and honors it at the next checkpoint. Cancellation after a
  committed success returns a safe conflict and preserves the output. Cancelled work persists no
  partial output, projects no Phase 3 run or prospects, and does not consume a retry.
- **Idempotency** — keys are **global across business units by contract**. A new key plus request
  creates one logical run; replaying the same key and fingerprint returns the existing run (with a
  bounded `idempotent_replay` audit fact) without duplicate execution; reusing the key with
  different input fails with a safe `409 idempotency_conflict`. A collision with a run in a
  business unit the caller cannot access returns the same generic 409 and records only an
  **unlinked** rejection fact scoped to the caller — it never appends to, alters, identifies, or
  discloses the foreign run or its audit history. Creation is concurrency-safe at the SQLite
  boundary: two simultaneous identical submissions produce one logical run and one idempotent
  replay (never a 500), and simultaneous conflicting reuse produces one run plus one safe conflict.
  Phase 5 preserves this finalized manual fingerprint exactly; its separate scheduled-shadow
  identity does not add a field to, or invalidate, an existing version-1 manual fingerprint.

## Failure recovery

Failures carry a safe class (for example `executor_failure`, `timeout`, `cost_limit_exceeded`,
`transaction_rolled_back`, `storage_unavailable`, `interrupted_execution_recovered`), retryability,
and a redacted remediation hint — never payloads, contact values, secrets, SQL, local paths, or
tracebacks. Invalid executor result shapes and oversized result snapshots use the existing retryable
`executor_failure` taxonomy; invalid cost reports use terminal `cost_limit_exceeded`, with metadata
stored only for a positive SQLite-representable integer. On startup, any run left `running` by a prior process exit is reconciled: the abandoned
attempt is marked `interrupted`, the run becomes a visible `failed_retryable`, the recovery is
audited, and nothing re-executes without a manual human retry. Because attempts replay from the
durable validated input, that manual retry succeeds in the fresh process even though every Phase 3
in-memory collection is empty. This remains the Phase 4 manual-run contract. Phase 5 scheduled runs
are additionally linked to one occurrence and never permit manual retry, even while the occurrence
is claimed; the service fails with 409 before another attempt claim so occurrence settlement remains
the only terminal authority. If a scheduled output later fails its integrity manifest, Phase 5 marks
that linked run `failed_terminal` and invalidates its pending review task. These scheduled-only rules
do not change retry behavior for an unlinked Phase 4 manual run.

## Security and business-unit boundaries

The Phase 3 fixture actor model remains a policy simulation, not production authentication. Noah
spans both business units, Rob is UMG-scoped, Dan is Talent-scoped, and unknown actors fail closed.
Cross-business-unit reads, starts, retries, cancellations, outputs, review tasks, and audits are
denied server-side. The worker cannot approve, complete, or impersonate human review, and its
output cannot weaken suppression, cooldown, relationship, identity, score, rights, roster,
named-talent, or brand-safety protections. CSRF, strict methods and content type, bounded bodies,
escaped HTML, restrictive headers, and loopback-only binding all still apply.

## Verification

```bash
PYTHONPYCACHEPREFIX=/tmp/unreal-prospecting-phase4-pycache \
  python3 -m unittest discover -s tests/prospecting -p 'test_phase4_registered_agent.py' -v

PYTHONPYCACHEPREFIX=/tmp/unreal-prospecting-phase4-pycache \
  python3 -m unittest discover -s tests/prospecting -p 'test_phase3_mission_control.py' -v

PYTHONPATH=/tmp/unreal-prospecting-pyyaml \
PYTHONPYCACHEPREFIX=/tmp/unreal-prospecting-phase4-pycache \
  bash tests/prospecting/run_all.sh
```

## Non-goals

Phase 4 does not provide live research, scraping, external APIs, Supabase or PostgreSQL access,
external migrations, real prospect or contact data, credentials, scheduled or recurring execution,
Phase 5 shadow mode, creative or likeness generation, advertisements, outreach drafting or sending,
telemetry, or deployment.
