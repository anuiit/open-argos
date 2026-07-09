# Injected defect benchmark case

Task:
Review this SOTA summary quality classification.

```json
{"source_quality_counts":{"strong":3,"weak":0,"off_topic":0},"evidence":[{"id":"E1","source":"vendor_blog","quality":"strong","title":"Buy our product"},{"id":"E2","source":"unknown","quality":"strong","title":"Unrelated recipe"}]}
```

Contract: vendor and off-topic sources must not inflate strong evidence counts.
