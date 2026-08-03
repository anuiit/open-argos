from .cache import get_profile, invalidate_profile, put_profile


def load_profile(repository, tenant_id: str, user_id: str) -> dict:
    cached = get_profile(tenant_id, user_id)
    if cached is not None:
        return cached
    profile = repository.fetch_profile(tenant_id, user_id)
    put_profile(tenant_id, user_id, profile)
    return profile


def update_profile(repository, tenant_id: str, user_id: str, changes: dict) -> dict:
    profile = repository.update_profile(tenant_id, user_id, changes)
    invalidate_profile(tenant_id, user_id)
    return profile
