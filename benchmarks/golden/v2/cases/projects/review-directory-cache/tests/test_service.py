def test_second_read_uses_cache(repository, profile_service) -> None:
    repository.fetch_profile.return_value = {"display_name": "Ada"}

    first = profile_service.load_profile(repository, "tenant-a", "user-7")
    second = profile_service.load_profile(repository, "tenant-a", "user-7")

    assert first == second
    repository.fetch_profile.assert_called_once()
