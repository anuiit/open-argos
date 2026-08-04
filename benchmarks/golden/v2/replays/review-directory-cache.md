## Blockers

- `service.py:get_profile()` reads the cache with `user_id` alone. Two tenants can share that value, so tenant B can receive tenant A's cached profile: this is a cross-tenant cache isolation failure.

## Important issues

- `invalidate_profile()` builds `tenant_id:user_id`, but reads and writes use only `user_id`. The invalidation key therefore never evicts the populated entry and stale data survives updates.

## Preferences

- Keep key construction in one helper so reads, writes, and invalidation cannot drift again.

## Minimal fix plan

1. Introduce a composite tenant and user cache key and use it in all three operations.
2. Add a test where two tenants reuse one user id and never observe each other's cached value.
3. Add an invalidation regression test proving an update evicts the tenant-scoped entry.
