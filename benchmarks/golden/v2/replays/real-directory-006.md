## Blockers
- `scripts/bench_argos_quality.py` should accept directory inputs deterministically.

## Important issues
- The benchmark should keep the per-file order visible in the artifact trail.

## Preferences
- Update `tests/test_bench_argos_quality.py` with a directory-input regression.

## Minimal fix plan
1. Extend `scripts/bench_argos_quality.py` to accept `--dir`.
2. Add a regression test for directory attachment.
3. Keep the change small and cross-platform.
