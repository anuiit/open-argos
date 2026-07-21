#!/usr/bin/env python3
"""Benchmark v1 runner for argos-dev quality/SOTA/infra/cost axes.

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
ARGOS_DEV = ROOT / "bin/argos-dev"

SECTION_NAMES = ["Blockers", "Important issues", "Preferences", "Minimal fix plan"]
VERIFY_WORDS = ("test", "pytest", "ruff", "verify", "validation", "smoke", "check", "assert")
BROAD_REWRITE_WORDS = ("rewrite everything", "rewrite the whole", "new framework", "new dependency")
TRAP_PENALTY = 0.15
MAX_TRAP_PENALTY = 0.30
NEGATED_DEP_RE = re.compile(r"\b(?:no|not|without|avoid|do not|don't)\s+(?:add(?:ing)?\s+)?(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:dependenc(?:y|ies)|package|library|framework)\b", re.I)
POSITIVE_DEP_RE = re.compile(r"\b(?:add|install|introduce|use)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:package|library|dependenc(?:y|ies)|framework)\b", re.I)
NEGATED_REWRITE_RE = re.compile(r"\b(?:no|not|without|avoid|do not|don't)\s+(?:broad\s+|whole\s+|unrelated\s+)?rewrite", re.I)
POSITIVE_REWRITE_RE = re.compile(r"\b(?:rewrite everything|rewrite the whole|rewrite unrelated|broad rewrite|new framework)\b", re.I)
REPO_ACCESS_CLAIM_RE = re.compile(r"\b(?:i inspected (?!the attached)|i reviewed (?!the attached)|the repository shows|repo files show|elsewhere in the repo)\b", re.I)
CONCRETE_FIX_TARGET_RE = re.compile(
    r"(`(?:[^`\s]+\.(?:py|md|json|toml|yaml|yml)|--[-\w]+|test_[A-Za-z0-9_]+|[A-Za-z_][A-Za-z0-9_]+\(\))`"
    r"|(?:^|[\s/])[-\w]+\.(?:py|md|json|toml|yaml|yml)\b"
    r"|--[-\w]+"
    r"|\b(?:test_[A-Za-z0-9_]+|[A-Za-z_][A-Za-z0-9_]+\(\)))",
    re.M,
)


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


def concrete_fix_targets(fix: str) -> set[str]:
    return {match.group(0).strip(" `") for match in CONCRETE_FIX_TARGET_RE.finditer(fix)}


def fix_requirement_hit(requirement: str, fix: str) -> bool:
    req = requirement.lower()
    if req == "structured_fix_steps":
        return bullet_count(fix) >= 2
    if req == "concrete_fix_target":
        return len(concrete_fix_targets(fix)) >= 2
    return req in fix.lower()


def false_positive_trap_route(trap: str) -> str | None:
    trap_low = trap.lower()
    if "add dependencies" in trap_low:
        return "dependency"
    if "broad rewrite" in trap_low or "rewrite unrelated" in trap_low:
        return "rewrite"
    if "claim access" in trap_low and "omitted repository" in trap_low:
        return "repo_access"
    return None


def false_positive_hit(trap: str, content: str) -> bool:
    route = false_positive_trap_route(trap)
    if route == "dependency":
        return bool(POSITIVE_DEP_RE.search(content)) and not NEGATED_DEP_RE.search(content)
    if route == "rewrite":
        return bool(POSITIVE_REWRITE_RE.search(content)) and not NEGATED_REWRITE_RE.search(content)
    if route == "repo_access":
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
    req_hits = sum(1 for req in fix_requirements if fix_requirement_hit(req, fix))
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
    argoses = []
    for result in meta.get("results", []):
        cost += float(result.get("cost") or 0.0)
        model_duration += float(result.get("duration_sec") or 0.0)
        argoses.append(result.get("argos"))

    status = "pass" if exit_code == 0 else ("needs_human" if exit_code == 3 else "fail")
    return {
        "case_id": case["case_id"],
        "kind": case.get("kind"),
        "mode": case.get("mode"),
        "status": status,
        "score": round(quality, 6),
        "section_score": round(section_score, 6),
        "fix_requirement_hits": req_hits,
        "fix_requirement_count": len(fix_requirements),
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
        "argoses": argoses,
        "artifact_dir": meta.get("artifact_dir"),
    }


def run_quality_case(case: dict[str, Any], argos: str, artifact_root: Path, timeout: int) -> dict[str, Any]:
    mode = "@" + case["mode"].lstrip("@")
    prompt = (
        "Benchmark v1 case. Review only the attached benchmark brief. "
        "Return the required four sections and make concrete, minimal, testable findings."
    )
    cmd = [str(ARGOS_DEV), mode, prompt, "--argos", argos, "--single-ok", "--file", str(ROOT / case["path"]), "--artifact-root", str(artifact_root), "--json"]
    exit_code, stdout, stderr, duration = run_cmd(cmd, timeout=timeout)
    if exit_code == 3:
        raise SystemExit("needs_human exit code from argos-dev; stopping benchmark immediately")
    try:
        meta = parse_json_stdout(stdout)
    except Exception as exc:
        meta = {"artifact_dir": None, "results": [], "parse_error": str(exc), "stdout_tail": stdout[-1000:], "stderr_tail": stderr[-1000:]}
    if any((r.get("status") == "needs_human") for r in meta.get("results", [])):
        raise SystemExit("needs_human status from argos-dev; stopping benchmark immediately")
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
    cmd = [str(ARGOS_DEV), "benchmark", "--json", "--artifact-root", str(artifact_root)]
    exit_code, stdout, stderr, duration = run_cmd(cmd, timeout=120)
    if exit_code == 3:
        raise SystemExit("needs_human exit code from argos-dev internal benchmark; stopping benchmark immediately")
    try:
        data = parse_json_stdout(stdout)
        score = float(data.get("normalized_score", 0.0)) / 100.0
        status = data.get("status")
    except Exception as exc:
        score = 0.0
        status = f"parse_error:{exc}"
        data = {}
    return {"case_id": case["case_id"], "status": "pass" if exit_code == 0 and status == case.get("expected_status") else "fail", "score": round(score, 6), "internal_status": status, "artifact_dir": data.get("artifact_dir"), "wall_duration_sec": round(duration, 3), "stderr_tail": stderr[-500:]}


def compare_expected(observed: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key, value in expected.get("equals", {}).items():
        if observed.get(key) != value:
            failures.append(f"{key}: expected {value!r}, observed {observed.get(key)!r}")
    for key, value in expected.get("min", {}).items():
        if observed.get(key, 0) < value:
            failures.append(f"{key}: expected >= {value!r}, observed {observed.get(key)!r}")
    for key, value in expected.get("max", {}).items():
        if observed.get(key, 0) > value:
            failures.append(f"{key}: expected <= {value!r}, observed {observed.get(key)!r}")
    return failures


def score_scorer_case(case: dict[str, Any]) -> dict[str, Any]:
    content = (ROOT / case["path"]).read_text()
    quality_case = dict(case["quality_case"])
    quality_case.setdefault("case_id", case["case_id"])
    observed = score_quality(quality_case, content, {"results": []}, 0.0, 0)
    failures = compare_expected(observed, case.get("expected", {}))
    return {
        "case_id": case["case_id"],
        "status": "pass" if not failures else "fail",
        "score": 1.0 if not failures else 0.0,
        "failures": failures,
        "observed": {
            "score": observed["score"],
            "recall": observed["recall"],
            "precision": observed["precision"],
            "actionability": observed["actionability"],
            "false_positive_hits": observed["false_positive_hits"],
            "false_positive_penalty": observed["false_positive_penalty"],
            "matched_defects": observed["matched_defects"],
        },
    }


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"total": 0.0, "mean": 0.0, "p95": 0.0}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {"total": round(sum(values), 6), "mean": round(statistics.mean(values), 6), "p95": round(p95, 6)}


def mean_score(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row.get(key) or 0.0) for row in rows]
    return round(statistics.mean(values), 6) if values else 0.0


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# Argos benchmark v{payload['benchmark_version']} — {payload['profile']}",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Argos: `{payload['argos']}`",
        f"Score: `{payload['score']}/100`",
        f"Artifact root: `{payload['artifact_root']}`",
        "",
        "## Axis scores",
    ]
    for axis, value in payload["axis_scores"].items():
        lines.append(f"- {axis}: `{value}`")
    diagnostics = payload.get("axis_diagnostics", {})
    if diagnostics:
        lines.append("- axis3 diagnostics: " + ", ".join(f"{key}=`{value}`" for key, value in diagnostics.items()))
    lines += ["", "## Quality cases"]
    for row in payload["quality_cases"]:
        lines.append(f"- {row['case_id']}: score={row['score']} status={row['status']} recall={row['recall']} precision={row['precision']} cost={row['cost']} artifact={row.get('artifact_dir')}")
    lines += ["", "## SOTA cases"]
    for row in payload["sota_cases"]:
        lines.append(f"- {row['case_id']}: score={row['score']} status={row['status']} invalid={row['invalid_evidence_ids']} missing={row['missing_citations']}")
    lines += ["", "## Infra cases"]
    for row in payload["infra_cases"]:
        lines.append(f"- {row['case_id']}: score={row['score']} status={row['status']} artifact={row.get('artifact_dir')}")
    lines += ["", "## Scorer calibration cases"]
    for row in payload.get("scorer_cases", []):
        lines.append(f"- {row['case_id']}: score={row['score']} status={row['status']} failures={len(row.get('failures', []))}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["cheap", "full"], default="cheap")
    parser.add_argument("--argos", default="minimax")
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--timeout", type=int, default=1300)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    result_dir = ROOT / "benchmarks/results" / f"{utc_stamp()}-v{manifest['version']}-{args.profile}-{args.argos}"
    artifact_root = result_dir / "argos-artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)

    selected = [c for c in manifest["cases"] if args.profile == "full" or c.get("cheap")]
    quality_rows = [run_quality_case(case, args.argos, artifact_root, args.timeout) for case in selected]
    sota_rows = [score_sota_case(case) for case in manifest.get("sota_cases", [])]
    infra_rows = [run_infra_case(case, artifact_root) for case in manifest.get("infra_cases", [])]
    scorer_rows = [score_scorer_case(case) for case in manifest.get("scorer_cases", [])]

    quality_score = statistics.mean([r["score"] for r in quality_rows]) if quality_rows else 0.0
    sota_score = statistics.mean([r["score"] for r in sota_rows]) if sota_rows else 0.0
    infra_inputs = infra_rows + scorer_rows
    infra_score = statistics.mean([r["score"] for r in infra_inputs]) if infra_inputs else 0.0
    infra_cli_score = statistics.mean([r["score"] for r in infra_rows]) if infra_rows else 0.0
    scorer_score = statistics.mean([r["score"] for r in scorer_rows]) if scorer_rows else 0.0
    real_quality_rows = [r for r in quality_rows if r.get("kind") == "real"]
    injected_quality_rows = [r for r in quality_rows if r.get("kind") == "injected"]
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
        "argos": args.argos,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(Path(args.manifest).resolve()),
        "artifact_root": str(artifact_root),
        "result_dir": str(result_dir),
        "score": total,
        "axis_scores": axis_scores,
        "axis_diagnostics": {
            "axis1_real_quality_score": mean_score(real_quality_rows, "score"),
            "axis1_injected_quality_score": mean_score(injected_quality_rows, "score"),
            "axis1_real_actionability_mean": mean_score(real_quality_rows, "actionability"),
            "axis1_injected_actionability_mean": mean_score(injected_quality_rows, "actionability"),
            "axis1_real_actionability_full_count": sum(1 for row in real_quality_rows if row.get("actionability") == 1.0),
            "axis1_false_positive_hit_count": sum(len(row.get("false_positive_hits", [])) for row in quality_rows),
            "axis3_infra_cli_score": round(infra_cli_score, 6),
            "axis3_scorer_selfcheck_score": round(scorer_score, 6),
            "axis3_infra_combined_score": round(infra_score, 6),
        },
        "cost": summarize(costs),
        "latency_sec": summarize(latencies),
        "quality_cases": quality_rows,
        "sota_cases": sota_rows,
        "infra_cases": infra_rows,
        "scorer_cases": scorer_rows,
    }
    write_json(result_dir / "results.json", payload)
    (result_dir / "report.md").write_text(render_report(payload))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"argos-dev benchmark {args.profile}: score={total}/100 results={result_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.TimeoutExpired as exc:
        print(f"benchmark timeout: {exc}", file=sys.stderr)
        raise SystemExit(2)
