from pathlib import Path


def staging_path(data_root: Path, requested_name: str) -> Path:
    return data_root / "imports" / requested_name
