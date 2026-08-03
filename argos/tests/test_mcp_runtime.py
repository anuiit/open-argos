from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "mcp_runtime.py"
SPEC = importlib.util.spec_from_file_location("mcp_runtime_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
mcp_runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mcp_runtime
SPEC.loader.exec_module(mcp_runtime)


class McpRuntimeTests(unittest.TestCase):
    def _workspace(self) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        workspace = Path(tempdir.name) / "workspace"
        (workspace / "argos").mkdir(parents=True)
        (workspace / "argos" / "mcp_server.py").write_text("# server\n", encoding="utf-8")
        return workspace

    def test_runtime_python_path_helper_handles_platform_layouts(self) -> None:
        self.assertEqual(
            mcp_runtime.runtime_python_path(Path("C:/runtime"), "nt"),
            Path("C:/runtime/Scripts/python.exe"),
        )
        self.assertEqual(
            mcp_runtime.runtime_python_path(Path("/runtime"), "posix"),
            Path("/runtime/bin/python"),
        )

    def test_default_runtime_root_is_versioned_user_cache(self) -> None:
        root = mcp_runtime.default_runtime_root(
            platform_name="nt",
            environment={"LOCALAPPDATA": r"C:\Users\test\AppData\Local"},
            home=Path(r"C:\Users\test"),
        )

        self.assertEqual(
            root,
            Path(r"C:\Users\test\AppData\Local")
            / "open-argos"
            / "runtimes"
            / (
                f"mcp-{mcp_runtime.MCP_VERSION}-"
                f"py{sys.version_info.major}{sys.version_info.minor}"
            ),
        )

    def test_default_runtime_root_uses_darwin_cache_when_requested(self) -> None:
        root = mcp_runtime.default_runtime_root(
            platform_name="darwin",
            environment={},
            home=Path("/Users/test"),
        )

        self.assertEqual(
            root,
            Path("/Users/test")
            / "Library"
            / "Caches"
            / "open-argos"
            / "runtimes"
            / (
                f"mcp-{mcp_runtime.MCP_VERSION}-"
                f"py{sys.version_info.major}{sys.version_info.minor}"
            ),
        )

    def test_default_runtime_root_detects_darwin_implicitly(self) -> None:
        with mock.patch.object(mcp_runtime.sys, "platform", "darwin"):
            root = mcp_runtime.default_runtime_root(
                environment={},
                home=Path("/Users/test"),
            )

        self.assertEqual(
            root,
            Path("/Users/test")
            / "Library"
            / "Caches"
            / "open-argos"
            / "runtimes"
            / (
                f"mcp-{mcp_runtime.MCP_VERSION}-"
                f"py{sys.version_info.major}{sys.version_info.minor}"
            ),
        )

    def test_bootstrap_reuses_healthy_runtime_without_installing(self) -> None:
        workspace = self._workspace()
        runtime_root = workspace / "runtime"
        runtime_python = mcp_runtime.runtime_python_path(runtime_root)
        completed = subprocess.CompletedProcess(args=["uv"], returncode=0, stdout="", stderr="")

        with (
            mock.patch.object(mcp_runtime, "_probe_runtime_version", return_value=mcp_runtime.MCP_VERSION),
            mock.patch.object(mcp_runtime, "_run_uv", return_value=completed) as run_uv,
        ):
            result = mcp_runtime.bootstrap_runtime(
                workspace,
                runtime_root=runtime_root,
            )

        self.assertTrue(result.ready)
        self.assertFalse(result.installed)
        self.assertEqual(result.installed_version, mcp_runtime.MCP_VERSION)
        self.assertEqual(result.runtime_python, runtime_python)
        self.assertEqual(run_uv.call_count, 0)
        marker = json.loads((runtime_root / mcp_runtime.MARKER_NAME).read_text(encoding="utf-8"))
        self.assertTrue(marker["ready"])
        self.assertEqual(marker["version"], mcp_runtime.MCP_VERSION)

    def test_bootstrap_installs_when_version_is_missing(self) -> None:
        workspace = self._workspace()
        runtime_root = workspace / "runtime"
        completed = subprocess.CompletedProcess(args=["uv"], returncode=0, stdout="", stderr="")

        with (
            mock.patch.object(
                mcp_runtime,
                "_probe_runtime_version",
                side_effect=[None, mcp_runtime.MCP_VERSION],
            ),
            mock.patch.object(mcp_runtime, "_run_uv", return_value=completed) as run_uv,
        ):
            result = mcp_runtime.bootstrap_runtime(
                workspace,
                runtime_root=runtime_root,
            )

        self.assertTrue(result.ready)
        self.assertTrue(result.installed)
        self.assertEqual(result.installed_version, mcp_runtime.MCP_VERSION)
        self.assertEqual(run_uv.call_count, 2)
        self.assertTrue((runtime_root / mcp_runtime.MARKER_NAME).exists())

    def test_bootstrap_failure_does_not_write_marker(self) -> None:
        workspace = self._workspace()
        runtime_root = workspace / "runtime"
        completed = subprocess.CompletedProcess(args=["uv"], returncode=0, stdout="", stderr="")

        with (
            mock.patch.object(
                mcp_runtime,
                "_probe_runtime_version",
                side_effect=[None, None],
            ),
            mock.patch.object(mcp_runtime, "_run_uv", return_value=completed),
        ):
            with self.assertRaises(mcp_runtime.BootstrapError):
                mcp_runtime.bootstrap_runtime(
                    workspace,
                    runtime_root=runtime_root,
                )

        self.assertFalse((runtime_root / mcp_runtime.MARKER_NAME).exists())

    def test_bootstrap_check_mode_skips_install_and_marker_write(self) -> None:
        workspace = self._workspace()
        runtime_root = workspace / "runtime"

        with (
            mock.patch.object(mcp_runtime, "_probe_runtime_version", return_value=None),
            mock.patch.object(mcp_runtime, "_run_uv") as run_uv,
        ):
            result = mcp_runtime.bootstrap_runtime(
                workspace,
                check_only=True,
                runtime_root=runtime_root,
            )

        self.assertFalse(result.ready)
        self.assertFalse(run_uv.called)
        self.assertFalse((runtime_root / mcp_runtime.MARKER_NAME).exists())

    def test_run_uv_uses_bounded_timeout_and_normalizes_expiry(self) -> None:
        with mock.patch.object(
            mcp_runtime.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["uv", "venv"],
                timeout=mcp_runtime.UV_COMMAND_TIMEOUT_SECONDS,
            ),
        ) as run:
            with self.assertRaisesRegex(
                mcp_runtime.BootstrapError,
                rf"uv timed out after {mcp_runtime.UV_COMMAND_TIMEOUT_SECONDS} seconds",
            ):
                mcp_runtime._run_uv(("venv",))

        self.assertEqual(
            run.call_args.kwargs["timeout"],
            mcp_runtime.UV_COMMAND_TIMEOUT_SECONDS,
        )

    def test_run_uv_uses_runtime_local_cache_without_overriding_caller(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["uv"], returncode=0, stdout="", stderr=""
        )
        cache_dir = Path("C:/writable/runtime-cache")
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                mcp_runtime.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            mcp_runtime._run_uv(("venv",), cache_dir=cache_dir)
        self.assertEqual(run.call_args.kwargs["env"]["UV_CACHE_DIR"], str(cache_dir))

        with (
            mock.patch.dict(
                os.environ,
                {"UV_CACHE_DIR": "C:/caller/cache"},
                clear=True,
            ),
            mock.patch.object(
                mcp_runtime.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            mcp_runtime._run_uv(("venv",), cache_dir=cache_dir)
        self.assertEqual(run.call_args.kwargs["env"]["UV_CACHE_DIR"], "C:/caller/cache")

    def test_workspace_symlink_or_reparse_is_rejected(self) -> None:
        workspace = self._workspace()

        with mock.patch.object(
            mcp_runtime,
            "_is_link_or_reparse",
            side_effect=lambda path: path == workspace,
        ):
            with self.assertRaises(mcp_runtime.BootstrapError):
                mcp_runtime.bootstrap_runtime(workspace)

    def test_runtime_path_component_symlink_or_reparse_is_rejected(self) -> None:
        workspace = self._workspace()
        runtime_component = workspace / "runtime"
        runtime_component.mkdir(parents=True, exist_ok=True)

        with mock.patch.object(
            mcp_runtime,
            "_is_link_or_reparse",
            side_effect=lambda path: path == runtime_component,
        ):
            with self.assertRaises(mcp_runtime.BootstrapError):
                mcp_runtime.bootstrap_runtime(
                    workspace,
                    runtime_root=runtime_component / "mcp",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
