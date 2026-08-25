#!/usr/bin/env bash
set -euo pipefail

EXPECTED_UPSTREAM='https://github.com/Kappaemme-git/codex-first-customer-finder-skill.git'

fail() {
  printf 'BLOCKED: %s\n' "$1" >&2
  exit 1
}

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail 'not inside a git repository.'
root=$(git rev-parse --show-toplevel)
[ -f "$root/package.json" ] || fail 'expected package.json is missing.'
[ -d "$root/first-customer-finder" ] || fail 'expected first-customer-finder directory is missing.'
grep -Eq '"name"[[:space:]]*:[[:space:]]*"codex-first-customer-finder-skill"' "$root/package.json" || fail 'package.json does not identify the expected repository.'

git remote get-url origin >/dev/null 2>&1 || fail 'origin remote is missing.'
raw_upstream=$(git config --get remote.upstream.url || true)
[ -n "$raw_upstream" ] || fail 'upstream remote is missing.'
effective_upstream=$(git remote get-url upstream || true)

case "$raw_upstream" in
  "$EXPECTED_UPSTREAM"|https://github.com/Kappaemme-git/codex-first-customer-finder-skill|git@github.com:Kappaemme-git/codex-first-customer-finder-skill.git|ssh://git@github.com/Kappaemme-git/codex-first-customer-finder-skill.git) ;;
  *) fail 'upstream fetch URL does not match the approved original repository.' ;;
esac
[ "$effective_upstream" = "$raw_upstream" ] || fail 'Git URL rewriting changes the approved upstream destination.'

git fetch upstream --prune
git show-ref --verify --quiet refs/heads/main || fail 'local main branch is missing.'
git show-ref --verify --quiet refs/remotes/upstream/main || fail 'upstream/main is missing after fetch.'
git show-ref --verify --quiet refs/heads/unreal || fail 'local unreal branch is missing.'

branch=$(git branch --show-current)
if [ -n "$(git status --porcelain)" ]; then cleanliness='dirty'; else cleanliness='clean'; fi
read -r main_ahead main_behind < <(git rev-list --left-right --count main...upstream/main)
if git merge-base --is-ancestor main unreal; then contains_main='yes'; else contains_main='no'; fi

if [ "$main_behind" -gt 0 ] || [ "$contains_main" = 'no' ]; then sync_required='yes'; else sync_required='no'; fi

printf 'Current branch: %s\n' "$branch"
printf 'Worktree: %s\n' "$cleanliness"
printf 'Local main vs upstream/main: ahead=%s behind=%s\n' "$main_ahead" "$main_behind"
printf 'Unreal contains local main: %s\n' "$contains_main"
printf 'Upstream synchronization required: %s\n' "$sync_required"

[ "$main_ahead" -eq 0 ] || fail 'local main is ahead of upstream/main; manual review is required.'
