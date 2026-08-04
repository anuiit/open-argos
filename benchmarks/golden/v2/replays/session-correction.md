## Blockers

- I withdraw the earlier cross-tenant read claim: the correction shows the read key already includes the tenant. The remaining defect is narrower: invalidation omits the tenant key segment and fails to evict the populated entry.

## Important issues

- The corrected scope is cache invalidation only. Retaining the disproved read-isolation finding would overstate the evidence and ignore the second turn.

## Preferences

- Record the correction in the review artifact so the withdrawn claim cannot reappear in a later summary.

## Minimal fix plan

1. Reuse the tenant-aware key builder in invalidation.
2. Add a test that updates one tenant, evicts that tenant's entry, and leaves a same-id user in another tenant untouched.
