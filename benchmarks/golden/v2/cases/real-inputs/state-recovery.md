# State recovery case

The session left behind a stale active turn after a provider failure.

The response must cover:

- `active_turn`
- `outcome_unknown`
- audit event recording
- a safe repair path before any success claim

It should not pretend the turn completed cleanly.

