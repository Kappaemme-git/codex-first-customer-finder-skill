# Agent compatibility surface

`../AGENTS.md` is the shared operating contract. This directory exposes canonical Codex skills and durable guidance adapted from Unreal OS without copying its unrelated runtime, database, company-approval, or deployment controls.

| Surface | Location | Status |
| --- | --- | --- |
| Canonical skills | `skills/` | Phase 1 implementations |
| Subagent guidance | `agents/README.md` | Policy guidance only |
| Command guidance | `commands/README.md` | No invented slash-command runtime |
| Safety validators | `hooks/` | Manual validators; not automatically wired |
| Reference map | `reference/README.md` | Repository references only |
| Model allocation | `MULTI_MODEL_ROLE_ALLOCATION_RECOMMENDATIONS.md` | Prompt-authoring guidance |

Policy remains authoritative when a host does not wire the manual validators. `.agents/skills/` is canonical; Claude compatibility is deferred until a deterministic, non-duplicating need is proven.
