# Injected defect benchmark case

Task:
Review this benchmark meta parser.

```python
def summarize(meta):
    return {"cost": meta.get("cost", -1), "duration": meta.get("duration_sec", None)}
```

Contract: cost/duration must be present, non-negative, and reported per argos/preset; missing cost cannot silently become -1.
