from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by Python 3.10 CI
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def _load_core_module():
    path = ROOT / "argos" / "argos.py"
    spec = importlib.util.spec_from_file_location("argos_distribution_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_distribution_metadata_exposes_only_runtime_package() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["name"] == "open-argos"
    assert metadata["build-system"]["requires"] == ["setuptools>=77"]
    assert metadata["project"]["license"] == "MIT"
    assert metadata["project"]["license-files"] == ["LICENSE"]
    assert metadata["project"]["dynamic"] == ["version"]
    assert metadata["project"]["scripts"] == {
        "argos": "argos.argos:cli_main",
        "argos-mcp": "argos.mcp_launcher:main",
    }
    assert "dependencies" not in metadata["project"]
    assert metadata["tool"]["setuptools"]["packages"]["find"]["include"] == ["argos"]


def test_core_and_package_versions_share_one_source() -> None:
    from argos import VERSION, __version__

    core = _load_core_module()
    assert VERSION == "0.9.0-rc1"
    assert __version__ == "0.9.0rc1"
    assert core.VERSION == VERSION


def test_mit_license_uses_the_canonical_grant_and_disclaimer() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    normalized = " ".join(license_text.split())

    assert license_text.startswith(
        "MIT License\n\nCopyright (c) 2026 Open Argos contributors\n"
    )
    assert "Permission is hereby granted, free of charge" in normalized
    assert "included in all copies or substantial portions" in normalized
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in normalized


def test_release_workflow_cannot_publish_without_a_license() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "test -f LICENSE" in workflow
    assert "softprops/action-gh-release@v3" in workflow
    assert "generate_release_notes: true" in workflow
    assert "expected_version=" in workflow
    assert "bin/python -P -c" in workflow
    assert "GITHUB_REF_NAME" in workflow
    assert "does not match" in workflow

    test_index = workflow.index("python -m pytest -q")
    build_index = workflow.index("python -m build")
    verify_index = workflow.index("python scripts/verify_distribution.py dist")
    smoke_index = workflow.index("open-argos-release-smoke")
    publish_index = workflow.index("softprops/action-gh-release@v3")
    assert test_index < build_index < verify_index < smoke_index < publish_index


def test_ci_publishes_the_exact_candidate_distributions() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "actions/upload-artifact@v4" in workflow
    assert "name: open-argos-dist" in workflow
    assert "path: dist/*" in workflow
    assert "if-no-files-found: error" in workflow
    assert "--no-deps dist/*.whl" in workflow
    assert "expected_version=" in workflow
    assert "bin/python -P -c" in workflow

    assert workflow.count("timeout-minutes: 10") == 2

    verify_index = workflow.index("python scripts/verify_distribution.py dist")
    install_index = workflow.index("--no-deps dist/*.whl")
    upload_index = workflow.index("uses: actions/upload-artifact@v4")
    assert verify_index < install_index < upload_index


def test_ci_and_release_pin_the_validated_quality_toolchain() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "timeout-minutes: 15" in release

    for pin in (
        "pytest==9.1.1",
        "ruff==0.9.2",
        "build==1.2.2.post1",
        "uv==0.11.25",
        "tomli==2.4.1",
    ):
        assert pin in ci
        assert pin in release


def test_sdist_manifest_excludes_internal_quality_payloads() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    for directory in ("argos/tests", "argos-tools", "benchmarks", "scripts", "tests"):
        assert f"prune {directory}" in manifest
    assert "exclude BENCHLOG.md" in manifest
    assert "exclude uv.lock" in manifest
    assert "LICENSE" in manifest.splitlines()[0]

    assert "uv.lock" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_public_install_surfaces_do_not_embed_maintainer_paths() -> None:
    public_surfaces = (
        ROOT / "README.md",
        ROOT / "README.fr.md",
        ROOT / "argos" / "README.md",
        ROOT / "docs" / "MCP_INSTALL.md",
        ROOT / "argos-tools" / "README.md",
        ROOT / "argos-tools" / "ARCHITECTURE.md",
        ROOT / "argos-tools" / "claude-code" / "SKILL.md",
        ROOT / "argos-tools" / "references" / "mcp-bridge-plan.md",
        ROOT / "scripts" / "install-claude-code-windows.ps1",
    )

    forbidden = ("f:\\dev\\open-argos", "c:\\users\\anmou")
    for path in public_surfaces:
        content = path.read_text(encoding="utf-8").casefold()
        assert not any(value in content for value in forbidden), path
