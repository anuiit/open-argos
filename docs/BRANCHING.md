# Branch and release workflow

## Branches

- `main` is protected and must remain releasable.
- Work happens on short-lived `feat/*`, `fix/*`, or `codex/*` branches.
- Pull requests require the CI test matrix and clean-package job.
- Use `release/<version>` only for a short stabilization window when several
  coordinated release fixes are necessary.

Do not introduce a permanent `dev` branch yet. It would duplicate integration
state and conflict with the current promotion scripts. Reconsider it only when
release trains or multiple supported versions create a concrete need.

## Promotion

1. Merge reviewed feature/fix branches into `main`.
2. Update the single product version source and `CHANGELOG.md`.
3. Verify Windows and Linux/WSL gates, package build, clean install, MCP
   preparation, and at least one bounded live provider smoke.
4. Create an annotated `v<product-version>` tag from `main`.
5. The release workflow re-runs the gate, verifies tag/version equality, builds
   wheel and source archive, writes checksums, and creates a GitHub pre-release
   when the tag contains `-`.

Open Argos is distributed under the MIT License. The release workflow
deliberately fails if `LICENSE` is missing. Registry publication is a separate
opt-in step and is not enabled for the first RC.

## Hotfixes

Branch from the released tag, add a regression test, merge the fix to `main`,
then issue the next patch or release candidate. Never patch a generated release
asset or installed plugin cache directly.
