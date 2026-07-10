---
name: mos-doctor
description: Check Mos-Tools/mosaic readiness after install or when provider/session status is uncertain. Use `mosaic doctor`, `mosaic ping`, and `mosaic providers`.
---

Run a non-destructive Mos-Tools readiness check.

Commands:
- Core readiness: `mosaic doctor`
- Static model/tool check: `mosaic ping --json`
- Provider slots/status: `mosaic providers --json`
- Optional live check when explicitly useful: `mosaic ping --live --mosaic sonnet --timeout 30 --json`

Rules:
1. Do not run live pings by default; they can spend tokens.
2. Treat `needs_human` as a blocker to surface to the user. Do not auto-retry or silently fall back.
3. Mosaic `>= 0.6.0` has experimental native Windows compatibility shims for core commands; provider process snapshots may be limited without `/proc`, and WSL remains the recommended path when provider CLIs/auth live there.
4. Report mosaic version, plugin version when available, missing tools, provider pressure, platform snapshot mode, and artifact paths if any live check runs.
