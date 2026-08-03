from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path


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
    assert metadata["project"]["dynamic"] == ["version"]
    assert metadata["project"]["scripts"] == {
        "argos": "argos.argos:cli_main",
        "argos-mcp": "argos.mcp_launcher:main",
    }
    assert "dependencies" not in metadata["project"]
    assert metadata["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "argos"
    ]


def test_core_and_package_versions_share_one_source() -> None:
    from argos import VERSION, __version__

    core = _load_core_module()
    assert VERSION == "0.9.0-rc1"
    assert __version__ == "0.9.0rc1"
    assert core.VERSION == VERSION


def test_release_workflow_cannot_publish_without_a_license() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "test -f LICENSE" in workflow
    assert "softprops/action-gh-release@v3" in workflow


def test_sdist_manifest_excludes_internal_quality_payloads() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    for directory in ("argos/tests", "argos-tools", "benchmarks", "scripts", "tests"):
        assert f"prune {directory}" in manifest
    assert "exclude BENCHLOG.md" in manifest


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
