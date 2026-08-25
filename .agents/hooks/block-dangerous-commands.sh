#!/usr/bin/env bash
set -euo pipefail

input=$(cat)
if printf '%s' "$input" | grep -Eiq '(git[^;|&]*[[:space:]](push|remote|reset|clean|stash)([[:space:]]|$)|rm[[:space:]]+(-[^[:space:]]*r[^[:space:]]*f|-rf|-fr)([[:space:]]|$)|curl([[:space:]]|$)|cron(tab)?|launchctl|supabase|openclaw|deploy|send(mail)?|gh[^;|&]*[[:space:]]pr([[:space:]]|$))'; then
  printf '%s\n' 'BLOCKED: command may cross a Phase 1 or repository safety boundary.' >&2
  exit 2
fi
printf '%s\n' 'OK: no blocked command family detected.'
