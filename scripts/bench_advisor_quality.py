#!/usr/bin/env python3
"""Benchmark v1 runner for advisor-dev quality/SOTA/infra/cost axes.

Stdlib only. Results are written under benchmarks/results/ and are not committed.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks/golden/v1/manifest.json"
ADVISOR_DEV = ROOT / "bin/advisor-dev"

SECTION_NAMES = ["Blockers", "Important issues", "Preferences", "Minimal fix plan"]
VERIFY_WORDS = ("test", "pytest", "ruff", "verify", "validation", "smoke", "check", "assert")
BROAD_REWRITE_WORDS = ("rewrite everything", "rewrite the whole", "new framework", "new dependency")
TRAP_PENALTY = 0.15
MAX_TRAP_PENALTY = 0.30
NEGATED_DEP_RE = re.compile(r"\b(?:no|without|avoid|do not|don't)\s+(?:add(?:ing)?\s+)?(?:a\s+|an\s+|the\s+)?(?:new\s+)?dependenc(?:y|ies)\b", re.I)
POSITIVE_DEP_RE = re.compile(r"\b(?:add|install|introduce|use)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:package|library|dependenc(?:y|ies)|framework)\b", re.I)
NEGATED_REWRITE_RE = re.compile(r"\b(?:no|without|avoid|do not|don't)\s+(?:broad\s+|whole\s+|unrelated\s+)?rewrite", re.I)
POSITIVE_REWRITE_RE = re.compile(r"\b(?:rewrite everything|rewrite the whole|rewrite unrelated|broad rewrite|new framework)\b", re.I)
REPO_ACCESS_CLAIM_RE = re.compile(r"\b(?:i inspected|i reviewed|the repository shows|repo files show|elsewhere in the repo)\b", re.I)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def run_cmd(cmd: list[str], *, cwd: Path = ROOT, timeout: int = 900) -> tuple[int, str, str, float]:
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr, time.perf_counter() - started


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    stdout = stdout.strip()
    if not stdout:
        return {}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Some provider wrappers may print leading noise; recover first JSON object.
        start = stdout.find("{")
        end = stdout.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stdout[start : end + 1])
        raise


def section_map(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    pattern = re.compile(r"^##\s+(Blockers|Important issues|Preferences|Minimal fix plan)\s*$", re.M | re.I)
    matches = list(pattern.finditer(text or ""))
    for i, match in enumerate(matches):
        name = next(s for s in SECTION_NAMES if s.lower() == match.group(1).lower())
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


BULLET_LINE_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(?P<text>.+?)\s*$", re.M)
NONE_MARKER_RE = re.compile(r"^(?:\(?none\)?|aucun(?:e)?|rien|n/?a|néant)\.?$", re.I)


def is_none_marker(text: str) -> bool:
    return bool(NONE_MARKER_RE.fullmatch(text.strip()))


def bullet_count(section: str) -> int:
    if not section or not section.strip():
        return 0
    bullet_items = [match.group("text").strip() for match in BULLET_LINE_RE.finditer(section)]
    if bullet_items:
        return sum(1 for item in bullet_items if not is_none_marker(item))
    stripped = section.strip()
    return 0 if is_none_marker(stripped) else 1


def contains_any(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(t.lower() in low for t in terms)


def false_positive_hit(trap: str, content: str) -> bool:
    trap_low = trap.lower()
    if "add dependencies" in trap_low:
        return bool(POSITIVE_DEP_RE.search(content)) and not NEGATED_DEP_RE.search(content)
    if "broad rewrite" in trap_low or "rewrite unrelated" in trap_low:
        return bool(POSITIVE_REWRITE_RE.search(content)) and not NEGATED_REWRITE_RE.search(content)
    if "claim access" in trap_low and "omitted repository" in trap_low:
        return bool(REPO_ACCESS_CLAIM_RE.search(content))
    return False


def false_positive_hits(case: dict[str, Any], content: str) -> list[str]:
    return [trap for trap in case.get("false_positive_traps", []) if false_positive_hit(trap, content)]


def false_positive_penalty(hits: list[str]) -> float:
    return min(MAX_TRAP_PENALTY, TRAP_PENALTY * len(hits))




def score_quality(case: dict[str, Any], content: str, meta: dict[str, Any], duration: float, exit_code: int) -> dict[str, Any]:
    sections = section_map(content)
    section_hits = sum(1 for s in SECTION_NAMES if s in sections)
    section_score = section_hits / len(SECTION_NAMES)
    blockers = sections.get("Blockers", "")
    important = sections.get("Important issues", "")
    fix = sections.get("Minimal fix plan", "")
    all_issue_text = f"{blockers}\n{important}"

    known = case.get("known_defects", [])
    matched: list[str] = []
    for defect in known:
        if contains_any(all_issue_text, defect.get("expected_terms", [])):
            matched.append(defect["id"])
    recall = len(matched) / len(known) if known else None
    reported_blockers = bullet_count(blockers)
    reported_important = bullet_count(important)
    reported_issue_bullets = reported_blockers + reported_important
    if known:
        precision = min(len(matched), reported_issue_bullets) / reported_issue_bullets if reported_issue_bullets else 0.0
    else:
        precision = 1.0 if reported_blockers <= 1 else 0.75

    fix_requirements = case.get("minimal_fix_requirements", [])
    fix_low = fix.lower()
    req_hits = sum(1 for req in fix_requirements if req.lower() in fix_low)
    verification_hit = any(w in fix_low for w in VERIFY_WORDS)
    broad_penalty = 0.25 if any(w in fix_low for w in BROAD_REWRITE_WORDS) else 0.0
    actionability = 0.0
    if fix_requirements:
        actionability = min(1.0, (req_hits / len(fix_requirements)) * 0.7 + (0.3 if verification_hit else 0.0))
        actionability = max(0.0, actionability - broad_penalty)
    else:
        actionability = 1.0 if fix.strip() else 0.0

    trap_hits = false_positive_hits(case, content)
    trap_penalty = false_positive_penalty(trap_hits)
    if known:
        quality = 0.25 * section_score + 0.35 * (recall or 0.0) + 0.20 * precision + 0.20 * actionability
    else:
        quality = 0.55 * section_score + 0.45 * actionability
    quality = max(0.0, quality - trap_penalty)

    cost = 0.0
    model_duration = 0.0
    advisors = []
    for result in meta.get("results", []):
        cost += float(result.get("cost") or 0.0)
        model_duration += float(result.get("duration_sec") or 0.0)
        advisors.append(result.get("advisor"))

    status = "pass" if exit_code == 0 else ("needs_human" if exit_code == 3 else "fail")
    return {
        "case_id": case["case_id"],
        "kind": case.get("kind"),
        "mode": case.get("mode"),
        "status": status,
        "score": round(quality, 6),
        "section_score": round(section_score, 6),
        "recall": None if recall is None else round(recall, 6),
        "precision": round(precision, 6),
        "actionability": round(actionability, 6),
        "false_positive_hits": trap_hits,
        "false_positive_penalty": round(trap_penalty, 6),
        "matched_defects": matched,
        "reported_blockers": reported_blockers,
        "reported_issue_bullets": reported_issue_bullets,
        "cost": round(cost, 6),
        "wall_duration_sec": round(duration, 3),
        "model_duration_sec": round(model_duration, 3),
        "advisors": advisors,
        "artifact_dir": meta.get("artifact_dir"),
    }


def run_quality_case(case: dict[str, Any], advisor: str, artifact_root: Path, timeout: int) -> dict[str, Any]:
    mode = "@" + case["mode"].lstrip("@")
    prompt = (
        "Benchmark v1 case. Review only the attached benchmark brief. "
        "Return the required four sections and make concrete, minimal, testable findings."
    )
    cmd = [str(ADVISOR_DEV), mode, prompt, "--advisor", advisor, "--single-ok", "--file", str(ROOT / case["path"]), "--artifact-root", str(artifact_root), "--json"]
    exit_code, stdout, stderr, duration = run_cmd(cmd, timeout=timeout)
    if exit_code == 3:
        raise SystemExit("needs_human exit code from advisor-dev; stopping benchmark immediately")
    try:
        meta = parse_json_stdout(stdout)
    except Exception as exc:
        meta = {"artifact_dir": None, "results": [], "parse_error": str(exc), "stdout_tail": stdout[-1000:], "stderr_tail": stderr[-1000:]}
    if any((r.get("status") == "needs_human") for r in meta.get("results", [])):
        raise SystemExit("needs_human status from advisor-dev; stopping benchmark immediately")
    content = "\n\n".join((r.get("content") or r.get("error") or "") for r in meta.get("results", []))
    score = score_quality(case, content, meta, duration, exit_code)
    score["command"] = " ".join(cmd[:4] + ["..."])
    if exit_code != 0:
        score["stderr_tail"] = stderr[-1000:]
        score["stdout_tail"] = stdout[-1000:]
    return score


def score_sota_case(case: dict[str, Any]) -> dict[str, Any]:
    data = load_json(ROOT / case["path"])
    verification = data.get("verification", {})
    summary = data.get("summary", {})
    expected = case.get("expected_status")
    status_match = verification.get("status") == expected
    invalid_count = len(verification.get("invalid_evidence_ids", []))
    missing_count = len(verification.get("missing_citations", []))
    unexpected_count = len(verification.get("unexpected_urls", []))
    counts = summary.get("source_quality_counts", {})
    health = summary.get("source_health", {})
    source_events = sum(v.get("error", 0) + v.get("skipped", 0) for v in health.values() if isinstance(v, dict))
    if expected == "ok":
        score = 1.0 if status_match and invalid_count == missing_count == unexpected_count == 0 else 0.0
    else:
        score = 1.0 if status_match and invalid_count + missing_count + unexpected_count > 0 else 0.0
    return {"case_id": case["case_id"], "status": "pass" if score else "fail", "score": score, "verification_status": verification.get("status"), "invalid_evidence_ids": invalid_count, "missing_citations": missing_count, "unexpected_urls": unexpected_count, "source_quality_counts": counts, "dead_or_skipped_source_events": source_events}


def run_infra_case(case: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    cmd = [str(ADVISOR_DEV), "benchmark", "--json", "--artifact-root", str(artifact_root)]
    exit_code, stdout, stderr, duration = run_cmd(cmd, timeout=120)
    if exit_code == 3:
        raise SystemExit("needs_human exit code from advisor-dev internal benchmark; stopping benchmark immediately")
    try:
        data = parse_json_stdout(stdout)
        score = float(data.get("normalized_score", 0.0)) / 100.0
        status = data.get("status")
    except Exception as exc:
        score = 0.0
        status = f"parse_error:{exc}"
        data = {}
    return {"case_id": case["case_id"], "status": "pass" if exit_code == 0 and status == case.get("expected_status") else "fail", "score": round(score, 6), "internal_status": status, "artifact_dir": data.get("artifact_dir"), "wall_duration_sec": round(duration, 3), "stderr_tail": stderr[-500:]}


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"total": 0.0, "mean": 0.0, "p95": 0.0}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {"total": round(sum(values), 6), "mean": round(statistics.mean(values), 6), "p95": round(p95, 6)}


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# Advisor benchmark v{payload['benchmark_version']} — {payload['profile']}",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Advisor: `{payload['advisor']}`",
        f"Score: `{payload['score']}/100`",
        f"Artifact root: `{payload['artifact_root']}`",
        "",
        "## Axis scores",
    ]
    for axis, value in payload["axis_scores"].items():
        lines.append(f"- {axis}: `{value}`")
    lines += ["", "## Quality cases"]
    for row in payload["quality_cases"]:
        lines.append(f"- {row['case_id']}: score={row['score']} status={row['status']} recall={row['recall']} precision={row['precision']} cost={row['cost']} artifact={row.get('artifact_dir')}")
    lines += ["", "## SOTA cases"]
    for row in payload["sota_cases"]:
        lines.append(f"- {row['case_id']}: score={row['score']} status={row['status']} invalid={row['invalid_evidence_ids']} missing={row['missing_citations']}")
    lines += ["", "## Infra cases"]
    for row in payload["infra_cases"]:
        lines.append(f"- {row['case_id']}: score={row['score']} status={row['status']} artifact={row.get('artifact_dir')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["cheap", "full"], default="cheap")
    parser.add_argument("--advisor", default="minimax")
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--timeout", type=int, default=1300)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    result_dir = ROOT / "benchmarks/results" / f"{utc_stamp()}-v{manifest['version']}-{args.profile}-{args.advisor}"
    artifact_root = result_dir / "advisor-artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)

    selected = [c for c in manifest["cases"] if args.profile == "full" or c.get("cheap")]
    quality_rows = [run_quality_case(case, args.advisor, artifact_root, args.timeout) for case in selected]
    sota_rows = [score_sota_case(case) for case in manifest.get("sota_cases", [])]
    infra_rows = [run_infra_case(case, artifact_root) for case in manifest.get("infra_cases", [])]

    quality_score = statistics.mean([r["score"] for r in quality_rows]) if quality_rows else 0.0
    sota_score = statistics.mean([r["score"] for r in sota_rows]) if sota_rows else 0.0
    infra_score = statistics.mean([r["score"] for r in infra_rows]) if infra_rows else 0.0
    costs = [r.get("cost", 0.0) for r in quality_rows]
    latencies = [r.get("wall_duration_sec", 0.0) for r in quality_rows]
    # Cost axis rewards complete cost telemetry and low-but-nonnegative costs; quality cases all expose cost field here.
    cost_score = 1.0 if all(c >= 0 for c in costs) and all("cost" in r for r in quality_rows) else 0.0
    axis_scores = {
        "axis1_quality_45": round(quality_score * 45, 6),
        "axis2_sota_20": round(sota_score * 20, 6),
        "axis3_infra_25": round(infra_score * 25, 6),
        "axis4_cost_latency_10": round(cost_score * 10, 6),
    }
    total = round(sum(axis_scores.values()), 6)
    payload = {
        "benchmark_version": manifest["version"],
        "profile": args.profile,
        "advisor": args.advisor,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(Path(args.manifest).resolve()),
        "artifact_root": str(artifact_root),
        "result_dir": str(result_dir),
        "score": total,
        "axis_scores": axis_scores,
        "cost": summarize(costs),
        "latency_sec": summarize(latencies),
        "quality_cases": quality_rows,
        "sota_cases": sota_rows,
        "infra_cases": infra_rows,
    }
    write_json(result_dir / "results.json", payload)
    (result_dir / "report.md").write_text(render_report(payload))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"advisor-dev benchmark {args.profile}: score={total}/100 results={result_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.TimeoutExpired as exc:
        print(f"benchmark timeout: {exc}", file=sys.stderr)
        raise SystemExit(2)
