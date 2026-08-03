from typing import Any

_profiles: dict[str, dict[str, Any]] = {}


def cache_key(tenant_id: str, user_id: str) -> str:
    return user_id


def get_profile(tenant_id: str, user_id: str) -> dict[str, Any] | None:
    return _profiles.get(cache_key(tenant_id, user_id))


def put_profile(tenant_id: str, user_id: str, profile: dict[str, Any]) -> None:
    _profiles[cache_key(tenant_id, user_id)] = dict(profile)


def invalidate_profile(tenant_id: str, user_id: str) -> None:
    _profiles.pop(f"{tenant_id}:{user_id}", None)
