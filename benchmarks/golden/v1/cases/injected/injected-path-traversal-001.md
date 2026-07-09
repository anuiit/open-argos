# Injected defect benchmark case

Task:
Review this Python helper for security and testability.

```python
from pathlib import Path

def read_note(base_dir: str, user_name: str) -> str:
    path = Path(base_dir) / user_name
    return path.read_text()
```

Constraints: no new dependencies; preserve ability to read files below base_dir only.
