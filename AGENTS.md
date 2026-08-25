# Repository Agent Contract

This repository contains the upstream `first-customer-finder` skill plus Unreal's completed Phase 6 finder/researcher workflow. The roadmap and finalized compatibility specifications under `docs/specs/` control scope. This repository finds, filters, deduplicates, researches, and reports leads; it does not implement Unreal OS or downstream creative, outreach, CRM, or orchestration agents.

## Operating principles

1. Read and inspect before editing.
2. Use the smallest complete diff and reuse the shared prospecting core.
3. Keep the upstream skill functional and avoid edits under `first-customer-finder/` unless a verified regression requires one.
4. Treat policy as authoritative even when the host does not mechanically enforce it.
5. Log completed tasks without credentials, private contact data, or sensitive values.

## Risk tiers

- **Green:** read-only work and reversible repository file changes. Proceed and log.
- **Yellow:** local side effects outside ordinary repository editing, generated material intended for external use, or ambiguous actions. Stop for explicit approval.
- **Red:** sends, posts, deployments, external writes, remotes, pushes, credentials, destructive actions, likeness use, or autonomous outreach. Stop; these are outside the finder/researcher boundary.

## Mandatory session start and synchronization

At the beginning of every session, run `bash scripts/check-upstream.sh`.

Before any file-changing work, run `bash scripts/sync-upstream.sh`.

If synchronization cannot complete safely, stop and report the blocker. A dirty worktree may pass only
when fresh validation proves synchronization is already complete and the script performs no branch,
index, or worktree mutation. Dirtiness blocks before any required switch, fast-forward, or merge, and
interrupted Git state always blocks. A successful dirty no-op neither infers change ownership nor grants
authority over unrelated files. Preserve all user changes and task-specific path limits. Do not bypass
the script with reset, force, stash, clean, remote changes, manual conflict guessing, or destructive
commands.

Read-only analysis may continue after a successful check. File-changing work may not begin until safe synchronization passes. During the documented first-session bootstrap, follow the bootstrap checks in the Phase 1 build prompt because these scripts do not exist yet.

## Task lifecycle

1. Restate the requested outcome and authorized phase.
2. Classify risk and confirm local Build mode.
3. Inspect relevant files, callers, tests, specs, and existing patterns.
4. Define success criteria and plan the smallest complete change.
5. Execute only authorized repository changes.
6. Run proportionate verification and review the final diff.
7. Append a scrubbed entry to `logs/execution/PROSPECTING_SKILLS_EXECUTION_LOG.md`.

## Phase control

Phase 1 remains frozen at checkpoint `f77236a`. Phase 2 design is independently reviewed and finalized in the three `docs/specs/UNREAL_OS_PROSPECTING_*.md` compatibility-contract documents; it authorizes no Unreal OS edit. Phase 3 is independently reviewed and finalized at commit `8ea7c16`; it is synthetic, deterministic, fixture-only, loopback-only, manually initiated, and not production authentication or authorization. Phase 4 is independently reviewed and finalized at current-lineage commit `b7892aed5ad9ab0dcb9d900d95d6971332582ef8`: one locally registered `brand-prospecting-agent` worker executes the Phase 3 fixture adapter behind a durable local gitignored SQLite control plane with timeout, zero cost cap, retry cap, cancellation, idempotency, audit transactions, and startup recovery (`docs/PHASE_4_REGISTERED_AGENT.md`). Phase 5 is independently reviewed and finalized at commit `1ddba9037f1db7e1b58098b83f7bf4caeafd7e8d`: one disabled-by-default, human-configured, weekly UTC shadow loop reuses that worker with durable schedule/occurrence/audit state, bounded history-aware fixture execution, and pending human review (`docs/PHASE_5_SHADOW_LOOP.md`). Phase 6 is the operational UMG finder/researcher release described in `docs/PHASE_6_OPERATIONAL_FINDER.md`: it reuses the original local campaign/history/report contracts and adds an evidence-backed product-photography/product-video filter with UGC-ad exclusion. The former dossier, live-proof, source-plan, claim-projector, approval, and graph-package machinery is retired and must not be reintroduced. External-system connections or migrations, private contact data, credentials, generic cron, autonomous crawling, creative generation, real-person likeness, advertisements, outreach, deployment, downstream invocation, Unreal OS edits, and other external writes remain prohibited.

## Planning and editing

- State only assumptions that change behavior.
- Search before reading broadly; inspect focused ranges and existing callers.
- Prefer the standard library and existing repository code.
- Keep business-unit reasoning in the relevant skill; keep shared deterministic behavior under `shared/prospecting-core/`.
- Do not add speculative configuration, duplicate helpers, dependencies, unrelated refactors, or unrelated formatting.
- Never silently weaken validation to meet a requested prospect count.

## Dirty worktree and Git protection

- Preserve all user changes. Never reset, clean, stash, discard, or overwrite them.
- Do not stage, commit, tag, rebase, push, create a pull request, or change remotes unless the user explicitly authorizes that exact action.
- `scripts/sync-upstream.sh` may create only a local merge commit needed to merge updated `main` into `unreal`.
- `main` is the upstream mirror; `unreal` is the Unreal implementation branch.

## Verification

Run targeted tests first, then the complete Phase 1 test suite when shared behavior changes. Syntax-check shell and Python, validate JSON schemas and fixtures, generate both report formats for both skills, test installers in temporary directories, exercise upstream scripts only in temporary repositories, and inspect status, changed names, diff statistics, and targeted diffs. Never claim a check passed unless it ran and passed.

## Skill development

- `.agents/skills/` is canonical.
- Each skill requires a concise `SKILL.md`, matching `agents/openai.yaml`, only necessary references/scripts, and successful `quick_validate.py` validation.
- Load history before qualification. Missing or invalid history fails closed.
- Save new, duplicate, re-engagement, suppressed, and rejected outcomes.
- Do not duplicate shared deterministic Python logic inside skills.

## Evidence, browsing, privacy, and contact data

- Use intentionally public business sources and open original sources when practical.
- Search snippets are discovery aids, not final evidence.
- Separate observation, inference, uncertainty, and internal-rights-review status.
- Comprehensive UMG research covers every material public business fact relevant to qualification or records the gap explicitly; it never means guessing.
- Apply `opportunity_filter` only after history classification. Search intent is not evidence, and every `opportunity_match` must cite a preserved result signal.
- Respect access controls, site restrictions, and source dates.
- Do not use private data, paid enrichment, personal contact details, secrets, authenticated scraping, or sensitive traits.
- Never commit personal emails, phone numbers, credentials, or real prospect records. Fixtures must be synthetic.

## Outreach, talent, loops, and schedules

- Never send, post, submit a form, create a CRM record, or autonomously contact anyone.
- Without an approved roster, recommend only a category or archetype. Never name real talent, imply availability, generate a likeness, or imply approval.
- Phase 5 permits only the repository-local scheduler described in `docs/PHASE_5_SHADOW_LOOP.md`: disabled by default, explicitly human-enabled, one weekly UTC cadence, synthetic fixtures, zero cost, shadow-only output, and joined shutdown.
- Do not build or start any other loop, watcher, generic cron job, runner, daemon, background campaign, external scheduler, live-proof worker, crawler, creative generator, outreach worker, graph orchestrator, or downstream consumer.

## Escalation and stop rules

Stop and report the exact blocker when history is unavailable, configuration is contradictory, identity
is ambiguous, evidence cannot be verified, rights or brand-safety risk is unresolved, synchronization
is unsafe, a secret is encountered, or the task would exceed the currently authorized phase or boundary
or affect an external system. Do not improvise around the boundary.

## Parallel agents and worktrees

Use parallel agents only for independent, bounded work. They inherit this contract and receive no additional authority. Keep review or prompt-authoring agents read-only. If more than one agent may edit, use isolated worktrees and avoid overlapping paths.

## Prompts for a second Codex model

Read `.agents/MULTI_MODEL_ROLE_ALLOCATION_RECOMMENDATIONS.md` first. State outcome, scope, phase, allowed paths, acceptance criteria, evidence already gathered, checks already run, required verification, bounded retries, and stop conditions. Choose the lowest-cost capable model class; model choice never expands permissions, phase authority, or approval authority. A prompt-writing or review model may not edit, push, send, or advance phases.
