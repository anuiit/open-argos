from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from mcp import Client, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ModuleNotFoundError as exc:  # Optional transport dependency.
    raise unittest.SkipTest(
        "mcp==2.0.0 is required for MCP stdio tests"
    ) from exc


SERVER_PATH = Path(__file__).resolve().parents[1] / "mcp_server.py"
RUNTIME_PYTHON_ENV = "ARGOS_MCP_RUNTIME_PYTHON"


def _stdio_parameters(workspace: Path) -> StdioServerParameters:
    runtime_python = os.environ.get(RUNTIME_PYTHON_ENV)
    if runtime_python:
        command = str(Path(runtime_python).expanduser().resolve())
        args = [str(SERVER_PATH)]
    else:
        command = "uv"
        args = ["run", "--script", str(SERVER_PATH)]
    return StdioServerParameters(
        command=command,
        args=args,
        env={"ARGOS_WORKSPACE": str(workspace)},
        cwd=str(workspace),
    )


class McpStdioSmokeTests(unittest.IsolatedAsyncioTestCase):
    def test_stdio_parameters_use_bootstrapped_runtime_when_configured(
        self,
    ) -> None:
        workspace = Path.cwd().resolve()
        runtime_python = str(Path(sys.executable).resolve())
        with mock.patch.dict(
            os.environ,
            {RUNTIME_PYTHON_ENV: runtime_python},
        ):
            parameters = _stdio_parameters(workspace)

        self.assertEqual(parameters.command, runtime_python)
        self.assertEqual(parameters.args, [str(SERVER_PATH)])

    def test_stdio_parameters_keep_pep723_fallback(self) -> None:
        workspace = Path.cwd().resolve()
        with mock.patch.dict(os.environ, {}, clear=True):
            parameters = _stdio_parameters(workspace)

        self.assertEqual(parameters.command, "uv")
        self.assertEqual(
            parameters.args,
            ["run", "--script", str(SERVER_PATH)],
        )

    async def test_real_stdio_process_initializes_and_handles_denied_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_workspace:
            workspace = Path(raw_workspace).resolve()
            parameters = _stdio_parameters(workspace)

            async with Client(
                stdio_client(parameters),
                raise_exceptions=True,
                read_timeout_seconds=60,
            ) as client:
                listed = await client.list_tools()
                health = await client.call_tool("argos_health", {})
                denied = await client.call_tool(
                    "argos_run",
                    {
                        "request_id": "stdio-denied",
                        "prompt": "Review this",
                        "mode": "review",
                        "artifact_write": False,
                        "model_egress": False,
                    },
                )

            self.assertEqual(len(listed.tools), 9)
            self.assertTrue(health.structured_content["result"]["ready"])
            self.assertEqual(
                denied.structured_content["error"]["class"],
                "approval_required",
            )
            self.assertFalse((workspace / ".argos").exists())

    @unittest.skipUnless(
        os.environ.get("ARGOS_MCP_LIVE_PROVIDER"),
        "set ARGOS_MCP_LIVE_PROVIDER for the opt-in provider smoke",
    )
    async def test_opt_in_live_provider_through_real_stdio(self) -> None:
        provider = os.environ["ARGOS_MCP_LIVE_PROVIDER"]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw_workspace:
            workspace = Path(raw_workspace).resolve()
            parameters = _stdio_parameters(workspace)

            async with Client(
                stdio_client(parameters),
                raise_exceptions=True,
                read_timeout_seconds=180,
            ) as client:
                response = await client.call_tool(
                    "argos_run",
                    {
                        "request_id": "stdio-live-provider",
                        "prompt": (
                            "Reply with exactly ARGOS_MCP_LIVE_OK and nothing else."
                        ),
                        "mode": "review",
                        "providers": [provider],
                        "artifact_write": True,
                        "model_egress": True,
                    },
                )

            payload = response.structured_content
            self.assertFalse(response.is_error)
            self.assertIn(payload["status"], {"completed", "partial"})
            self.assertIn("ARGOS_MCP_LIVE_OK", payload["result"]["final_text"])
            self.assertFalse(Path(payload["artifact_dir"]).is_absolute())
            self.assertTrue((workspace / ".argos" / "mcp").exists())
            provider_cwds = list(workspace.rglob("provider_cwd"))
            self.assertTrue(provider_cwds)
            for provider_cwd in provider_cwds:
                release_probe = provider_cwd.with_name(
                    "provider_cwd-release-probe"
                )
                for _ in range(40):
                    try:
                        provider_cwd.rename(release_probe)
                        release_probe.rename(provider_cwd)
                        break
                    except PermissionError:
                        await asyncio.sleep(0.25)
                else:
                    self.fail(
                        f"{provider} retained its provider cwd after completion"
                    )


if __name__ == "__main__":
    unittest.main()
