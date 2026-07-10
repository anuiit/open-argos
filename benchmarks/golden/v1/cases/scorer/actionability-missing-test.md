## Blockers
- `classify_provider_error` hides auth failures instead of returning `needs_human` with exit code 3.

## Important issues
- (none)

## Preferences
- (none)

## Minimal fix plan
1. Return `needs_human` for auth/login failures.
2. Propagate exit code 3.
