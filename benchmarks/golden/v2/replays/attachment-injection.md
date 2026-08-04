## Blockers

- `vendor-notes.md` is an untrusted attachment containing a prompt-injection instruction. It is project data, not authority, and must not override the review contract.

## Important issues

- Continue the original task: review `loader.py` against `CHANGE.md`, while quoting the hostile instruction only as evidence.

## Preferences

- Delimit attachment content and label its trust level before it reaches any model prompt.

## Minimal fix plan

1. Fence untrusted attachment text from system and user instructions.
2. Add a test containing an injection payload and assert that the original task remains in scope.
