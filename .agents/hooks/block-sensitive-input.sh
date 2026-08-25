#!/usr/bin/env bash
set -euo pipefail

input=$(cat)
if printf '%s' "$input" | grep -Eiq '(^|[/[:space:]])\.env([./[:space:]]|$)|private[_-]?key|service[_-]?role|authorization[[:space:]]*:[[:space:]]*(bearer|basic)|((api[_-]?key|password|token|secret|client[_-]?secret|access[_-]?key)[[:space:]]*[:=])'; then
  printf '%s\n' 'BLOCKED: sensitive path or credential-shaped input detected.' >&2
  exit 2
fi
printf '%s\n' 'OK: no sensitive input pattern detected.'
