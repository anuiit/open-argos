---
name: argos-config
description: Show or safely modify local argos model configuration from Codex. Use `argos config show`, `argos config set-model`, and `argos config set-mode`.
---

Manage argos model configuration safely.

Commands:
- Show effective config: `argos config show`
- JSON config summary: `argos config show --json`
- Set a logical model route: `argos config set-model <argos> --kind <opencode|claude|agy> --model <model> [--provider <provider>] [--effort <level>] [--command <agy>]`
- Set mode argos: `argos config set-mode <mode> --argos <name> [--argos <name> ...]`
- Inspect readiness: `argos doctor`, `argos ping`, and `argos providers`

Rules:
1. Preserve argos invariants: no Codex subprocesses, no native Ollama CLI, MiniMax only `minimax/MiniMax-M3` with `provider_lock=minimax` / `--provider-lock minimax`.
2. Use `kind=agy`, `provider=agy`, and `command=agy` for Antigravity routes such as `agy_image`.
3. Prefer presets and multi-argos modes; only narrow to one argos/model for explicit targeted smoke/debug with `--single-ok`.
4. Rely on argos validation and backups before reporting success.
5. Run `argos doctor` and `argos config show --json` after meaningful changes.

6. If argos reports `needs_human`, stop and surface the blocker to the user; do not auto-retry or silently fall back.
