# Tenant profile cache

Profiles are scoped by both tenant and user. The same user identifier may
exist in many tenants. The change adds a short-lived process cache to reduce
database reads and an invalidation hook after profile updates.

Review all files as one change. Backward compatibility matters more than a
large cache redesign.
