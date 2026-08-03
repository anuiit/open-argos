## Blockers
- Update `openai_client.py` so request validation happens before the network call.
- Fix `vision_context.py` so stale context is not reused across benchmark turns.

## Important issues
- Add a regression test in `tests/test_m2_2d_policy.py` for the new behavior.

## Preferences
- Keep the patch narrow; do not rewrite unrelated modules.

## Minimal fix plan
1. Patch `openai_client.py`.
2. Patch `vision_context.py`.
3. Add the targeted pytest regression.
