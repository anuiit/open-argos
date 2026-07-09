---
name: adv-doctor
description: Check Adv-Tools/advisor readiness after install or when provider/session status is uncertain. Use `advisor doctor`, `advisor ping`, and `advisor providers`.
---

Run a non-destructive Adv-Tools readiness check.

Commands:
- Core readiness: `advisor doctor`
- Static model/tool check: `advisor ping --json`
- Provider slots/status: `advisor providers --json`
- Optional live check when explicitly useful: `advisor ping --live --advisor sonnet --timeout 30 --json`

Rules:
1. Do not run live pings by default; they can spend tokens.
2. Treat `needs_human` as a blocker to surface to the user. Do not auto-retry or silently fall back.
3. Advisor `>= 0.6.0` has experimental native Windows compatibility shims for core commands; provider process snapshots may be limited without `/proc`, and WSL remains the recommended path when provider CLIs/auth live there.
4. Report advisor version, plugin version when available, missing tools, provider pressure, platform snapshot mode, and artifact paths if any live check runs.
