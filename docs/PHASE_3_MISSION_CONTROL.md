# Phase 3 Manual Mission Control

**Status:** Independently reviewed and finalized at commit `8ea7c16`

This is a synthetic review application for the finalized Phase 2 contract behavior. It is not an
Unreal OS connection, production authentication system, database, scheduler, or outbound tool.

**Phase 4 transition note:** the authoritative manual-run path now goes through the locally
registered `brand-prospecting-agent` worker described in
[Phase 4 Registered Agent](PHASE_4_REGISTERED_AGENT.md). The campaign detail form delegates to that
registered agent, which executes the same deterministic fixture adapter and durably records worker
runs, attempts, outputs, audits, and human-review tasks in a local gitignored SQLite file. The
inert Phase 3 registry placeholder was replaced by that registration. Everything else in this
document still describes the review model.

## Start locally

From the repository root:

```bash
PYTHONPATH=apps/prospecting-mission-control \
  python3 -m mission_control --port 8765
```

Open `http://127.0.0.1:8765`. The server always binds to loopback. Stop it with `Ctrl-C`. All campaign,
run, projection, and review-event state is held in memory and resets when the process stops.

## Local review model

- Campaign submissions construct a complete Phase 1 configuration and call the frozen Phase 1
  validator.
- Each edit creates an immutable campaign version with a configuration hash.
- A human must select **Start fixture dry run**. No background execution path exists.
- Open and filtered campaigns select different deterministic synthetic results. An unmatched filter
  produces a visible `no_results` run.
- New, duplicate/re-engagement, and rejection queues partition every result from a run.
- Governed identity, suppression, deeper-research, rejection, assignment, and note actions append
  history. Corrections explicitly supersede an existing event without deleting it.
- Current state is selected by effective time, recorded time, and stable event ID.
- The Agent Registry shows the Phase 4 `brand-prospecting-agent`, registered for manual synthetic
  execution only, with a zero cost cap and no credentials, network, schedule, recurring loop,
  creative, likeness, or outreach capability.

The Noah, Rob, and Dan selector is an allowlisted fixture mechanism for exercising business-unit scope
and separation of duty. It is deliberately labeled as **not authentication**. Noah can review both
business units, Rob only UMG, and Dan only Talent. Production routes and real authorization are later
work.

## Routes and workflow

| Route | Purpose |
| --- | --- |
| `/campaigns` | List campaigns in the selected business unit |
| `/campaigns/new` | Create an open or filtered campaign version |
| `/campaigns/{family}/{version}` | Inspect configuration and start a dry run |
| `/runs` and `/runs/{id}` | Inspect versions, sources, outputs, zero cost, errors, and stop reason |
| `/prospects?queue=...` | Review new, duplicate/re-engagement, or rejection queues |
| `/prospects/{id}` | Inspect evidence and append governed review events |
| `/registry` and `/registry/{agent}` | Inspect the registered manual-only agent and capabilities |
| `/worker-runs` and `/worker-runs/{id}` | Inspect durable worker runs, attempts, outputs, audits |
| `/review-tasks` and `/review-tasks/{id}` | Inspect pending human-review tasks |

Recommended local review sequence:

1. Create a UMG open campaign as Noah and start a fixture dry run.
2. Inspect all three queues, result evidence, zero cost, partial errors, and stop reason.
3. Resolve the listed duplicate identity without deleting either identity.
4. Apply suppression and confirm deeper-research approval fails closed.
5. Switch to Rob to approve an eligible Noah-proposed UMG result, then append rejection, assignment,
   and note events.
6. Create a Talent filtered campaign for `sports apparel` or `sports beverage`; confirm archetype-only
   output and blocked named-person, rights-conflict, and brand-safety states.
7. Use an unmatched vertical to confirm the visible no-results run.

## Safety boundary

Every mutating form uses a process-local CSRF token. Requests have bounded bodies and fields, strict
methods and content type, allowlisted actors, server-enforced business-unit scope, safe local errors,
and escaped HTML. Evidence URLs must be credential-free HTTP(S) values and are displayed without being
fetched. The application has no external request client, arbitrary file access, shell execution,
dynamic evaluation, open redirect, privileged browser client, service-role key, contact value, or real
prospect data.

## Verification

```bash
python3 -m unittest discover -s tests/prospecting -p 'test_phase3_mission_control.py' -v
python3 -m compileall -q apps/prospecting-mission-control shared/prospecting-core tests/prospecting
bash tests/prospecting/run_all.sh
```

The fixtures use invented organizations, synthetic identities, and `.example` domains only. No
migration file is required because the sole active Phase 3 adapter is process-local.

## Later-phase non-goals

Phase 3 does not provide live research, scraping, external APIs, external database access, migration
execution, real authentication, production authorization, schedules, loops, watchers, creative
briefs, asset generation, advertisements, likeness use, outreach drafting, outreach sending,
telemetry, or deployment. Registered manual worker execution and durable local worker state are
Phase 4 behavior, documented separately and pending independent review; Phase 5 remains
unauthorized.
