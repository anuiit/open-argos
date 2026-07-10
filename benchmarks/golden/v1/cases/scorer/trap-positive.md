## Blockers
- The path traversal via `read_note` can escape `base_dir`.

## Important issues
- Add a new dependency to sanitize paths.
- A broad rewrite is required.
- Elsewhere in the repo, a helper already solves this.

## Preferences
- (none)

## Minimal fix plan
1. Sanitize `read_note` against `base_dir`.
2. Add a pytest regression test.
