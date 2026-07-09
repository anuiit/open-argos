#!/usr/bin/env python3
"""Non-destructive Adv-Tools/advisor smoke test.

Default mode avoids expensive live multi-advisor presets. Use --live for a tiny
MiniMax text route and agy vision route if local credentials are available. Use
--sota for a public-source retrieval-only SOTA smoke without model spend.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd: list[str], *, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd))
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    if check and proc.returncode != 0:
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return proc


def parse_json_output(proc: subprocess.CompletedProcess[str], label: str) -> dict:
    """Parse a JSON CLI response and fail with context instead of a traceback."""
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        stdout_tail = (proc.stdout or "")[-500:].strip()
        stderr_tail = (proc.stderr or "")[-500:].strip()
        details = []
        if stdout_tail:
            details.append(f"stdout tail: {stdout_tail}")
        if stderr_tail:
            details.append(f"stderr tail: {stderr_tail}")
        context = "; ".join(details) or "no output"
        raise SystemExit(f"{label} did not return valid JSON: {exc}; {context}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} returned JSON {type(payload).__name__}, expected object")
    return payload


def write_png(path: Path) -> None:
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception:
        # Minimal 1x1 PNG fallback is enough for path/MIME smoke; live vision is skipped without Pillow.
        path.write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
            "0000000c4944415408d763f8cfc0000003010100c9fe92ef0000000049454e44ae426082"
        ))
        return
    im = Image.new("RGB", (80, 80), "red")
    ImageDraw.Draw(im).rectangle([20, 20, 60, 60], fill="blue")
    im.save(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="run small paid/live advisor checks")
    parser.add_argument("--vision", action="store_true", help="include agy vision live check; implies --live")
    parser.add_argument("--sota", action="store_true", help="include retrieval-only advisor sota smoke over public sources")
    parser.add_argument("--adversarial", action="store_true", help="run two break-oriented smoke checks per Adv-Tools/advisor feature")
    parser.add_argument("--adversarial-sota-live", action="store_true", help="include bounded public-source SOTA fetch in adversarial smoke")
    parser.add_argument("--advisor-py", help="advisor.py path forwarded to adversarial smoke")
    parser.add_argument("--artifact-root", help="advisor artifact root for gate/SOTA smoke artifacts")
    parser.add_argument("--no-gate", action="store_true", help="skip writing the adv-tools-smoke gate artifact")
    args = parser.parse_args()
    if args.vision:
        args.live = True

    doctor = run(["advisor", "doctor"], check=False)
    doctor_data = parse_json_output(doctor, "advisor doctor")
    core_ready = bool(doctor_data.get("readiness", {}).get("core_text_advisors"))
    agy_ready = bool(doctor_data.get("readiness", {}).get("optional_agy_vision_cli"))
    if doctor.returncode != 0 and not ((args.vision or args.live) and agy_ready):
        raise SystemExit(f"advisor doctor returned {doctor.returncode}; core text advisors are not ready")
    ping = run(["advisor", "ping", "--json"])
    data = parse_json_output(ping, "advisor ping --json")
    if data.get("status") != "ok":
        raise SystemExit("advisor ping returned non-ok status")
    run(["advisor", "providers", "--json"])
    if not args.no_gate:
        gate_cmd = ["advisor", "gate", "set", "adv-tools-smoke", "pass", "--evidence", "smoke script static checks passed"]
        if args.artifact_root:
            gate_cmd.extend(["--artifact-root", args.artifact_root])
        run(gate_cmd)

    if args.live and not args.vision:
        if not core_ready:
            raise SystemExit("--live text smoke requires core text advisors from advisor doctor")
        run(["advisor", "@review", "Smoke test only. Reply PASS.", "--advisor", "minimax", "--single-ok", "--json"], timeout=180)
    if args.vision:
        if not agy_ready:
            raise SystemExit("--vision smoke requires optional_agy_vision_cli from advisor doctor")
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "adv-tools-smoke.png"
            write_png(image)
            run(["advisor", "@vision", "Identify the two main colors only.", "--image", str(image), "--json"], timeout=180)
    if args.adversarial:
        adversarial_cmd = [sys.executable, str(Path(__file__).with_name("adversarial_smoke_adv_tools.py"))]
        if args.advisor_py:
            adversarial_cmd.extend(["--advisor-py", args.advisor_py])
        if args.adversarial_sota_live:
            adversarial_cmd.append("--sota-live")
        run(adversarial_cmd, timeout=180 if not args.adversarial_sota_live else 300)

    if args.sota:
        sota_cmd = [
            "advisor", "sota", "retrieval augmented generation evaluation",
            "--source", "arxiv", "--max-queries", "2", "--max-sources", "4",
            "--timeout", "60", "--no-model", "--json",
        ]
        if args.artifact_root:
            sota_cmd.extend(["--artifact-root", args.artifact_root])
        proc = run(sota_cmd, timeout=120, check=False)
        # SOTA may return EXIT_ERROR (2) for degraded/empty retrieval while still
        # producing diagnostic artifacts; parse and validate the artifact contract below.
        if proc.returncode not in {0, 2}:
            raise SystemExit(f"advisor sota smoke crashed ({proc.returncode})")
        payload = parse_json_output(proc, "advisor sota smoke")
        artifact = Path(payload["artifact_dir"])
        if payload.get("mode") != "sota" or not (artifact / "report.md").exists():
            raise SystemExit("advisor sota smoke did not produce expected artifacts")
    print("Adv-Tools smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
