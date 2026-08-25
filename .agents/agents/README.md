# Agent and subagent guidance

No custom subagent runtime definitions are installed. Subagents are scoped helpers for independent search, planning, or review. They inherit `../../AGENTS.md`, hold no approval authority, may not touch external systems, and are never a path around Phase 1 or a safety gate.

Prefer read-only delegation. If edits are explicitly authorized, isolate worktrees, assign non-overlapping directories, cap retries, and require concise evidence rather than raw dumps.
