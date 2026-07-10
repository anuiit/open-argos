---
name: mos-config
description: Show or safely modify local mosaic model configuration from Codex. Use `mosaic config show`, `mosaic config set-model`, and `mosaic config set-mode`.
---

Manage mosaic model configuration safely.

Commands:
- Show effective config: `mosaic config show`
- JSON config summary: `mosaic config show --json`
- Set a logical model route: `mosaic config set-model <mosaic> --kind <opencode|claude|agy> --model <model> [--provider <provider>] [--effort <level>] [--command <agy>]`
- Set mode mosaics: `mosaic config set-mode <mode> --mosaic <name> [--mosaic <name> ...]`
- Inspect readiness: `mosaic doctor`, `mosaic ping`, and `mosaic providers`

Rules:
1. Preserve mosaic invariants: no Codex subprocesses, no native Ollama CLI, MiniMax only `minimax/MiniMax-M3` with `provider_lock=minimax` / `--provider-lock minimax`.
2. Use `kind=agy`, `provider=agy`, and `command=agy` for Antigravity routes such as `agy_image`.
3. Prefer presets and multi-mosaic modes; only narrow to one mosaic/model for explicit targeted smoke/debug with `--single-ok`.
4. Rely on mosaic validation and backups before reporting success.
5. Run `mosaic doctor` and `mosaic config show --json` after meaningful changes.

6. If mosaic reports `needs_human`, stop and surface the blocker to the user; do not auto-retry or silently fall back.
