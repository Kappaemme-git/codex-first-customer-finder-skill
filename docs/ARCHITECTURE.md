# Prospecting repository architecture

## Boundary

Phase 6 is the operational release of the original local research and validation layer. It reuses the frozen Phase 1 JSON contracts and adds one UMG opportunity filter; it contains no live-proof runtime, network writer, creative generator, likeness workflow, CRM, outreach system, or downstream orchestrator.

```text
Campaign JSON + local history JSON
              |
              v
    validate configuration/history ---- fail closed
              |
              v
  public-source research by selected skill
              |
              v
 normalize identity -> classify duplicate/relationship/re-engagement
              |
              v
 optional UMG opportunity filter (evidence-linked include/exclude)
              |
              v
 business-specific evidence review + weighted scoring
              |
              v
 validated result + rejection/duplicate audit records
              |
              v
     JSON -> escaped Markdown / HTML
              |
              v
          human review only
```

The retained `run_metadata.phase: 1` value is the compatibility version of these original report contracts. Phase 3 adds a separate local review surface without changing the finder pipeline:

```text
ordinary loopback POST form
           |
           v
bounded parser + CSRF + fixture actor/BU policy
           |
           v
existing Phase 1 campaign validator
           |
           v
MissionControl application service
           |
           v
FixtureRepository interface implementation
  | immutable campaign versions
  | append-only manual run facts
  | deterministic BU projections
  | append-only governed review events
           |
           v
escaped server-rendered HTML on 127.0.0.1
```

The UI depends on the repository boundary rather than fixture arrays. A later governed adapter can
implement the same boundary. Fixture actor selection is a policy simulation for local review, not
authentication.

Phase 4 places that same fixture adapter behind one locally registered, manually triggered worker
without changing the frozen Phase 1 pipeline or the Phase 3 review model:

```text
human loopback request (campaign detail form)
           |
           v
bounded server validation + CSRF + fixture actor/BU policy
           |
           v
registered agent lookup (brand-prospecting-agent, server-owned BU→skill binding)
           |
           v
durable logical run creation (SQLite, idempotency key + request fingerprint)
           |
           v
bounded one-shot cooperative worker attempt (timeout, zero cost cap, retry cap, cancellation)
           |
           v
non-visible prepared evaluation from the existing Phase 3 deterministic fixture adapter
           |
           v
post-executor cost, shape, and bounded-snapshot trust validation
           |
           v
atomic output + attempt + audit + human-review-task transaction
           |
           v
exactly-once same-process Phase 3 projection after durable success
           |
           v
human-visible run/attempt/recovery state on 127.0.0.1
```

Worker-run, attempt, output, review-task, and audit state is durable in a local, gitignored SQLite
file with additive schema versioning. Every attempt replays the run's durable validated input
(hash-checked configuration snapshot, frozen-validator revalidation, server-owned skill binding and
integrity manifest), so manual retries and recovery work after a real process restart, and the
durable result snapshot keeps outputs and pending review tasks inspectable when the process-local
Phase 3 queues are gone. Every durable output read verifies the stored snapshot bytes against its
byte-length and SHA-256 manifest before parsing or rendering. Prepared snapshots reuse existing
business-unit/prospect-scoped append-only review events, so their effective decision matches the
live projection without mutating review history. One repository-owned non-mutating validator checks
the concrete prepared-run/audit/prospect shape and executor consistency both before durable success
and before process-local commit, while accepting the no-duplicate `existing_run` form. Invalid cost
or executor output is converted into a completed durable failure attempt before it can reach SQLite
output persistence. Durable disposition rendering prioritizes suppression, then governed decision,
then protection/pending fallbacks. Fixture
evaluation stays non-visible until the durable success transaction
commits; only that winning success projects the Phase 3 run, prospects, idempotency entry, and
manual-run audit. Failed, cancelled, rejected, and rolled-back attempts leave those collections
unchanged. The loopback server handles requests on bounded, joined threads — no
scheduler, poller, or background worker — so a human can cancel a running cooperative attempt over
HTTP; the process-local fixture repository is serialized behind a reentrant lock. Phase 4 still
contains no database server, external migration, network client, credential, creative, likeness, or
outreach capability, and no fallback from fixtures to production.

Phase 5 adds one deliberately narrow scheduler around the finalized Phase 4 service. It is not a
parallel runner framework and does not change the Phase 1 schemas or Phase 2 contracts:

```text
human configures immutable campaign rotation (disabled)
           |
           v
explicit enable / pause / resume / disable (conditional SQLite transition + audit)
           |
           v
one joined non-daemon scheduler thread evaluates one weekly UTC boundary
           |
           v
atomic occurrence claim (stable schedule+occurrence idempotency; no catch-up storm)
           |
           v
load + validate synthetic seed history and durable same-BU Phase 4 output history
           |
           v
RegisteredAgentService (manual fingerprint preserved; scheduled run/link/audit atomic)
           |
           v
durable shadow occurrence + health + local alert + duplicate rate
           |
           v
pending human-review task only
```

The scheduler starts with the loopback process but schedules default to `disabled`; only Noah's
explicit local fixture action can enable one. Cadence is fixed to one weekday/hour/minute in UTC,
not generic cron. Each evaluation claims at most one due occurrence and advances directly to a
future weekly boundary, preventing catch-up storms. Campaign configurations are copied into an
immutable schedule-version snapshot and hash-checked again by the registered agent before execution.
History is validated before each attempt and then applied by the existing Phase 1 duplicate
classifier so a durable prior identity cannot return to the new queue. Missing, corrupt, ambiguous,
directory-valued, unreadable, or inconsistent history blocks before worker execution and settles
the claim with a local alert without terminating the scheduler. Durable history outputs share one
aggregate snapshot-byte budget, and transient settlement/output-read failures are reconciled before
new work. The local prospect cap is at most
15 and the inherited cost cap remains exactly zero. Duplicate rate counts only rows carrying a
governed identity/history classification over all output rows; ordinary qualification, protection,
and cap rejections are not duplicates merely because they are not new.

SQLite schema version 2 adds schedule versions, campaign rotation snapshots, schedule state,
occurrence claims, schedule audits, and local alerts without altering or deleting a Phase 4 table or
row. Run creation and occurrence linking share one transaction. Startup recovery closes an
interrupted occurrence: a previously committed successful output is preserved only after the normal
length, SHA-256, JSON, result-shape, and duplicate-metric validation; otherwise the occurrence fails
closed with an audit and local alert, the linked run becomes terminally failed, and its pending review
task is invalidated. Scheduled linking is Noah-only and requires an exact business-unit, campaign,
and idempotency match. Every linked scheduled run rejects manual retry before another attempt claim,
including while its occurrence is still claimed; only unlinked Phase 4 manual runs retain manual
retry. Noah alone sees
schedule mutation controls; Rob and Dan receive truthful business-unit-scoped read-only pages. The one
scheduler thread uses an injected clock and stop event, and is stopped and joined before server
shutdown completes. It performs no live research, network request, approval, enrichment, creative,
likeness, advertising, outreach, or invocation of the Phase 6 operational finder.

The former Phase 6 dossier/live-proof/source-plan/claim-projector/approval/graph experiment was removed. It bypassed the actual finder and made a narrow proof failure terminal for an entire candidate. The release architecture keeps public research in the skill, deterministic safety and validation in the shared core, and durable local prospect history as the deduplication authority.

## Ownership

| Concern | Canonical location |
| --- | --- |
| UMG research judgment | `.agents/skills/unreal-media-brand-prospector/` |
| Phase 6 opportunity filter and result validation | `shared/prospecting-core/scripts/validate_campaign.py`, `validate_results.py` |
| Talent/agency/rights judgment | `.agents/skills/unreal-talent-campaign-prospector/` |
| Deterministic contracts and code | `shared/prospecting-core/` |
| Synthetic evaluation data | `fixtures/prospecting/` |
| Regression and safety checks | `tests/prospecting/` |
| Phase 3 local application | `apps/prospecting-mission-control/` |
| Phase 3 synthetic review catalog | `fixtures/prospecting/phase3/` |
| Phase 4 registered worker + durable store | `apps/prospecting-mission-control/mission_control/agent.py`, `store.py` |
| Phase 4 synthetic worker scenarios | `fixtures/prospecting/phase4/` |
| Phase 4 local runtime state (gitignored) | `apps/prospecting-mission-control/local_state/` |
| Phase 5 weekly shadow control plane | `apps/prospecting-mission-control/mission_control/shadow.py`, `store.py` |
| Phase 5 synthetic history seeds | `fixtures/prospecting/phase5/` |
| Original upstream skill | `first-customer-finder/` |

Skill report scripts are thin delegates. The installer places the shared core once at `unreal-prospecting-core`, preventing two business skills from drifting.

## Data contracts

Campaign, controlled roster, history, prospect result, and run report schemas separate company identity, discovery event, public signal, evidence-linked opportunity match, score snapshot, duplicate decision, rejection decision, qualified/re-engagement result, and summary. Runtime validators enforce score/freshness, history, source lineage, include/exclude filtering, shortlist eligibility, handoff readiness, roster compatibility, rights-review, privacy, and summary invariants without adding a dependency.

## Identity limits

The standard library has no public suffix list. Domain normalization handles common service subdomains and a bounded set of common multi-part suffixes. Unknown suffixes, shared storefronts, franchises, and ambiguous company relationships must be reviewed rather than silently merged.

## Claude compatibility

`.agents/skills/` is canonical. The repository does not create manually duplicated `.claude/skills` copies because that would create drift. A deterministic compatibility generator can be evaluated later if a real Claude installation requirement appears.
