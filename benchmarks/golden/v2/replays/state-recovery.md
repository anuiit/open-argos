## Blockers

- The stale `active_turn` cannot be marked successful or failed because the provider may have completed after the client disconnected. Transition it to `outcome_unknown`; do not relaunch automatically.

## Important issues

- Append an audit event with the stale pid, timestamps, provider and repair reason.
- Preserve the original log and turn evidence in history so an operator can reconcile a late provider artifact.

## Preferences

- Prefer an explicit recoverable state over silently overwriting the active turn.

## Minimal fix plan

1. Mark the stale turn `outcome_unknown` and clear only the active lock.
2. Record the repair audit event without mutating the original evidence.
3. Resume with a new turn only after the operator chooses whether another attempt is safe.
