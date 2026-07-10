## Blockers
- The path traversal via `read_note` can escape `base_dir`.

## Important issues
- Fix this without new dependencies.
- Do not rewrite unrelated code.
- I reviewed the attached brief only.

## Preferences
- (none)

## Minimal fix plan
1. Sanitize `read_note` against `base_dir`.
2. Add a pytest regression test.
