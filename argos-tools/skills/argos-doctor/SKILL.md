---
name: argos-doctor
description: Check Argos-Tools/argos readiness after install or when provider/session status is uncertain. Use `argos doctor`, `argos ping`, and `argos providers`.
---

Run a non-destructive Argos-Tools readiness check.

Commands:
- Core readiness: `argos doctor`
- Static model/tool check: `argos ping --json`
- Provider slots/status: `argos providers --json`
- Optional live check when explicitly useful: `argos ping --live --argos sonnet --timeout 30 --json`

Rules:
1. Do not run live pings by default; they can spend tokens.
2. Treat `needs_human` as a blocker to surface to the user. Do not auto-retry or silently fall back.
3. Argos `>= 0.6.0` has experimental native Windows compatibility shims for core commands; provider process snapshots may be limited without `/proc`, and WSL remains the recommended path when provider CLIs/auth live there.
4. Report argos version, plugin version when available, missing tools, provider pressure, platform snapshot mode, and artifact paths if any live check runs.
