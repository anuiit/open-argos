from __future__ import annotations

import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys


ARGOS_DIR = Path(__file__).resolve().parents[1]
if str(ARGOS_DIR) not in sys.path:
    sys.path.insert(0, str(ARGOS_DIR))

import argos as core  # noqa: E402
import mcp_adapter  # noqa: E402
import mcp_contract  # noqa: E402


def sample_config() -> dict:
    return {
        "models": {
            "fable": [
                {
                    "kind": "claude",
                    "model": "test-model",
                    "provider": "claude",
                }
            ],
            "critic": [
                {
                    "kind": "opencode",
                    "model": "test-critic",
                    "provider": "test",
                }
            ],
        },
        "modes": {
            "review": ["fable"],
            "plan": ["fable"],
            "council": ["fable"],
        },
        "synthesis": {"default_model": "fable"},
        "sota": {
            "synthesizers": ["fable"],
            "reviewer": "fable",
            "high_reviewer": "fable",
        },
    }


class AdapterTestCase(unittest.IsolatedAsyncioTestCase):
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

    def tearDown(self) -> None:
        self.config_patch.stop()
        self.temp.cleanup()

    def run_request(
        self,
        request_id: str = "req-run",
        *,
        prompt: str = "Review this",
        artifact_write: bool = True,
        model_egress: bool = True,
        **kwargs,
    ) -> mcp_contract.RunRequest:
        return mcp_contract.RunRequest(
            request_id=request_id,
            prompt=prompt,
            mode="review",
            providers=["fable"],
            artifact_write=artifact_write,
            model_egress=model_egress,
            **kwargs,
        )

    async def fake_run(self, namespace, *, return_payload=False):
        artifact = Path(namespace.artifact_root) / "review-test"
        artifact.mkdir(parents=True, exist_ok=True)
        (artifact / "final.md").write_text("safe answer", encoding="utf-8")
        payload = {
            "mode": "review",
            "artifact_dir": str(artifact),
            "inputs_report": {
                "included": [],
                "skipped": [],
                "total_chars": 0,
                "limits": {
                    "max_files": 100,
                    "max_file_chars": 60_000,
                    "max_total_chars": 180_000,
                },
            },
            "results": [
                {
                    "argos": "fable",
                    "status": "ok",
                    "content": "safe answer",
                }
            ],
            "findings": None,
        }
        return core.EXIT_OK, payload

    def write_session(
        self,
        session_id: str = "adv_20260731T120000_1234abcd",
        *,
        mode: str = "review",
        turn: int = 1,
    ) -> Path:
        session_dir = self.adapter.sessions_root / session_id
        turn_dir = session_dir / "turns" / "001"
        turn_dir.mkdir(parents=True)
        session = {
            "schema_version": 1,
            "id": session_id,
            "name": "Design session",
            "mode": mode,
            "status": "active",
            "created_at": "2026-07-31T12:00:00+00:00",
            "updated_at": "2026-07-31T12:00:01+00:00",
            "artifact_dir": str(session_dir),
            "argoses_requested": ["fable"],
            "personas": {"fable": {"secret_prompt": "do not expose"}},
            "assignments": {"fable": {"role": "partner"}},
            "argoses": {
                "fable": {
                    "status": "alive",
                    "provider_session_id": "provider-secret-id",
                }
            },
            "turn": turn,
            "last_good_turn": turn,
            "last_turn_status": "ok",
            "active_turn": None,
            "config_snapshot": sample_config(),
        }
        if mode == "council":
            session["council"] = {
                "schema_version": 1,
                "synthesis_file": None,
                "source_turn": None,
            }
        (session_dir / "session.json").write_text(
            json.dumps(session),
            encoding="utf-8",
        )
        (turn_dir / "meta.json").write_text(
            json.dumps(
                {
                    "turn": 1,
                    "status": "ok",
                    "results": [
                        {
                            "argos": "fable",
                            "status": "ok",
                            "content": "private full response",
                            "provider_session_id": "provider-secret-id",
                        }
                    ],
                    "inputs_report": {
                        "included": [],
                        "skipped": [],
                        "total_chars": 0,
                    },
                }
            ),
            encoding="utf-8",
        )
        (turn_dir / "final.md").write_text("turn answer", encoding="utf-8")
        return session_dir

    async def test_denied_write_has_zero_filesystem_side_effects(self) -> None:
        response = await self.adapter.argos_run(
            self.run_request(artifact_write=False, model_egress=False)
        )

        self.assertEqual(response["error"]["class"], "approval_required")
        self.assertFalse((self.workspace / ".argos").exists())

    async def test_folder_context_is_accepted_and_core_stdout_stays_silent(self) -> None:
        context_dir = self.workspace / "src"
        context_dir.mkdir()
        (context_dir / "example.py").write_text("answer = 42\n", encoding="utf-8")
        request = self.run_request(
            context={
                "directories": ["src"],
                "include": ["**/*.py"],
            }
        )

        stdout = io.StringIO()
        with patch.object(core, "run_mode", side_effect=self.fake_run):
            with contextlib.redirect_stdout(stdout):
                response = await self.adapter.argos_run(request)

        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["artifact_dir"], ".argos/mcp/runs/review-test")
        self.assertEqual(stdout.getvalue(), "")

    async def test_outside_traversal_ads_and_absolute_paths_are_rejected(self) -> None:
        outside = Path(self.temp.name).parent / "outside-mcp.txt"
        outside.write_text("outside", encoding="utf-8")
        cases = [
            "../outside-mcp.txt",
            str(outside),
            "src/file.txt:secret",
            r"\\server\share\file.txt",
            r"\\?\C:\Windows\win.ini",
        ]
        try:
            for index, path in enumerate(cases):
                request = self.run_request(
                    request_id=f"req-path-{index}",
                    context={"files": [path]},
                )
                response = await self.adapter.argos_run(request)
                self.assertEqual(
                    response["error"]["class"],
                    "path_outside_workspace",
                    path,
                )
            self.assertFalse(self.adapter.requests_root.exists())
        finally:
            outside.unlink(missing_ok=True)

    async def test_symlink_or_reparse_context_is_rejected_when_supported(self) -> None:
        target = self.workspace / "target.txt"
        target.write_text("target", encoding="utf-8")
        link = self.workspace / "link.txt"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("symlink creation is not available")

        response = await self.adapter.argos_run(
            self.run_request(context={"files": ["link.txt"]})
        )

        self.assertEqual(response["error"]["class"], "path_outside_workspace")

    async def test_reparse_context_is_checked_before_resolution(self) -> None:
        target = self.workspace / "target.txt"
        target.write_text("target", encoding="utf-8")
        link = self.workspace / "link.txt"
        link.write_text("simulated link", encoding="utf-8")
        real_resolve = Path.resolve

        def resolve_as_target(path: Path, strict: bool = False) -> Path:
            if path == link:
                return target
            return real_resolve(path, strict=strict)

        with (
            patch.object(Path, "resolve", resolve_as_target),
            patch.object(
                mcp_adapter,
                "_is_link_or_reparse",
                side_effect=lambda path: path == link,
            ),
        ):
            response = await self.adapter.argos_run(
                self.run_request(context={"files": ["link.txt"]})
            )

        self.assertEqual(response["error"]["class"], "path_outside_workspace")

    async def test_idempotent_replay_and_conflict_do_not_rerun_core(self) -> None:
        calls = 0

        async def counted(namespace, *, return_payload=False):
            nonlocal calls
            calls += 1
            return await self.fake_run(namespace, return_payload=return_payload)

        with patch.object(core, "run_mode", side_effect=counted):
            first = await self.adapter.argos_run(self.run_request())
            replay = await self.adapter.argos_run(self.run_request())
            conflict = await self.adapter.argos_run(
                self.run_request(prompt="Different input")
            )

        self.assertEqual(first, replay)
        self.assertEqual(calls, 1)
        self.assertEqual(conflict["error"]["class"], "idempotency_conflict")

    async def test_idempotent_replay_survives_adapter_restart(self) -> None:
        with patch.object(core, "run_mode", side_effect=self.fake_run):
            first = await self.adapter.argos_run(
                self.run_request(request_id="req-restart")
            )

        restarted = mcp_adapter.ArgosMCPAdapter(self.workspace)
        with patch.object(restarted, "_load_config", return_value=sample_config()):
            with patch.object(core, "run_mode") as run_mode:
                replay = await restarted.argos_run(
                    self.run_request(request_id="req-restart")
                )

        self.assertEqual(first, replay)
        self.assertFalse(run_mode.called)

    async def test_duplicate_live_request_reports_in_progress(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocking(namespace, *, return_payload=False):
            started.set()
            await release.wait()
            return await self.fake_run(namespace, return_payload=return_payload)

        with patch.object(core, "run_mode", side_effect=blocking):
            first_task = asyncio.create_task(
                self.adapter.argos_run(self.run_request())
            )
            await started.wait()
            duplicate = await self.adapter.argos_run(self.run_request())
            release.set()
            first = await first_task

        self.assertEqual(duplicate["error"]["class"], "request_in_progress")
        self.assertEqual(first["status"], "completed")

    async def test_dead_claim_becomes_terminal_interrupted_without_rerun(self) -> None:
        request = self.run_request()
        approval = mcp_adapter._approval_for(
            request,
            [
                mcp_contract.ApprovalKind.artifact_write,
                mcp_contract.ApprovalKind.model_egress,
            ],
        )
        self.adapter._claim_request(
            mcp_contract.ToolName.argos_run,
            request,
            approval,
        )

        with patch.object(core, "pid_alive", return_value=False):
            with patch.object(core, "run_mode") as run_mode:
                response = await self.adapter.argos_run(request)

        self.assertEqual(response["error"]["class"], "interrupted")
        self.assertFalse(run_mode.called)
        replay = await self.adapter.argos_run(request)
        self.assertEqual(response, replay)

    async def test_cancelled_request_is_durable_and_reraises_cancellation(self) -> None:
        started = asyncio.Event()

        async def never(namespace, *, return_payload=False):
            started.set()
            await asyncio.Event().wait()

        request = self.run_request()
        with patch.object(core, "run_mode", side_effect=never):
            task = asyncio.create_task(self.adapter.argos_run(request))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        replay = await self.adapter.argos_run(request)
        self.assertEqual(replay["status"], "cancelled")

    async def test_stale_session_turn_is_a_conflict_without_new_turn(self) -> None:
        session_id = "adv_20260731T120000_1234abcd"
        session_dir = self.write_session(session_id)
        request = mcp_contract.AskRequest(
            request_id="req-ask-conflict",
            session_id=session_id,
            expected_turn=0,
            prompt="Next",
            providers=["fable"],
            artifact_write=True,
            model_egress=True,
        )

        async def conflict(namespace, *, return_payload=False):
            raise core.SessionConflictError("private current path and value")

        with patch.object(core, "ask_mode", side_effect=conflict):
            response = await self.adapter.argos_ask(request)

        self.assertEqual(response["error"]["class"], "session_conflict")
        self.assertFalse((session_dir / "turns" / "002").exists())
        self.assertNotIn(str(self.workspace), json.dumps(response))

    async def test_tampered_session_candidate_is_rejected_before_resume(self) -> None:
        session_id = "adv_20260731T120000_1234abcd"
        session_dir = self.write_session(session_id)
        session_path = session_dir / "session.json"
        session = json.loads(session_path.read_text(encoding="utf-8"))
        session["argoses"]["fable"]["candidate"] = {
            "kind": "claude",
            "model": "attacker-model",
            "provider": "claude",
        }
        session_path.write_text(json.dumps(session), encoding="utf-8")
        request = mcp_contract.AskRequest(
            request_id="req-ask-tamper",
            session_id=session_id,
            expected_turn=1,
            prompt="Next",
            providers=["fable"],
            artifact_write=True,
            model_egress=True,
        )

        with patch.object(core, "ask_mode") as ask_mode:
            response = await self.adapter.argos_ask(request)

        self.assertEqual(response["error"]["class"], "session_conflict")
        self.assertFalse(ask_mode.called)
        self.assertFalse((session_dir / "turns" / "002").exists())

    async def test_council_publishes_independent_answers_and_synthesis(self) -> None:
        council_id = "adv_20260731T120000_1234abcd"
        session_dir = self.write_session(council_id, mode="council")
        turn_dir = session_dir / "turns" / "002"
        runner_calls: list[dict[str, object]] = []

        async def fake_ask(namespace, *, return_payload=False):
            turn_dir.mkdir(parents=True)
            (turn_dir / "final.md").write_text(
                "Independent answer",
                encoding="utf-8",
            )
            return core.EXIT_OK, {
                "mode": "council",
                "artifact_dir": str(session_dir),
                "turn_dir": str(turn_dir),
                "turn": 2,
                "inputs_report": {
                    "included": [],
                    "skipped": [],
                    "total_chars": 0,
                },
                "results": [
                    {
                        "argos": "fable",
                        "status": "ok",
                        "content": "Independent answer",
                    }
                ],
            }

        class FakeRunner:
            def __init__(
                fake_self,
                cfg,
                artifact_dir,
                *,
                provider_cwd,
                mode,
            ):
                runner_calls.append(
                    {
                        "cfg": cfg,
                        "artifact_dir": artifact_dir,
                        "provider_cwd": provider_cwd,
                        "mode": mode,
                    }
                )

            async def run_logical(fake_self, argos, prompt, images):
                runner_calls[-1]["argos"] = argos
                return core.ArgosResult(
                    argos=argos,
                    status="ok",
                    content="Council synthesis",
                )

        request = mcp_contract.CouncilPublishRequest(
            request_id="req-council",
            council_id=council_id,
            expected_turn=1,
            prompt="Continue the design",
            artifact_write=True,
            model_egress=True,
        )
        with patch.object(core, "ask_mode", side_effect=fake_ask):
            with patch.object(core, "Runner", FakeRunner):
                with patch.object(
                    core,
                    "publish_council_synthesis",
                    return_value=(core.EXIT_OK, {}),
                ) as publish:
                    response = await self.adapter.argos_council_publish(request)

        self.assertEqual(response["status"], "completed")
        self.assertEqual(
            response["result"]["independent_answers"][0]["content"],
            "Independent answer",
        )
        self.assertEqual(response["result"]["synthesis"], "Council synthesis")
        self.assertEqual(runner_calls[0]["argos"], "fable")
        self.assertEqual(runner_calls[0]["mode"], "council")
        self.assertEqual(
            runner_calls[0]["provider_cwd"],
            session_dir / "provider_cwd",
        )
        publish.assert_called_once()

    async def test_read_tools_are_sanitized_and_do_not_write(self) -> None:
        session_id = "adv_20260731T120000_1234abcd"
        self.write_session(session_id)
        before = {
            path.relative_to(self.workspace).as_posix()
            for path in self.workspace.rglob("*")
        }

        response = await self.adapter.argos_session_show(
            mcp_contract.SessionShowRequest(session_id=session_id)
        )
        health = await self.adapter.argos_health(mcp_contract.HealthRequest())
        after = {
            path.relative_to(self.workspace).as_posix()
            for path in self.workspace.rglob("*")
        }
        serialized = json.dumps(response)

        self.assertEqual(response["status"], "completed")
        self.assertNotIn("provider-secret-id", serialized)
        self.assertNotIn("secret_prompt", serialized)
        self.assertNotIn(str(self.workspace), serialized)
        self.assertEqual(health["result"]["allowed_roots"], ["."])
        self.assertEqual(before, after)

    async def test_session_cursor_detects_changed_selection(self) -> None:
        self.write_session("adv_20260731T120000_1234abcd")
        first = await self.adapter.argos_session_list(
            mcp_contract.SessionListRequest(limit=1)
        )
        self.write_session("adv_20260731T120001_abcdef12")

        changed = await self.adapter.argos_session_list(
            mcp_contract.SessionListRequest(
                limit=1,
                cursor=first["result"]["next_cursor"],
            )
        )

        # A one-row result has no next cursor, so explicitly create one from
        # the original selection fingerprint for the stale-cursor check.
        if first["result"]["next_cursor"] is None:
            stale = mcp_contract.encode_cursor(
                selection_fingerprint=mcp_adapter._selection_fingerprint(
                    [
                        {
                            "session_id": "adv_20260731T120000_1234abcd",
                            "updated_at": "2026-07-31T12:00:01+00:00",
                            "turn": 1,
                        }
                    ]
                ),
                offset=1,
            )
            changed = await self.adapter.argos_session_list(
                mcp_contract.SessionListRequest(limit=1, cursor=stale)
            )
        self.assertEqual(changed["error"]["class"], "invalid_input")

    async def test_research_insufficient_is_not_reported_as_failure(self) -> None:
        request = mcp_contract.ResearchRequest(
            request_id="req-research",
            prompt="What is supported?",
            research_profile="docs",
            artifact_write=True,
            retrieval_egress=True,
            model_egress=False,
        )

        async def fake_research(namespace, *, return_payload=False):
            self.assertEqual(namespace.profile, "docs")
            self.assertTrue(namespace.strict_topic)
            self.assertTrue(namespace.no_model)
            artifact = Path(namespace.artifact_root) / "research-test"
            artifact.mkdir(parents=True, exist_ok=True)
            (artifact / "report.md").write_text(
                "Deterministic report",
                encoding="utf-8",
            )
            (artifact / "query_plan.json").write_text("[]", encoding="utf-8")
            (artifact / "coverage.json").write_text(
                json.dumps({"status": "insufficient"}),
                encoding="utf-8",
            )
            (artifact / "evidence.json").write_text("[]", encoding="utf-8")
            return core.EXIT_ERROR, {
                "artifact_dir": str(artifact),
                "profile": "docs",
                "coverage": {
                    "status": "insufficient",
                    "model_allowed": False,
                },
                "verification": {"status": "insufficient"},
                "evidence_count": 0,
            }

        with patch.object(core, "sota_mode", side_effect=fake_research):
            response = await self.adapter.argos_research(request)

        self.assertEqual(response["status"], "insufficient")
        self.assertIsNone(response["error"])

    async def test_resource_misses_are_uniform_and_manifest_hides_ledger_details(self) -> None:
        with patch.object(core, "run_mode", side_effect=self.fake_run):
            await self.adapter.argos_run(self.run_request())

        manifest = await self.adapter.read_resource(
            "argos://runs/req-run/manifest"
        )
        self.assertNotIn("input_hash", manifest)
        self.assertNotIn('"pid"', manifest)
        self.assertNotIn(str(self.workspace), manifest)

        messages = []
        for uri in (
            "argos://runs/missing/manifest",
            "argos://runs/../../manifest",
            "file:///etc/passwd",
        ):
            with self.assertRaises(mcp_adapter.ResourceNotFoundError) as caught:
                await self.adapter.read_resource(uri)
            messages.append(str(caught.exception))
        self.assertEqual(messages, ["Argos resource not found"] * 3)


if __name__ == "__main__":
    unittest.main()
