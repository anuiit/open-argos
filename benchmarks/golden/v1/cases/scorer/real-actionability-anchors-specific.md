## Blockers
- (none)
## Important issues
- (none)
## Preferences
- (none)
## Minimal fix plan
1. Update `alita/policy/openai_client.py` to sanitize timeout and secret-error paths.
2. Update `alita/policy/vision_context.py` to enforce safe image path guards.
3. Add `tests/test_m2_2d_policy.py::test_openai_error_sanitized` and run pytest.
