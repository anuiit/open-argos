from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SMOKE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_mos_tools.py"
ADVERSARIAL_SMOKE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "adversarial_smoke_mos_tools.py"
spec = importlib.util.spec_from_file_location("smoke_mos_tools_under_test", SMOKE_PATH)
assert spec and spec.loader
smoke = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = smoke
spec.loader.exec_module(smoke)
adv_spec = importlib.util.spec_from_file_location("adversarial_smoke_mos_tools_under_test", ADVERSARIAL_SMOKE_PATH)
assert adv_spec and adv_spec.loader
adversarial = importlib.util.module_from_spec(adv_spec)
sys.modules[adv_spec.name] = adversarial
adv_spec.loader.exec_module(adversarial)


def completed(cmd: list[str], stdout: str, stderr: str = "", rc: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr=stderr)


class SmokeAdvToolsTests(unittest.TestCase):
    def run_main(self, argv: list[str], fake_run):
        out = io.StringIO()
        err = io.StringIO()
        with mock.patch.object(sys, "argv", ["smoke_mos_tools.py", *argv]), \
            mock.patch.object(smoke, "run", side_effect=fake_run), \
            contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
            rc = smoke.main()
        return rc, out.getvalue(), err.getvalue()

    def test_default_smoke_runs_static_checks_and_gate_only(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["mosaic", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_mosaics": True}}))
            if cmd == ["mosaic", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["mosaic", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:3] == ["mosaic", "gate", "set"]:
                return completed(cmd, "mos-tools-smoke\tpass\t/tmp/gate.json")
            self.fail(f"unexpected command: {cmd}")

        rc, out, _err = self.run_main([], fake_run)
        self.assertEqual(rc, 0)
        self.assertIn("Mos-Tools smoke: PASS", out)
        self.assertEqual(calls, [
            ["mosaic", "doctor"],
            ["mosaic", "ping", "--json"],
            ["mosaic", "providers", "--json"],
            ["mosaic", "gate", "set", "mos-tools-smoke", "pass", "--evidence", "smoke script static checks passed"],
        ])

    def test_no_gate_skips_gate_write(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["mosaic", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_mosaics": True}}))
            if cmd == ["mosaic", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["mosaic", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            self.fail(f"unexpected command: {cmd}")

        rc, out, _err = self.run_main(["--no-gate"], fake_run)
        self.assertEqual(rc, 0)
        self.assertIn("Mos-Tools smoke: PASS", out)
        self.assertFalse(any(cmd[:3] == ["mosaic", "gate", "set"] for cmd in calls))


    def test_malformed_json_fails_with_context_not_traceback(self) -> None:
        def fake_run(cmd, **kwargs):
            if cmd == ["mosaic", "doctor"]:
                return completed(cmd, "warning\n{", "doctor stderr")
            self.fail(f"unexpected command: {cmd}")

        with mock.patch.object(sys, "argv", ["smoke_mos_tools.py"]), \
            mock.patch.object(smoke, "run", side_effect=fake_run):
            with self.assertRaises(SystemExit) as raised:
                smoke.main()
        self.assertIn("mosaic doctor did not return valid JSON", str(raised.exception))
        self.assertIn("stdout tail", str(raised.exception))

    def test_vision_implies_live_but_does_not_run_text_live_branch(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["mosaic", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_mosaics": True, "optional_agy_vision_cli": True}}))
            if cmd == ["mosaic", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["mosaic", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:3] == ["mosaic", "gate", "set"]:
                return completed(cmd, "ok")
            if cmd[:3] == ["mosaic", "@vision", "Identify the two main colors only."]:
                return completed(cmd, json.dumps({"status": "ok"}))
            self.fail(f"unexpected command: {cmd}")

        with mock.patch.object(smoke, "write_png", lambda path: path.write_bytes(b"png")):
            rc, _out, _err = self.run_main(["--vision"], fake_run)
        self.assertEqual(rc, 0)
        self.assertTrue(any(cmd[:2] == ["mosaic", "@vision"] for cmd in calls))
        self.assertFalse(any(cmd[:2] == ["mosaic", "@review"] for cmd in calls))

    def test_sota_accepts_exit_two_when_artifacts_exist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "sota-artifact"
            artifact.mkdir()
            (artifact / "report.md").write_text("report", encoding="utf-8")

            def fake_run(cmd, **kwargs):
                if cmd == ["mosaic", "doctor"]:
                    return completed(cmd, json.dumps({"readiness": {"core_text_mosaics": True}}))
                if cmd == ["mosaic", "ping", "--json"]:
                    return completed(cmd, json.dumps({"status": "ok"}))
                if cmd == ["mosaic", "providers", "--json"]:
                    return completed(cmd, json.dumps({"status": "ok"}))
                if cmd[:3] == ["mosaic", "gate", "set"]:
                    return completed(cmd, "ok")
                if cmd[:2] == ["mosaic", "sota"]:
                    return completed(cmd, json.dumps({"mode": "sota", "artifact_dir": str(artifact)}), rc=2)
                self.fail(f"unexpected command: {cmd}")

            rc, out, _err = self.run_main(["--sota"], fake_run)
        self.assertEqual(rc, 0)
        self.assertIn("Mos-Tools smoke: PASS", out)

    def test_adversarial_flag_runs_adversarial_suite_after_static_checks(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["mosaic", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_mosaics": True}}))
            if cmd == ["mosaic", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["mosaic", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:3] == ["mosaic", "gate", "set"]:
                return completed(cmd, "ok")
            if cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)]:
                return completed(cmd, "Mos-Tools adversarial smoke: PASS")
            self.fail(f"unexpected command: {cmd}")

        rc, out, _err = self.run_main(["--adversarial"], fake_run)
        self.assertEqual(rc, 0)
        self.assertIn("Mos-Tools smoke: PASS", out)
        self.assertTrue(any(cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)] for cmd in calls))

    def test_adversarial_sota_live_flag_is_forwarded(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["mosaic", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_mosaics": True}}))
            if cmd == ["mosaic", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["mosaic", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:3] == ["mosaic", "gate", "set"]:
                return completed(cmd, "ok")
            if cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)]:
                return completed(cmd, "ok")
            self.fail(f"unexpected command: {cmd}")

        rc, _out, _err = self.run_main(["--adversarial", "--adversarial-sota-live"], fake_run)
        self.assertEqual(rc, 0)
        adversarial_calls = [cmd for cmd in calls if cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)]]
        self.assertEqual(adversarial_calls, [[sys.executable, str(ADVERSARIAL_SMOKE_PATH), "--sota-live"]])

    def test_adversarial_mosaic_py_flag_is_forwarded(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["mosaic", "doctor"]:
                return completed(cmd, json.dumps({"readiness": {"core_text_mosaics": True}}))
            if cmd == ["mosaic", "ping", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd == ["mosaic", "providers", "--json"]:
                return completed(cmd, json.dumps({"status": "ok"}))
            if cmd[:3] == ["mosaic", "gate", "set"]:
                return completed(cmd, "ok")
            if cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)]:
                return completed(cmd, "ok")
            self.fail(f"unexpected command: {cmd}")

        rc, _out, _err = self.run_main(["--adversarial", "--mosaic-py", "/tmp/custom-mosaic.py"], fake_run)
        self.assertEqual(rc, 0)
        adversarial_calls = [cmd for cmd in calls if cmd[:2] == [sys.executable, str(ADVERSARIAL_SMOKE_PATH)]]
        self.assertEqual(adversarial_calls, [[sys.executable, str(ADVERSARIAL_SMOKE_PATH), "--mosaic-py", "/tmp/custom-mosaic.py"]])


class AdversarialSmokeTests(unittest.TestCase):
    def test_feature_requires_exactly_two_checks(self) -> None:
        suite = adversarial.Suite(mosaic=object())
        with self.assertRaises(AssertionError):
            suite.feature("bad", [("one", lambda: None)])


    def test_check_accumulates_failures_without_raising_immediately(self) -> None:
        suite = adversarial.Suite(mosaic=object())
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


if __name__ == "__main__":
    unittest.main()
