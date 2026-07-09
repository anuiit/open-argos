---
name: adv-config
description: Show or safely modify local advisor model configuration from Codex. Use `advisor config show`, `advisor config set-model`, and `advisor config set-mode`.
---

Manage advisor model configuration safely.

Commands:
- Show effective config: `advisor config show`
- JSON config summary: `advisor config show --json`
- Set a logical model route: `advisor config set-model <advisor> --kind <opencode|claude|agy> --model <model> [--provider <provider>] [--effort <level>] [--command <agy>]`
- Set mode advisors: `advisor config set-mode <mode> --advisor <name> [--advisor <name> ...]`
- Inspect readiness: `advisor doctor`, `advisor ping`, and `advisor providers`

Rules:
1. Preserve advisor invariants: no Codex subprocesses, no native Ollama CLI, MiniMax only `minimax/MiniMax-M3` with `provider_lock=minimax` / `--provider-lock minimax`.
2. Use `kind=agy`, `provider=agy`, and `command=agy` for Antigravity routes such as `agy_image`.
3. Prefer presets and multi-advisor modes; only narrow to one advisor/model for explicit targeted smoke/debug with `--single-ok`.
4. Rely on advisor validation and backups before reporting success.
5. Run `advisor doctor` and `advisor config show --json` after meaningful changes.

6. If advisor reports `needs_human`, stop and surface the blocker to the user; do not auto-retry or silently fall back.
