# Phase 5 Scheduled Loop in Shadow Mode

**Status:** Independently reviewed and finalized at commit `1ddba9037f1db7e1b58098b83f7bf4caeafd7e8d`

Phase 5 adds one repository-local weekly UTC scheduler to the independently finalized Phase 4
registered-agent control plane. It remains synthetic, deterministic, fixture-only, loopback-only,
zero-cost, and shadow-only. No external system, production database, live research, scraping,
credential, real prospect record, approval, enrichment, creative, likeness, advertisement, outreach,
deployment, or invocation of the Phase 6 operational finder exists.

## Start and stop

From the repository root:

```bash
PYTHONPATH=apps/prospecting-mission-control \
  python3 -m mission_control --port 8765
```

Open `http://127.0.0.1:8765/shadow-schedules?actor=noah&business_unit=unreal-media-group`.
The HTTP server binds only to `127.0.0.1`. It starts one non-daemon scheduler thread, but every
schedule is created `disabled`; application startup alone cannot make work due. `Ctrl-C` stops the
scheduler, joins it, closes the server, and joins request threads. No process should remain.

## Human-controlled workflow

1. Create and validate immutable Phase 3 campaign versions for one business unit.
2. Open **Shadow schedules**, configure a bounded campaign-version rotation, one UTC weekday and
   time, a prospect cap from 1 through 15, and an optional open-discovery interval.
3. The schedule is stored disabled. Noah must explicitly select **Enable schedule**. Fixture actor
   selection simulates local policy; it is not authentication or production authorization.
4. At a due boundary, the scheduler atomically claims at most one occurrence, loads governed local
   history, and invokes `RegisteredAgentService` with a stable occurrence idempotency key.
5. Inspect health, occurrences, stop reasons, duplicate rate, and local alerts. Successful output
   creates exactly one durable pending human-review task. The loop cannot approve it.
6. **Pause** preserves the next due value but prevents a new claim. **Resume** calculates the first
   UTC boundary at or after the current time. **Disable** clears the next due value. All transitions
   are conditional, atomic, and append-only audited.

Pause or disable wins when it commits before an occurrence claim. Once a claim commits, that
occurrence finishes under its immutable snapshot even if a later control action pauses or disables
the schedule. Its output remains shadow-only and pending human review.

## Cadence, rotation, and idempotency

- Cadence is exactly one weekday/hour/minute in UTC. There is no cron expression or generic timer.
- Rotation is deterministic. Filtered campaign versions rotate in stored position order; configured
  open-discovery weeks select an approved open campaign version.
- `schedule_id + schedule_version + scheduled_for` derives the occurrence idempotency identity.
  SQLite uniqueness and conditional claims prevent duplicate logical occurrences under repeated or
  concurrent ticks.
- Manual requests retain the finalized Phase 4 fingerprint byte contract. Only scheduled-shadow
  fingerprints add their request kind, so a populated version-1 manual run replays after the
  additive version-2 initialization without conflict or execution.
- Scheduled run creation, occurrence linking, and the acceptance audit share one transaction. A
  failure at the link boundary rolls back the run, link, and audit together, so startup never has
  to infer a missing run link from an idempotency key. Noah is the only scheduled-run creator, and
  the occurrence business unit, campaign family/version, and idempotency key must all match.
- One evaluation reconciles at most one overdue boundary, then advances directly to a future weekly
  boundary. Downtime cannot produce a catch-up storm.
- A shared opportunity identity prevents two schedules from claiming the same business-unit,
  campaign-version, and scheduled time. The Phase 4 store also enforces the worker concurrency cap
  transactionally across service instances.

## History and stops

Before every occurrence, Phase 5 loads the bounded synthetic seed in
`fixtures/prospecting/phase5/history-seeds.json`, merges only durable outputs from the requested
business unit within the shared aggregate snapshot-byte budget, and runs the frozen Phase 1 history
validator. The validated history snapshot and
hash are persisted before run creation. The existing Phase 1 classifier uses that exact snapshot
during fixture evaluation; prior identities therefore cannot be presented as new, while
re-engagement remains governed by existing evidence, cooldown, relationship, and history rules.

Missing, unreadable, directory-valued, or permission-denied history blocks as
`history_unavailable`; malformed, contradictory, or inconsistent history blocks as
`history_invalid`. All post-claim schedule, campaign, history, run-link, and expected local-store
failures settle the occurrence before returning. History failures stop before a worker attempt and
create a bounded local alert, while the scheduler remains alive.
Worker/storage failure, zero-cost-cap violation, interruption recovery, and overlap protection are
also durable and visible. A transient settlement or post-success output-read failure is retried from
bounded in-process state before new work; startup recovery remains the durable crash fallback.
Errors never include raw history, contact values, file paths, or secrets.

`duplicate_count` is the number of result rows with a non-null governed
`duplicate_classification`; `result_count` is every result row, including ordinary qualification,
protection, and cap rejections; and `duplicate_rate = duplicate_count / result_count` (or zero for
an empty result). Below-threshold, missing-evidence, target-cap, rights, and brand-safety rejections
do not enter the numerator solely because they are not new. An identity matched by history does
enter the numerator even when suppression or an existing client, partner, or outreach protection
routes it to rejections. Normal completion and startup recovery use the same metric helper.

Startup recovery reads a successful linked output through the same bounded byte-length, SHA-256,
JSON, and result-shape decoder as every normal durable read. A mismatched or malformed snapshot
settles the occurrence failed as `shadow_output_invalid`, marks schedule health unhealthy, and adds
a bounded audit and local alert; it also moves the linked run from `succeeded` to `failed_terminal`
and invalidates its pending review task, so invalid output cannot remain actionable. It cannot
create completion or duplicate metrics. A run linked to any scheduled shadow occurrence is never
manually retryable, including while the occurrence remains `claimed`; the occurrence owns final
settlement. The service returns 409 before another attempt can be claimed, so stale failure
settlement cannot race a second attempt into a successful output or pending review task. Finalized
Phase 4 manual-run retry behavior is unchanged.

## Additive local SQLite upgrade

Schema version 2 adds only:

- immutable `shadow_schedule_versions` and `shadow_schedule_campaigns`;
- current `shadow_schedules` state and health;
- idempotent `shadow_occurrences` with history/run links and duplicate reporting;
- append-only `shadow_schedule_audits`; and
- business-unit-scoped `shadow_alerts`.

Fresh initialization and a real version-1 Phase 4 file both use the same additive initializer.
Existing Phase 4 runs, attempts, outputs, review tasks, audits, identifiers, snapshots, and integrity
manifests are unchanged. There is no `DROP`, `TRUNCATE`, destructive reconciliation, history rewrite,
delete-and-recreate path, external migration, or database connection.

## UI and safety boundaries

All schedule reads and mutations are business-unit scoped. Noah alone sees configuration and
transition controls. Rob and Dan retain their authorized business-unit schedule/list/detail reads,
but receive explicit read-only copy and no schedule mutation links or forms; forged POSTs still
fail closed server-side. Mutations use the existing bounded form
parser, CSRF token, fixture actor allowlist, conditional row version, escaped server-rendered HTML,
safe status codes, loopback Host check, no-store response policy, and restrictive CSP. The schedule
pages expose truthful disabled, empty, healthy, unhealthy, paused, occurrence, stop, and local-alert
states, distinguish unavailable metrics from numeric zero, and explain that scheduled shadow runs
are not manually retryable even when worker attempt budget remains. Pages use semantic forms, labels,
tables, live status messages, visible focus, and the existing
narrow-layout rules.

The scheduler owns no credential, external client, generic job runner, approval permission, or
outbound capability. It cannot send, draft outreach, enrich, generate creative or likenesses,
advertise, or invoke the Phase 6 operational finder.

## Verification

```bash
PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/unreal-prospecting-skills-pycache" \
  python3 -m unittest discover -s tests/prospecting -p 'test_phase5_shadow_loop.py' -v

PYTHONPATH=/tmp/unreal-prospecting-pyyaml bash tests/prospecting/run_all.sh
```

The Phase 5 suite covers exact UTC boundaries, controls, rotation, history failure, durable
deduplication, caps, retries/idempotency boundaries, concurrency, recovery, additive upgrade,
business-unit isolation, CSRF, safe rendering, local alerts, and joined shutdown without sleeps or
external access. This implementation is independently reviewed and finalized at commit
`1ddba9037f1db7e1b58098b83f7bf4caeafd7e8d`.
