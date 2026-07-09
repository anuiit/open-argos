# Injected defect benchmark case

Task:
Review lock handling in this runner.

```python
import fcntl, subprocess

def run_locked(lock_file, cmd):
    fd = open(lock_file, "w")
    fcntl.flock(fd, fcntl.LOCK_EX)
    subprocess.run(cmd, timeout=5)
    fcntl.flock(fd, fcntl.LOCK_UN)
```

Expected behavior: lock must always release on timeout or subprocess failure.
