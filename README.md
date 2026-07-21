# open-argos

Benchmark-driven development working copy for the local `argos` CLI (core 0.7.0) and the `argos-tools` plugin facade.

- Dev CLI entrypoints: `./bin/argos-dev` (WSL/Linux) and `bin\argos-dev.cmd` / `bin\argos-dev.ps1` (Windows).
- Dev config: `.config/argos-dev/config.json`.
- Dev artifacts: `.argos/sessions/`.
- Dev locks: `.argos/locks/`.
- Internal quality suite: `argos-internal-quality` (`scripts/bench_argos_quality.py`, golden set under `benchmarks/golden/`).
- Native Windows mirror: `F:\dev\open-argos`. Feature parity with this working copy is mandatory; sync via `scripts/migrate-to-argos.sh`.
- Stable install: `/home/sina/.local/bin/argos -> /home/sina/.config/argos/argos.py` (promoted from this working copy at core 0.7.0, rebaseline v1.1.0 score 93.73/100; see `scripts/finalize-rename.sh`).

Unchanged rule: do not promote changes to the stable CLI/plugin without explicit human validation.
