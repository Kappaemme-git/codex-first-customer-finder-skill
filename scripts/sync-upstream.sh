#!/usr/bin/env bash
set -euo pipefail

maintenance=false
if [ "${1:-}" = '--maintenance' ]; then
  maintenance=true
  shift
fi
[ "$#" -eq 0 ] || { printf '%s\n' 'Usage: bash scripts/sync-upstream.sh [--maintenance]' >&2; exit 2; }

root=$(git rev-parse --show-toplevel 2>/dev/null) || { printf '%s\n' 'BLOCKED: not inside a git repository.' >&2; exit 1; }
cd "$root"

git_dir=$(git rev-parse --git-dir)
for marker in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG; do
  [ ! -e "$git_dir/$marker" ] || { printf 'BLOCKED: interrupted git operation detected (%s). Resolve it manually.\n' "$marker" >&2; exit 1; }
done
for directory in rebase-apply rebase-merge; do
  [ ! -d "$git_dir/$directory" ] || { printf 'BLOCKED: interrupted git operation detected (%s). Resolve it manually.\n' "$directory" >&2; exit 1; }
done

bash scripts/check-upstream.sh

start_branch=$(git branch --show-current)
if [ "$start_branch" != 'unreal' ] && [ "$maintenance" != true ]; then
  printf 'BLOCKED: run from unreal, or use --maintenance for an intentional main-only mirror update. Current branch: %s\n' "$start_branch" >&2
  exit 1
fi
if [ "$maintenance" = true ] && [ "$start_branch" != 'main' ]; then
  printf '%s\n' 'BLOCKED: --maintenance is allowed only when starting on main.' >&2
  exit 1
fi

read -r main_ahead main_behind < <(git rev-list --left-right --count main...upstream/main)
[ "$main_ahead" -eq 0 ] || { printf '%s\n' 'BLOCKED: local main is ahead of upstream/main; manual review is required.' >&2; exit 1; }
if git merge-base --is-ancestor main unreal; then
  unreal_contains_main=true
else
  unreal_contains_main=false
fi

mutation_required=false
if [ "$main_behind" -gt 0 ] || { [ "$maintenance" != true ] && [ "$unreal_contains_main" != true ]; }; then
  mutation_required=true
fi

if [ "$mutation_required" != true ]; then
  if [ -n "$(git status --porcelain)" ]; then
    merge_result='already synchronized (dirty no-op)'
  else
    merge_result='already synchronized'
  fi
  timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf -- '\n### %s — sync-upstream.sh\n- Task: safe upstream synchronization\n- Phase: repository governance\n- Risk / mode: Green / local Build\n- Approval: script contract\n- Files touched: ignored local synchronization log only; no branch, index, or worktree mutation\n- Commands and checks actually run: remote validation, fetch, branch validation, main divergence check, unreal ancestry check\n- Result: %s\n- Blockers or deferred scope: no push and no remote mutation\n' "$timestamp" "$merge_result" >> logs/execution/PROSPECTING_SKILLS_SYNC_LOG.local.md
  printf 'Synchronization result: %s\n' "$merge_result"
  git status --short
  git rev-list --left-right --count main...upstream/main
  if [ "$unreal_contains_main" = true ]; then
    printf '%s\n' 'Unreal contains local main: yes'
  else
    printf '%s\n' 'Unreal contains local main: no'
  fi
  exit 0
fi

[ -z "$(git status --porcelain)" ] || { printf '%s\n' 'BLOCKED: synchronization requires Git mutations, but the worktree is dirty. Commit or otherwise resolve user changes manually; do not stash, clean, reset, force, or discard them.' >&2; exit 1; }

git switch main
if ! git merge --ff-only upstream/main; then
  git switch "$start_branch" >/dev/null 2>&1 || true
  printf '%s\n' 'BLOCKED: local main cannot fast-forward to upstream/main. Review branch history manually; do not reset or force.' >&2
  exit 1
fi

merge_result='main updated only'
if [ "$start_branch" = 'unreal' ]; then
  git switch unreal
  if ! git merge-base --is-ancestor main unreal; then
    if ! git merge --no-edit main; then
      git merge --abort || true
      printf '%s\n' 'BLOCKED: conflict while merging main into unreal. The merge was aborted. Resolve the upstream changes in a dedicated manual review; do not reset, rebase, or guess.' >&2
      exit 1
    fi
    merge_result='main merged into unreal'
  else
    merge_result='already synchronized'
  fi
else
  git switch "$start_branch"
fi

timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf -- '\n### %s — sync-upstream.sh\n- Task: safe upstream synchronization\n- Phase: Phase 1 governance\n- Risk / mode: Green / local Build\n- Approval: script contract\n- Files touched: git branches only when fast-forward or approved upstream merge was required\n- Commands and checks actually run: remote validation, fetch, fast-forward-only main update, unreal ancestry check\n- Result: %s\n- Blockers or deferred scope: no push and no remote mutation\n' "$timestamp" "$merge_result" >> logs/execution/PROSPECTING_SKILLS_SYNC_LOG.local.md

printf 'Synchronization result: %s\n' "$merge_result"
git status --short
git rev-list --left-right --count main...upstream/main
if git merge-base --is-ancestor main unreal; then
  printf '%s\n' 'Unreal contains local main: yes'
else
  printf '%s\n' 'Unreal contains local main: no'
fi
