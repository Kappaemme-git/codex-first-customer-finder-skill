# Manual safety validators

These scripts are repository-discoverable manual validators. The repository does not prove that Codex, Claude, or another host runs them automatically.

- `block-dangerous-commands.sh`: rejects destructive, remote-changing, push, scheduler, deployment, and outbound command patterns.
- `block-sensitive-input.sh`: rejects secret-file references and common credential-shaped assignments without printing values.
- `log-task-summary.sh`: emits a scrubbed one-line summary suitable for manual append-only logging.

Syntax-check with `bash -n .agents/hooks/*.sh`. Runtime policy remains in `AGENTS.md`.
