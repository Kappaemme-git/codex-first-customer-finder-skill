#!/usr/bin/env bash
set -euo pipefail

root=$(git rev-parse --show-toplevel)
cd "$root"
PROSPECTING_PYCACHE="${TMPDIR:-/tmp}/unreal-prospecting-skills-pycache"
export PYTHONPYCACHEPREFIX="$PROSPECTING_PYCACHE"
python_bin="${PROSPECTING_PYTHON:-python3}"

bash -n scripts/check-upstream.sh
bash -n scripts/sync-upstream.sh
bash -n .agents/hooks/block-dangerous-commands.sh
bash -n .agents/hooks/block-sensitive-input.sh
bash -n .agents/hooks/log-task-summary.sh
node --check scripts/install.js
node --check scripts/install-unreal.js
"$python_bin" -m compileall -q shared/prospecting-core .agents/skills first-customer-finder/scripts tests/prospecting
"$python_bin" -c 'import json, pathlib; [json.loads(path.read_text(encoding="utf-8")) for path in pathlib.Path("shared/prospecting-core/schemas").glob("*.json")]'
"$python_bin" -m unittest discover -s tests/prospecting -p 'test_*.py' -v
SKILL_VALIDATOR="${SKILL_VALIDATOR:-${CODEX_HOME:-${HOME}/.codex}/skills/.system/skill-creator/scripts/quick_validate.py}"
[ -f "$SKILL_VALIDATOR" ] || { printf 'Missing skill validator: %s\n' "$SKILL_VALIDATOR" >&2; exit 1; }
"$python_bin" -c 'import yaml' 2>/dev/null || { printf 'PyYAML is required for the official skill validator. Install requirements-dev.txt or set PROSPECTING_PYTHON.\n' >&2; exit 1; }
"$python_bin" "$SKILL_VALIDATOR" .agents/skills/unreal-media-brand-prospector
"$python_bin" "$SKILL_VALIDATOR" .agents/skills/unreal-talent-campaign-prospector
