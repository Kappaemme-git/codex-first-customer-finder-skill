#!/usr/bin/env bash
set -euo pipefail

summary=$(cat | tr '\n' ' ' | sed -E 's/(authorization[[:space:]]*:[[:space:]]*(bearer|basic))[[:space:]]+[^ ,;]+/\1 <REDACTED>/Ig; s/(api[_-]?key|password|token|secret|service[_-]?role|client[_-]?secret|access[_-]?key)[[:space:]]*[:=][[:space:]]*[^ ,;]+/\1=<REDACTED>/Ig' | cut -c1-500)
printf -- '- %s | %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$summary"
