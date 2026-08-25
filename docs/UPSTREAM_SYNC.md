# Safe upstream synchronization

## Branch strategy

- `main` is an exact fast-forward-only mirror of `upstream/main`.
- `unreal` contains Unreal-specific governance, skills, shared utilities, fixtures, tests, and docs.
- `origin` is the fork. `upstream` must normalize to `https://github.com/Kappaemme-git/codex-first-customer-finder-skill.git`.

## Every session

Run:

```bash
bash scripts/check-upstream.sh
```

Before editing, run:

```bash
bash scripts/sync-upstream.sh
```

The check validates the repository and remotes, fetches upstream, and reports branch, cleanliness, main divergence, Unreal ancestry, and whether synchronization is needed. It never switches, merges, commits, pushes, or changes remotes.

The sync script always refuses interrupted Git operations, unexpected branches, divergent local `main`,
and unsafe remotes. After fresh validation, it recomputes whether synchronization would require a branch
switch, fast-forward, or merge. If synchronization is already complete, the script performs a true
no-op: it does not switch branches or alter the branch refs, index, or worktree, and either a clean or
dirty worktree may pass. A successful dirty no-op does not identify who owns any change and does not
grant authority to edit unrelated dirty files; task-specific allowed paths and preservation rules still
apply.

If synchronization requires any Git mutation, a dirty worktree blocks before the first branch switch,
fast-forward, or merge. From a clean `unreal` worktree the script fast-forwards `main`, returns to
`unreal`, and merges `main` only when needed. It never rebases, resets, forces, cleans, stashes, pushes,
or changes remotes. A conflict is aborted and reported for manual review. `--maintenance` follows the
same rule: a dirty invocation succeeds only when the main mirror is already current and no mutation is
required.

Each successful run appends a scrubbed entry to the ignored repository-local `logs/execution/PROSPECTING_SKILLS_SYNC_LOG.local.md`. Keeping machine-local sync events out of tracked state makes repeated no-op synchronization idempotent.

`--maintenance` is intentionally narrow: it may be used only when starting on `main`, and performs the mirror update without merging into `unreal`.

Temporary-repository tests patch only their copied check script to approve a temporary local upstream. Production checks reject Git URL rewriting that changes the effective approved destination. Tests never target this working copy.
