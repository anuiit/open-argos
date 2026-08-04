#!/usr/bin/env python3
"""Verify that release archives contain runtime files and no internal corpus."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


FORBIDDEN_PARTS = {
    ".argos",
    ".omc",
    ".omx",
    "argos-tools",
    "benchmarks",
    "tests",
}
FORBIDDEN_NAMES = {"BENCHLOG.md", "ETAT_DES_LIEUX-20260721.md", "uv.lock"}
REQUIRED_RUNTIME = {
    "argos/__init__.py",
    "argos/_version.py",
    "argos/argos.py",
    "argos/context_inputs.py",
    "argos/mcp_launcher.py",
    "argos/mcp_runtime.py",
    "argos/mcp_server.py",
}


def _relative_archive_paths(names: list[str], *, strip_root: bool) -> set[str]:
    normalized: set[str] = set()
    for raw in names:
        path = PurePosixPath(raw.replace("\\", "/"))
        parts = path.parts[1:] if strip_root and len(path.parts) > 1 else path.parts
        if parts:
            normalized.add(PurePosixPath(*parts).as_posix())
    return normalized


def _verify_members(paths: set[str], archive: Path) -> None:
    for raw in paths:
        path = PurePosixPath(raw)
        if FORBIDDEN_PARTS.intersection(path.parts) or path.name in FORBIDDEN_NAMES:
            raise SystemExit(f"forbidden release payload in {archive.name}: {raw}")


def _is_wheel_license(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return (
        len(parts) >= 3
        and parts[-2:] == ("licenses", "LICENSE")
        and parts[-3].endswith(".dist-info")
    )


def verify_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        members = _relative_archive_paths(archive.namelist(), strip_root=False)
    _verify_members(members, path)
    missing = REQUIRED_RUNTIME.difference(members)
    if missing:
        raise SystemExit(f"wheel is missing runtime files: {sorted(missing)}")
    license_members = {member for member in members if _is_wheel_license(member)}
    if len(license_members) != 1:
        raise SystemExit(f"wheel must contain one MIT LICENSE: {license_members}")


def verify_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        members = _relative_archive_paths(archive.getnames(), strip_root=True)
    _verify_members(members, path)
    missing = (REQUIRED_RUNTIME | {"LICENSE"}).difference(members)
    if missing:
        raise SystemExit(f"sdist is missing runtime files: {sorted(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", nargs="?", default="dist", type=Path)
    args = parser.parse_args()
    wheels = sorted(args.dist.glob("*.whl"))
    sdists = sorted(args.dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(
            f"expected exactly one wheel and one sdist in {args.dist}, "
            f"found {len(wheels)} and {len(sdists)}"
        )
    verify_wheel(wheels[0])
    verify_sdist(sdists[0])
    print(f"verified {wheels[0].name} and {sdists[0].name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
