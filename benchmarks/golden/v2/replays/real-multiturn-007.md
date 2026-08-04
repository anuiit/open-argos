## Blockers
- The benchmark should preserve the correction loop instead of flattening both turns into a single one-shot response.

## Important issues
- The first answer should be allowed to be revised after the user correction.

## Preferences
- Add coverage in `tests/test_conversation_lifecycle.py` for the replayed turn sequence.

## Minimal fix plan
1. Preserve both turns in the benchmark report.
2. Record the revision explicitly in the artifact.
3. Add a regression test for the turn-state repair path.
