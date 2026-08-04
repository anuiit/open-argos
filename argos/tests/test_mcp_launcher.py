from __future__ import annotations

import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ARGOS_DIR = Path(__file__).resolve().parents[1]
if str(ARGOS_DIR) not in sys.path:
    sys.path.insert(0, str(ARGOS_DIR))

import mcp_launcher  # noqa: E402

BootstrapError = mcp_launcher.BootstrapError
RuntimeBootstrapResult = mcp_launcher.RuntimeBootstrapResult


def ready_result() -> RuntimeBootstrapResult:
    root = Path("C:/runtime")
    return RuntimeBootstrapResult(
        workspace=Path("C:/package"),
        runtime_root=root,
        runtime_python=root / "Scripts" / "python.exe",
        server_path=Path("C:/package/argos/mcp_server.py"),
        marker_path=root / "runtime.json",
        ready=True,
        installed_version="2.0.0",
        check_only=False,
        installed=False,
    )


class McpLauncherTests(unittest.TestCase):
    @mock.patch.object(mcp_launcher, "bootstrap_runtime", return_value=ready_result())
    @mock.patch.object(
        mcp_launcher.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0),
    )
    def test_default_bootstraps_then_runs_server_without_capturing_stdio(
        self,
        run: mock.Mock,
        bootstrap: mock.Mock,
    ) -> None:
        self.assertEqual(mcp_launcher.main([]), 0)

        bootstrap.assert_called_once_with(
            mcp_launcher.package_workspace(),
            check_only=False,
            runtime_root=None,
        )
        run.assert_called_once_with(
            [
                str(ready_result().runtime_python),
                str(ready_result().server_path),
            ],
            check=False,
        )

    @mock.patch.object(mcp_launcher, "bootstrap_runtime", return_value=ready_result())
    @mock.patch.object(mcp_launcher.subprocess, "run")
    def test_prepare_reports_runtime_without_starting_server(
        self,
        run: mock.Mock,
        bootstrap: mock.Mock,
    ) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            self.assertEqual(mcp_launcher.main(["--prepare", "--json"]), 0)

        run.assert_not_called()
        bootstrap.assert_called_once()
        self.assertIn('"ready": true', stdout.getvalue())

    @mock.patch.object(
        mcp_launcher,
        "bootstrap_runtime",
        side_effect=BootstrapError("runtime unavailable"),
    )
    def test_bootstrap_error_is_a_clean_cli_failure(self, bootstrap: mock.Mock) -> None:
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            self.assertEqual(mcp_launcher.main([]), 1)

        self.assertEqual(stderr.getvalue().strip(), "runtime unavailable")
