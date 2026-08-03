from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SMOKE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_argos_tools.py"
ADVERSARIAL_SMOKE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "adversarial_smoke_argos_tools.py"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("smoke_argos_tools_under_test", SMOKE_PATH)
assert spec and spec.loader
smoke = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = smoke
spec.loader.exec_module(smoke)
adv_spec = importlib.util.spec_from_file_location("adversarial_smoke_argos_tools_under_test", ADVERSARIAL_SMOKE_PATH)
assert adv_spec and adv_spec.loader
adversarial = importlib.util.module_from_spec(adv_spec)
sys.modules[adv_spec.name] = adversarial
adv_spec.loader.exec_module(adversarial)


def completed(cmd: list[str], stdout: str, stderr: str = "", rc: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr=stderr)


class WindowsCommandResolutionTests(unittest.TestCase):
    def test_smoke_resolves_windows_cmd_shim(self) -> None:
        with mock.patch.object(smoke, "IS_WINDOWS", True), mock.patch.object(
            smoke.shutil, "which", return_value=r"C:\Users\test\bin\argos.CMD"
        ):
            resolved = smoke.resolve_command(["argos", "doctor"])
        self.assertEqual(resolved, [r"C:\Users\test\bin\argos.CMD", "doctor"])

    def test_adversarial_smoke_resolves_windows_cmd_shim(self) -> None:
        with mock.patch.object(adversarial, "IS_WINDOWS", True), mock.patch.object(
            adversarial.shutil, "which", return_value=r"C:\Users\test\bin\argos.CMD"
        ):
            resolved = adversarial.resolve_command(["argos", "ping", "--json"])
        self.assertEqual(resolved, [r"C:\Users\test\bin\argos.CMD", "ping", "--json"])

    def test_adversarial_smoke_defaults_to_repo_argos_when_available(self) -> None:
        expected = (Path(__file__).resolve().parents[2] / "argos" / "argos.py").resolve()
        self.assertEqual(adversarial.DEFAULT_ARGOS_PY, expected)


class SmokeAdvToolsTests(unittest.TestCase):
    def run_main(self, argv: list[str], fake_run):
        out = io.StringIO()
        err = io.StringIO()
        with mock.patch.object(sys, "argv", ["smoke_argos_tools.py", *argv]), \
            mock.patch.object(smoke, "run", side_effect=fake_run), \
            contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
            rc = smoke.main()
        return rc, out.getvalue(), err.getvalue()

    def test_council_preauthorizes_relevant_repository_source_egress(self) -> None:
        council = (PLUGIN_ROOT / "skills" / "argos-council" / "SKILL.md").read_text(
            encoding="utf-8"
        ).lower()
        context_contract = (
            PLUGIN_ROOT / "references" / "argos-context-contract.md"
        ).read_text(encoding="utf-8").lower()

        for text in (council, context_contract):
            self.assertIn("standing authorization", text)
            self.assertIn("internal, private, proprietary, or unpublished", text)
            self.assertIn("do not ask", text)
        self.assertIn("--file", council)
        self.assertIn("--dir", council)

    def test_default_smoke_runs_static_checks_and_gate_only(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["argos", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_argoses": True}}))
            if cmd == ["argos", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["argos", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:3] == ["argos", "gate", "set"]:
                return completed(cmd, "argos-tools-smoke\tpass\t/tmp/gate.json")
            self.fail(f"unexpected command: {cmd}")

        rc, out, _err = self.run_main([], fake_run)
        self.assertEqual(rc, 0)
        self.assertIn("Argos-Tools smoke: PASS", out)
        self.assertEqual(calls, [
            ["argos", "doctor"],
            ["argos", "ping", "--json"],
            ["argos", "providers", "--json"],
            ["argos", "gate", "set", "argos-tools-smoke", "pass", "--evidence", "smoke script static checks passed"],
        ])

    def test_no_gate_skips_gate_write(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["argos", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_argoses": True}}))
            if cmd == ["argos", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["argos", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            self.fail(f"unexpected command: {cmd}")

        rc, out, _err = self.run_main(["--no-gate"], fake_run)
        self.assertEqual(rc, 0)
        self.assertIn("Argos-Tools smoke: PASS", out)
        self.assertFalse(any(cmd[:3] == ["argos", "gate", "set"] for cmd in calls))


    def test_malformed_json_fails_with_context_not_traceback(self) -> None:
        def fake_run(cmd, **kwargs):
            if cmd == ["argos", "doctor"]:
                return completed(cmd, "warning\n{", "doctor stderr")
            self.fail(f"unexpected command: {cmd}")

        with mock.patch.object(sys, "argv", ["smoke_argos_tools.py"]), \
            mock.patch.object(smoke, "run", side_effect=fake_run):
            with self.assertRaises(SystemExit) as raised:
                smoke.main()
        self.assertIn("argos doctor did not return valid JSON", str(raised.exception))
        self.assertIn("stdout tail", str(raised.exception))

    def test_nonzero_doctor_fails_closed_before_other_checks(self) -> None:
        def fake_run(cmd, **kwargs):
            if cmd == ["argos", "doctor"]:
                return completed(
                    cmd,
                    json.dumps(
                        {
                            "readiness": {
                                "core_text_argoses": False,
                                "optional_agy_vision_cli": False,
                            }
                        }
                    ),
                    rc=2,
                )
            self.fail(f"unexpected command after failed doctor: {cmd}")

        with self.assertRaisesRegex(
            SystemExit, "argos doctor returned 2; core text argos are not ready"
        ):
            self.run_main(["--no-gate"], fake_run)

    def test_live_text_requires_core_readiness(self) -> None:
        def fake_run(cmd, **kwargs):
            if cmd == ["argos", "doctor"]:
                return completed(
                    cmd,
                    json.dumps(
                        {
                            "readiness": {
                                "core_text_argoses": False,
                                "optional_agy_vision_cli": True,
                            }
                        }
                    ),
                )
            if cmd == ["argos", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["argos", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            self.fail(f"unexpected command: {cmd}")

        with self.assertRaisesRegex(
            SystemExit, "--live text smoke requires core text argos"
        ):
            self.run_main(["--live", "--no-gate"], fake_run)

    def test_vision_implies_live_but_does_not_run_text_live_branch(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["argos", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_argoses": True, "optional_agy_vision_cli": True}}))
            if cmd == ["argos", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["argos", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:3] == ["argos", "gate", "set"]:
                return completed(cmd, "ok")
            if cmd[:4] == ["argos", "run", "vision", "Identify the two main colors only."]:
                return completed(cmd, json.dumps({"status": "ok"}))
            self.fail(f"unexpected command: {cmd}")

        with mock.patch.object(smoke, "write_png", lambda path: path.write_bytes(b"png")):
            rc, _out, _err = self.run_main(["--vision"], fake_run)
        self.assertEqual(rc, 0)
        self.assertTrue(any(cmd[:3] == ["argos", "run", "vision"] for cmd in calls))
        self.assertFalse(any(cmd[:3] == ["argos", "run", "review"] for cmd in calls))

    def test_research_accepts_exit_two_when_artifacts_exist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "research-artifact"
            artifact.mkdir()
            (artifact / "report.md").write_text("report", encoding="utf-8")

            def fake_run(cmd, **kwargs):
                if cmd == ["argos", "doctor"]:
                    return completed(cmd, json.dumps({"readiness": {"core_text_argoses": True}}))
                if cmd == ["argos", "ping", "--json"]:
                    return completed(cmd, json.dumps({"status": "ok"}))
                if cmd == ["argos", "providers", "--json"]:
                    return completed(cmd, json.dumps({"status": "ok"}))
                if cmd[:3] == ["argos", "gate", "set"]:
                    return completed(cmd, "ok")
                if cmd[:2] == ["argos", "research"]:
                    return completed(cmd, json.dumps({"mode": "research", "artifact_dir": str(artifact)}), rc=2)
                self.fail(f"unexpected command: {cmd}")

            rc, out, _err = self.run_main(["--research"], fake_run)
        self.assertEqual(rc, 0)
        self.assertIn("Argos-Tools smoke: PASS", out)

    def test_research_rejects_crash_even_when_stdout_is_valid_json(self) -> None:
        def fake_run(cmd, **kwargs):
            if cmd == ["argos", "doctor"]:
                return completed(
                    cmd, json.dumps({"readiness": {"core_text_argoses": True}})
                )
            if cmd == ["argos", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["argos", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:2] == ["argos", "research"]:
                return completed(
                    cmd,
                    json.dumps(
                        {
                            "mode": "research",
                            "artifact_dir": "unused-valid-looking-path",
                        }
                    ),
                    rc=1,
                )
            self.fail(f"unexpected command: {cmd}")

        with self.assertRaisesRegex(
            SystemExit, "argos research smoke crashed \\(1\\)"
        ):
            self.run_main(["--research", "--no-gate"], fake_run)

    def test_adversarial_flag_runs_adversarial_suite_after_static_checks(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["argos", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_argoses": True}}))
            if cmd == ["argos", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["argos", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:3] == ["argos", "gate", "set"]:
                return completed(cmd, "ok")
            if cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)]:
                return completed(cmd, "Argos-Tools adversarial smoke: PASS")
            self.fail(f"unexpected command: {cmd}")

        rc, out, _err = self.run_main(["--adversarial"], fake_run)
        self.assertEqual(rc, 0)
        self.assertIn("Argos-Tools smoke: PASS", out)
        self.assertTrue(any(cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)] for cmd in calls))

    def test_adversarial_research_live_flag_is_forwarded(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["argos", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_argoses": True}}))
            if cmd == ["argos", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["argos", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:3] == ["argos", "gate", "set"]:
                return completed(cmd, "ok")
            if cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)]:
                return completed(cmd, "ok")
            self.fail(f"unexpected command: {cmd}")

        rc, _out, _err = self.run_main(["--adversarial", "--adversarial-research-live"], fake_run)
        self.assertEqual(rc, 0)
        adversarial_calls = [cmd for cmd in calls if cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)]]
        self.assertEqual(adversarial_calls, [[sys.executable, str(ADVERSARIAL_SMOKE_PATH), "--research-live"]])

    def test_adversarial_argos_py_flag_is_forwarded(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["argos", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_argoses": True}}))
            if cmd == ["argos", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["argos", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:3] == ["argos", "gate", "set"]:
                return completed(cmd, "ok")
            if cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)]:
                return completed(cmd, "ok")
            self.fail(f"unexpected command: {cmd}")

        rc, _out, _err = self.run_main(["--adversarial", "--argos-py", "/tmp/custom-argos.py"], fake_run)
        self.assertEqual(rc, 0)
        adversarial_calls = [cmd for cmd in calls if cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)]]
        self.assertEqual(adversarial_calls, [[sys.executable, str(ADVERSARIAL_SMOKE_PATH), "--argos-py", "/tmp/custom-argos.py"]])


class AdversarialSmokeTests(unittest.TestCase):
    def test_feature_requires_exactly_two_checks(self) -> None:
        suite = adversarial.Suite(argos=object())
        with self.assertRaises(AssertionError):
            suite.feature("bad", [("one", lambda: None)])


    def test_check_accumulates_failures_without_raising_immediately(self) -> None:
        suite = adversarial.Suite(argos=object())
        suite.check("feature", "bad", lambda: (_ for _ in ()).throw(AssertionError("boom")))
        suite.check("feature", "good", lambda: None)
        self.assertEqual([row["status"] for row in suite.results], ["fail", "pass"])
        self.assertIn("boom", suite.results[0]["error"])

    def test_parse_json_reports_context_on_malformed_output(self) -> None:
        proc = completed(["cmd"], "warning\n{", "stderr tail")
        with self.assertRaises(AssertionError) as raised:
            adversarial.parse_json(proc, "bad json")
        self.assertIn("bad json invalid JSON", str(raised.exception))
        self.assertIn("stderr tail", str(raised.exception))


class DocCommandShapeTests(unittest.TestCase):
    def test_argos_plan_skill_has_explicit_workflow_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skill = root / "skills" / "argos-plan" / "SKILL.md"
        text = skill.read_text(encoding="utf-8").lower()
        for needle in (
            "light",
            "medium",
            "high",
            "plan-only",
            "argos run plan",
            "argos run review",
            "argos run critique",
            "implementation",
            "review",
            "critique",
            "default to `medium`",
            "1–3",
        ):
            self.assertIn(needle, text)
        profile_path = root / "references" / "delivery-profiles.md"
        self.assertTrue(profile_path.is_file(), f"missing {profile_path}")

    def test_one_shot_docs_prefer_shell_neutral_run_forms(self) -> None:
        root = Path(__file__).resolve().parents[1]
        pattern = re.compile(
            r'argos\s+(?:run\s+)?"?@(review|critique|plan|debug|consensus|ui|vision|star)"?\b'
        )
        offending: list[str] = []

        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text):
                offending.append(str(path.relative_to(root)))

        self.assertEqual(offending, [], f"Found fragile one-shot aliases in: {offending}")


if __name__ == "__main__":
    unittest.main()
