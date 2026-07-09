# Injected defect benchmark case

Task:
Review this provider error classifier for automation safety.

```python
def classify_provider_error(stderr: str) -> tuple[str, int]:
    if "auth" in stderr.lower() or "login" in stderr.lower():
        return ("error", 2)
    return ("error", 2)
```

Contract: auth/client eligibility failures must propagate as needs_human with exit code 3. No auto-retry/fallback.
