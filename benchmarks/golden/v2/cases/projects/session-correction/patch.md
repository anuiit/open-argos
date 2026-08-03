# Proposed patch

The first review claimed that `load_profile()` leaks data because it did not
see the tenant-aware repository call. The attached correction shows the
repository call is scoped correctly; the actual remaining bug is that cache
invalidation uses a different key format from cache reads.
