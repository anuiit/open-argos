# Injected defect benchmark case

Task:
Critique this patch that runs a formatter selected by user input.

```python
import subprocess

def format_file(tool: str, filename: str) -> None:
    subprocess.run(f"{tool} {filename}", shell=True, check=True)
```

Constraints: stdlib only; keep formatter configurable.
