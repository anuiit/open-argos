from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ARGOS_DIR = Path(__file__).resolve().parents[1]
if str(ARGOS_DIR) not in sys.path:
    sys.path.insert(0, str(ARGOS_DIR))

try:
    from mcp import Client
except ModuleNotFoundError as exc:  # Optional transport dependency.
    raise unittest.SkipTest(
        "mcp==2.0.0 is required for MCP SDK tests"
    ) from exc

import mcp_adapter  # noqa: E402
import mcp_server  # noqa: E402


def sample_config() -> dict:
    return {
        "models": {
            "fable": [
                {
                    "kind": "claude",
                    "model": "test-model",
                    "provider": "claude",
                }
            ]
        },
        "modes": {"review": ["fable"], "council": ["fable"]},
        "synthesis": {"default_model": "fable"},
        "sota": {
            "synthesizers": ["fable"],
            "reviewer": "fable",
            "high_reviewer": "fable",
        },
    }


class McpServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name).resolve()
        self.adapter = mcp_adapter.ArgosMCPAdapter(self.workspace)
        self.config_patch = patch.object(
            self.adapter,
            "_load_config",
            return_value=sample_config(),
        )
        self.config_patch.start()
        self.server = mcp_server.create_mcp_server(self.adapter)

    def tearDown(self) -> None:
        self.config_patch.stop()
        self.temp.cleanup()

    async def test_initialize_tools_and_annotations(self) -> None:
        async with Client(self.server, raise_exceptions=True) as client:
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            annotations = {
                tool.name: tool.annotations for tool in listed.tools
            }
            schemas = {
                tool.name: tool.input_schema for tool in listed.tools
            }

        self.assertEqual(
            names,
            {
                "argos_health",
                "argos_session_list",
                "argos_session_show",
                "argos_council_show",
                "argos_run",
                "argos_start",
                "argos_ask",
                "argos_council_publish",
                "argos_research",
            },
        )
        self.assertTrue(annotations["argos_health"].read_only_hint)
        self.assertFalse(annotations["argos_run"].read_only_hint)
        self.assertTrue(annotations["argos_run"].idempotent_hint)
        self.assertFalse(annotations["argos_run"].open_world_hint)
        self.assertTrue(annotations["argos_research"].open_world_hint)
        for tool_name in (
            "argos_run",
            "argos_start",
            "argos_ask",
            "argos_council_publish",
            "argos_research",
        ):
            self.assertIn(
                "artifact_write",
                schemas[tool_name].get("required", []),
                tool_name,
            )

    async def test_health_and_denied_write_are_structured_and_side_effect_free(
        self,
    ) -> None:
        async with Client(self.server, raise_exceptions=True) as client:
            health = await client.call_tool("argos_health", {})
            denied = await client.call_tool(
                "argos_run",
                {
                    "request_id": "mcp-denied",
                    "prompt": "Review this",
                    "mode": "review",
                    "artifact_write": False,
                    "model_egress": False,
                },
            )

        self.assertFalse(health.is_error)
        self.assertTrue(health.structured_content["result"]["ready"])
        self.assertFalse(denied.is_error)
        self.assertEqual(
            denied.structured_content["error"]["class"],
            "approval_required",
        )
        self.assertFalse((self.workspace / ".argos").exists())

    async def test_resource_templates_and_sanitized_resource_read(self) -> None:
        session_id = "adv_20260731T120000_1234abcd"
        session_dir = self.adapter.sessions_root / session_id
        turn_dir = session_dir / "turns" / "001"
        turn_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text(
            json.dumps(
                {
                    "id": session_id,
                    "mode": "review",
                    "status": "active",
                    "turn": 1,
                    "last_good_turn": 1,
                    "last_turn_status": "ok",
                    "updated_at": "2026-07-31T12:00:00+00:00",
                    "argoses_requested": ["fable"],
                    "argoses": {
                        "fable": {
                            "status": "alive",
                            "provider_session_id": "must-not-leak",
                        }
                    },
                    "config_snapshot": sample_config(),
                }
            ),
            encoding="utf-8",
        )
        (turn_dir / "meta.json").write_text(
            json.dumps(
                {
                    "turn": 1,
                    "status": "ok",
                    "results": [{"argos": "fable", "status": "ok"}],
                }
            ),
            encoding="utf-8",
        )
        (turn_dir / "final.md").write_text("safe output", encoding="utf-8")

        async with Client(self.server, raise_exceptions=True) as client:
            templates = await client.list_resource_templates()
            resource = await client.read_resource(
                f"argos://sessions/{session_id}/summary"
            )

        uris = {
            str(item.uri_template)
            for item in templates.resource_templates
        }
        self.assertIn("argos://sessions/{session_id}/summary", uris)
        text = resource.contents[0].text
        self.assertIn(session_id, text)
        self.assertNotIn("must-not-leak", text)
        self.assertNotIn(str(self.workspace), text)


if __name__ == "__main__":
    unittest.main()
