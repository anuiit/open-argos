from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ARGOS_PATH = Path(__file__).resolve().parents[1] / "argos.py"
SPEC = importlib.util.spec_from_file_location("argos_kimi_under_test", ARGOS_PATH)
assert SPEC and SPEC.loader
argos = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = argos
SPEC.loader.exec_module(argos)


KIMI_CANDIDATE = {
    "kind": "kimi",
    "model": "kimi-code/k3",
    "provider": "kimi",
    "command": "kimi",
}


def acp_jsonl(*, session_id: str = "session-k3", text: str = "answer") -> str:
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": 1,
                "agentInfo": {"name": "Kimi Code CLI", "version": "0.29.2"},
                "agentCapabilities": {"loadSession": True},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": session_id}},
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                },
            },
        },
        {"jsonrpc": "2.0", "id": 3, "result": {"stopReason": "end_turn"}},
    ]
    return "\n".join(json.dumps(message) for message in messages) + "\n"


class IsolatedRuntimeRootsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        runtime_root = tempfile.TemporaryDirectory()
        self.addCleanup(runtime_root.cleanup)
        lock_root_patch = mock.patch.object(
            argos,
            "DEFAULT_LOCK_ROOT",
            Path(runtime_root.name) / "locks",
        )
        lock_root_patch.start()
        self.addCleanup(lock_root_patch.stop)


class KimiConfigTests(IsolatedRuntimeRootsTestCase):
    def test_defaults_route_both_kimi_names_directly_to_kimi_k3(self) -> None:
        self.assertEqual(argos.DEFAULT_CONFIG["models"]["kimi"], [KIMI_CANDIDATE])
        self.assertEqual(argos.DEFAULT_CONFIG["models"]["kimi3"], [KIMI_CANDIDATE])
        self.assertEqual(argos.DEFAULT_CONFIG["concurrency"]["kimi"], 1)
        self.assertGreaterEqual(argos.DEFAULT_CONFIG["timeouts"]["kimi"], 120)

    def test_kimi_candidate_rejects_provider_model_or_command_override(self) -> None:
        invalid_candidates = [
            {**KIMI_CANDIDATE, "provider": "opencode_go"},
            {**KIMI_CANDIDATE, "model": "kimi-code/k2.7"},
            {**KIMI_CANDIDATE, "command": "opencode"},
        ]
        for candidate in invalid_candidates:
            with self.subTest(candidate=candidate):
                cfg = argos.deep_merge(
                    argos.DEFAULT_CONFIG,
                    {"models": {"bad": [candidate]}, "modes": {}, "presets": {}},
                )
                with self.assertRaises(SystemExit):
                    argos.validate_config(cfg)

    def test_reserved_kimi_aliases_reject_redirects_and_fallback_chains(self) -> None:
        opencode_candidate = {
            "kind": "opencode",
            "model": "opencode-go/glm-5.2",
            "provider": "opencode_go",
        }
        invalid_chains = [
            [opencode_candidate],
            [KIMI_CANDIDATE, opencode_candidate],
        ]
        for logical in ("kimi", "kimi3"):
            for chain in invalid_chains:
                with self.subTest(logical=logical, chain=chain):
                    cfg = argos.deep_merge(
                        argos.DEFAULT_CONFIG,
                        {"models": {logical: chain}},
                    )
                    with self.assertRaises(SystemExit):
                        argos.validate_config(cfg)

    def test_any_kimi_route_rejects_a_fallback_candidate(self) -> None:
        cfg = argos.deep_merge(
            argos.DEFAULT_CONFIG,
            {
                "models": {
                    "custom_kimi": [
                        KIMI_CANDIDATE,
                        {
                            "kind": "opencode",
                            "model": "opencode-go/glm-5.2",
                            "provider": "opencode_go",
                        },
                    ]
                }
            },
        )
        with self.assertRaises(SystemExit):
            argos.validate_config(cfg)

    def test_kimi_is_allowlisted_but_unrelated_binaries_are_not(self) -> None:
        argos.assert_allowed_subprocess(["kimi", "acp"])
        argos.assert_allowed_subprocess([r"C:\Tools\kimi.exe", "acp"])
        with self.assertRaises(RuntimeError):
            argos.assert_allowed_subprocess(["opencode-kimi", "run"])

    def test_kimi_tool_is_reported_by_ping(self) -> None:
        self.assertEqual(argos.tool_for_candidate(KIMI_CANDIDATE), "kimi")


class KimiTransportTests(IsolatedRuntimeRootsTestCase):
    def test_private_agent_disables_tools_and_command_never_contains_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            agent_file = argos.stage_kimi_agent(Path(td))
            body = agent_file.read_text(encoding="utf-8")
            command, shape = argos.build_kimi_command(KIMI_CANDIDATE, agent_file)

        self.assertIn("tools: []", body)
        self.assertIn("subagents: []", body)
        self.assertEqual(
            command,
            [
                "kimi",
                "-m",
                "kimi-code/k3",
                "--agent-file",
                str(agent_file),
                "acp",
            ],
        )
        self.assertEqual(
            shape,
            "kimi -m kimi-code/k3 --agent-file <private-no-tools-agent> acp",
        )
        self.assertNotIn("prompt", " ".join(command).lower())

    def test_large_prompt_is_only_present_in_acp_prompt_request(self) -> None:
        prompt = "x" * 43000
        requests = argos.kimi_acp_requests(prompt, Path("C:/workspace"))
        serialized = [json.dumps(request) for request in requests]

        self.assertNotIn(prompt, serialized[0])
        self.assertNotIn(prompt, serialized[1])
        self.assertIn(prompt, serialized[2])
        self.assertEqual(requests[1]["method"], "session/new")
        self.assertEqual(requests[2]["method"], "session/prompt")

    def test_resume_uses_structured_session_id(self) -> None:
        requests = argos.kimi_acp_requests(
            "next turn", Path("C:/workspace"), provider_session_id="session-k3"
        )
        self.assertEqual(requests[1]["method"], "session/resume")
        self.assertEqual(requests[1]["params"]["sessionId"], "session-k3")
        self.assertEqual(requests[2]["params"]["sessionId"], "session-k3")

    def test_kimi_environment_enables_agent_file_and_disables_telemetry(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            env = argos._subprocess_env(["kimi", "acp"], Path.cwd())
        self.assertEqual(env["KIMI_CODE_EXPERIMENTAL_FLAG"], "1")
        self.assertEqual(env["KIMI_DISABLE_TELEMETRY"], "1")

    def test_workspace_shadowed_kimi_binary_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            shadow = cwd / "kimi.exe"
            shadow.touch()
            with mock.patch.object(argos.shutil, "which", return_value=str(shadow)):
                with self.assertRaises(RuntimeError):
                    argos.resolve_kimi_executable(["kimi", "acp"], cwd)


class KimiParserTests(IsolatedRuntimeRootsTestCase):
    def test_parser_collects_text_session_and_unknown_cost(self) -> None:
        content, meta = argos.parse_kimi_acp(acp_jsonl(text="hello world"))
        self.assertEqual(content, "hello world")
        self.assertEqual(meta["session_id"], "session-k3")
        self.assertIsNone(meta["cost"])
        self.assertIsNone(meta["tokens"])

    def test_parser_rejects_tool_updates(self) -> None:
        tool_message = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "danger",
                    "title": "shell",
                }
            },
        }
        with self.assertRaises(argos.KimiToolUseError):
            argos.parse_kimi_acp(json.dumps(tool_message) + "\n")

    def test_parser_rejects_reverse_rpc(self) -> None:
        permission = {
            "jsonrpc": "2.0",
            "id": 77,
            "method": "session/request_permission",
            "params": {"sessionId": "session-k3"},
        }
        with self.assertRaises(argos.KimiToolUseError):
            argos.parse_kimi_acp(json.dumps(permission) + "\n")

    def test_parser_marks_truncated_jsonl_as_unknown(self) -> None:
        with self.assertRaises(argos.KimiAcpParseError):
            argos.parse_kimi_acp('{"jsonrpc":"2.0","method":"session/update"')

    def test_parser_rejects_non_jsonrpc_and_duplicate_responses(self) -> None:
        missing_version = acp_jsonl().replace('{"jsonrpc": "2.0", ', "{", 1)
        duplicate = acp_jsonl() + json.dumps(
            {"jsonrpc": "2.0", "id": 3, "result": {"stopReason": "end_turn"}}
        )
        for stream in (missing_version, duplicate):
            with self.subTest(stream=stream):
                with self.assertRaises(argos.KimiAcpParseError):
                    argos.parse_kimi_acp(stream)

    def test_parser_rejects_non_success_terminal_reason(self) -> None:
        stream = acp_jsonl().replace('"stopReason": "end_turn"', '"stopReason": "cancelled"')
        with self.assertRaises(argos.KimiAcpParseError):
            argos.parse_kimi_acp(stream)

    def test_parser_rejects_unknown_reverse_notification(self) -> None:
        stream = acp_jsonl().replace(
            '{"jsonrpc": "2.0", "id": 3, "result": {"stopReason": "end_turn"}}',
            '\n'.join(
                [
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "method": "session/request_permission",
                            "params": {"sessionId": "session-k3"},
                        }
                    ),
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 3,
                            "result": {"stopReason": "end_turn"},
                        }
                    ),
                ]
            ),
        )
        with self.assertRaises(argos.KimiToolUseError):
            argos.parse_kimi_acp(stream)

    def test_parser_rejects_resume_session_mismatch(self) -> None:
        with self.assertRaises(argos.KimiAcpParseError):
            argos.parse_kimi_acp(
                acp_jsonl(session_id="session-B"),
                expected_session_id="session-A",
            )


class KimiRunnerTests(IsolatedRuntimeRootsTestCase):
    def test_runner_uses_acp_and_preserves_session_id(self) -> None:
        async def fake_run(*args: object, **kwargs: object) -> tuple[int, str, str, float]:
            self.assertEqual(kwargs["provider_session_id"], "session-k3")
            self.assertEqual(kwargs["prompt"], "next")
            return 0, acp_jsonl(session_id="session-k3", text="done"), "", 0.1

        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            argos, "run_kimi_acp", side_effect=fake_run
        ):
            runner = argos.Runner(argos.DEFAULT_CONFIG, Path(td))
            result = asyncio.run(
                runner.run_candidate(
                    "kimi",
                    KIMI_CANDIDATE,
                    "next",
                    [],
                    fallback_from=None,
                    provider_session_id="session-k3",
                )
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.content, "done")
        self.assertEqual(result.session_id, "session-k3")
        self.assertEqual(result.command_shape, "kimi -m kimi-code/k3 --agent-file <private-no-tools-agent> acp")

    def test_auth_error_needs_human_without_fallback(self) -> None:
        async def fake_run(*args: object, **kwargs: object) -> tuple[int, str, str, float]:
            return 1, "", "Authentication required. Please login.", 0.1

        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            argos, "run_kimi_acp", side_effect=fake_run
        ):
            runner = argos.Runner(argos.DEFAULT_CONFIG, Path(td))
            result = asyncio.run(
                runner.run_candidate(
                    "kimi", KIMI_CANDIDATE, "prompt", [], fallback_from=None
                )
            )

        self.assertEqual(result.status, "needs_human")
        self.assertIsNone(result.fallback_from)

    def test_truncated_acp_output_becomes_outcome_unknown(self) -> None:
        async def fake_run(*args: object, **kwargs: object) -> tuple[int, str, str, float]:
            return 1, '{"jsonrpc":"2.0"', "ACP stream ended unexpectedly", 0.1

        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            argos, "run_kimi_acp", side_effect=fake_run
        ):
            runner = argos.Runner(argos.DEFAULT_CONFIG, Path(td))
            result = asyncio.run(
                runner.run_candidate(
                    "kimi", KIMI_CANDIDATE, "prompt", [], fallback_from=None
                )
            )

        self.assertEqual(result.status, "outcome_unknown")

    def test_reserved_alias_rejects_a_persisted_non_kimi_candidate(self) -> None:
        legacy_candidate = {
            "kind": "opencode",
            "model": "opencode-go/kimi-k3",
            "provider": "opencode_go",
        }
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            argos, "run_subprocess"
        ) as run_subprocess:
            runner = argos.Runner(argos.DEFAULT_CONFIG, Path(td))
            result = asyncio.run(
                runner.run_candidate(
                    "kimi3", legacy_candidate, "prompt", [], fallback_from=None
                )
            )
        self.assertEqual(result.status, "error")
        self.assertIn("reserved Kimi", result.error or "")
        run_subprocess.assert_not_called()

    def test_unknown_kimi_outcome_is_not_retried(self) -> None:
        outcome = argos.ArgosResult(
            argos="kimi",
            status="outcome_unknown",
            provider="kimi",
            model="kimi-code/k3",
            kind="kimi",
            error="Kimi ACP timed out",
        )
        state = {
            "candidate": KIMI_CANDIDATE,
            "locked_provider": "kimi",
            "locked_model": "kimi-code/k3",
            "locked_kind": "kimi",
            "provider_session_id": "session-k3",
        }
        with tempfile.TemporaryDirectory() as td:
            runner = argos.Runner(argos.DEFAULT_CONFIG, Path(td), mode="review")
            with mock.patch.object(
                runner, "run_candidate", mock.AsyncMock(return_value=outcome)
            ) as run_candidate:
                result = asyncio.run(runner.run_locked("kimi", state, "next", []))
        self.assertIs(result, outcome)
        run_candidate.assert_awaited_once()

    def test_config_cli_accepts_only_the_exact_kimi_route(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            config_path = Path(td) / "config.json"
            rc = argos.main(
                [
                    "--config",
                    str(config_path),
                    "config",
                    "set-model",
                    "kimi",
                    "--kind",
                    "kimi",
                    "--model",
                    "kimi-code/k3",
                    "--provider",
                    "kimi",
                    "--command",
                    "kimi",
                ]
            )
            self.assertEqual(rc, 0)
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["models"]["kimi"], [KIMI_CANDIDATE])


if __name__ == "__main__":
    unittest.main()
