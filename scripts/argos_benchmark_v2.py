"""Reproducible Argos harness, readiness, output-quality and performance benchmark.

The module is intentionally stdlib-only.  It keeps the deterministic v1
scorer helpers public while implementing a v2 benchmark whose axes cannot hide
one another:

* harness health is provider-free;
* replay fixtures calibrate the scorer and are never model results;
* readiness records launcher/provider outcomes;
* quality and performance exist only for successful live outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks/golden/v2/manifest.json"
LEGACY_MANIFEST = ROOT / "benchmarks/golden/v1/manifest.json"
ARGOS_PY = ROOT / "argos" / "argos.py"
# Kept for compatibility with callers that imported the old constant.  V2
# never executes this shell wrapper.
ARGOS_DEV = ROOT / "bin/argos-dev"

RESULT_SCHEMA_VERSION = 2
SCORER_VERSION = "2.0.0"
PROMPT_PROTOCOL_VERSION = "2.0.0"
MEASUREMENT_PROTOCOL_VERSION = "2.0.0"
ISOLATED_ASSIGNMENT_VERSION = "1"
ISOLATED_ASSIGNMENT = {
    "role": "implementation_reviewer",
    "lenses": ["correctness", "maintainability"],
}

SECTION_NAMES = ["Blockers", "Important issues", "Preferences", "Minimal fix plan"]
VERIFY_WORDS = (
    "test",
    "pytest",
    "ruff",
    "verify",
    "validation",
    "smoke",
    "check",
    "assert",
)
BROAD_REWRITE_WORDS = (
    "rewrite everything",
    "rewrite the whole",
    "new framework",
    "new dependency",
)
TRAP_PENALTY = 0.15
MAX_TRAP_PENALTY = 0.30
NEGATED_DEP_RE = re.compile(
    r"\b(?:no|not|without|avoid|do not|don't)\s+(?:add(?:ing)?\s+)?"
    r"(?:a\s+|an\s+|the\s+)?(?:new\s+)?"
    r"(?:dependenc(?:y|ies)|package|library|framework)\b",
    re.I,
)
POSITIVE_DEP_RE = re.compile(
    r"\b(?:add|install|introduce|use)\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:new\s+)?(?:package|library|dependenc(?:y|ies)|framework)\b",
    re.I,
)
NEGATED_REWRITE_RE = re.compile(
    r"\b(?:no|not|without|avoid|do not|don't)\s+"
    r"(?:broad\s+|whole\s+|unrelated\s+)?rewrite",
    re.I,
)
POSITIVE_REWRITE_RE = re.compile(
    r"\b(?:rewrite everything|rewrite the whole|rewrite unrelated|"
    r"broad rewrite|new framework)\b",
    re.I,
)
REPO_ACCESS_CLAIM_RE = re.compile(
    r"\b(?:i inspected (?!the attached)|i reviewed (?!the attached)|"
    r"the repository shows|repo files show|elsewhere in the repo)\b",
    re.I,
)
CONCRETE_FIX_TARGET_RE = re.compile(
    r"(`(?:[^`\s]+\.(?:py|md|json|toml|yaml|yml)|--[-\w]+|"
    r"test_[A-Za-z0-9_]+|[A-Za-z_][A-Za-z0-9_]+\(\))`"
    r"|(?:^|[\s/])[-\w]+\.(?:py|md|json|toml|yaml|yml)\b"
    r"|--[-\w]+"
    r"|\b(?:test_[A-Za-z0-9_]+|[A-Za-z_][A-Za-z0-9_]+\(\)))",
    re.M,
)
BULLET_LINE_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(?P<text>.+?)\s*$", re.M)
NONE_MARKER_RE = re.compile(
    r"^(?:\(?none\)?|aucun(?:e)?|rien|n/?a|néant)\.?$", re.I
)
HIDDEN_LABEL_RE = re.compile(r"\b(?:C|F|G)\d{2,3}\b", re.I)

PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "offline": {
        "tracks": ["harness", "replay"],
        "launches": ["harness", "replay"],
        "repetitions": 1,
        "max_calls": 0,
        "max_wall_seconds": 180.0,
        "max_cost_usd": 0.0,
        "estimated_cost_per_call_usd": 0.0,
        "argoses": [],
    },
    "smoke": {
        "tracks": ["harness", "replay", "isolated"],
        "launches": ["harness", "replay", "oneshot"],
        "repetitions": 1,
        "max_calls": 1,
        "max_wall_seconds": 300.0,
        "max_cost_usd": 0.50,
        "estimated_cost_per_call_usd": 0.10,
        "argoses": ["sonnet"],
    },
    "cheap": {
        "tracks": ["harness", "replay", "isolated", "production"],
        "launches": ["harness", "replay", "oneshot", "session"],
        "repetitions": 2,
        "max_calls": 32,
        "max_wall_seconds": 2400.0,
        "max_cost_usd": 5.0,
        "estimated_cost_per_call_usd": 0.15,
        "argoses": ["sonnet", "kimi3"],
    },
    "full": {
        "tracks": ["harness", "replay", "isolated", "production"],
        "launches": [
            "harness",
            "replay",
            "oneshot",
            "session",
            "council",
            "debate",
        ],
        "repetitions": 3,
        "max_calls": 140,
        "max_wall_seconds": 14400.0,
        "max_cost_usd": 30.0,
        "estimated_cost_per_call_usd": 0.20,
        "argoses": ["sonnet", "kimi3", "fable"],
    },
}

TRACK_NAMES = ("harness", "replay", "isolated", "production")
LAUNCH_NAMES = ("harness", "replay", "oneshot", "session", "council", "debate")
LIVE_TRACKS = {"isolated", "production"}
LIVE_LAUNCHES = {"oneshot", "session", "council", "debate"}
EXPLOITABLE_STATUSES = {"ok", "replay_ok"}
READINESS_FAILURE_STATUSES = {
    "provider_unavailable",
    "provider_bootstrap_failed",
    "provider_error",
    "launcher_failed",
    "timeout",
    "needs_human",
    "parse_error",
    "outcome_unknown",
    "budget_exhausted",
    "budget_telemetry_missing",
}


class BenchmarkConfigError(ValueError):
    """The benchmark contract or selection is invalid."""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            value = json.loads(text[start : end + 1])
            return value if isinstance(value, dict) else {}
        raise


def section_map(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    pattern = re.compile(
        r"^##\s+(Blockers|Important issues|Preferences|Minimal fix plan)\s*$",
        re.M | re.I,
    )
    matches = list(pattern.finditer(text or ""))
    for index, match in enumerate(matches):
        name = next(
            section
            for section in SECTION_NAMES
            if section.lower() == match.group(1).lower()
        )
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


def is_none_marker(text: str) -> bool:
    return bool(NONE_MARKER_RE.fullmatch(text.strip()))


def bullet_count(section: str) -> int:
    if not section or not section.strip():
        return 0
    bullet_items = [
        match.group("text").strip() for match in BULLET_LINE_RE.finditer(section)
    ]
    if bullet_items:
        return sum(1 for item in bullet_items if not is_none_marker(item))
    stripped = section.strip()
    return 0 if is_none_marker(stripped) else 1


def contains_any(text: str, terms: Sequence[str]) -> bool:
    low = text.lower()
    return any(str(term).lower() in low for term in terms)


def concrete_fix_targets(fix: str) -> set[str]:
    return {
        match.group(0).strip(" `") for match in CONCRETE_FIX_TARGET_RE.finditer(fix)
    }


def fix_requirement_hit(requirement: str, fix: str) -> bool:
    requirement_low = requirement.lower()
    if requirement_low == "structured_fix_steps":
        return bullet_count(fix) >= 2
    if requirement_low == "concrete_fix_target":
        return len(concrete_fix_targets(fix)) >= 2
    return requirement_low in fix.lower()


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
        return bool(POSITIVE_DEP_RE.search(content)) and not NEGATED_DEP_RE.search(
            content
        )
    if route == "rewrite":
        return bool(POSITIVE_REWRITE_RE.search(content)) and not NEGATED_REWRITE_RE.search(
            content
        )
    if route == "repo_access":
        return bool(REPO_ACCESS_CLAIM_RE.search(content))
    return False


def false_positive_hits(case: dict[str, Any], content: str) -> list[str]:
    return [
        trap
        for trap in case.get("false_positive_traps", [])
        if false_positive_hit(str(trap), content)
    ]


def false_positive_penalty(hits: Sequence[str]) -> float:
    return min(MAX_TRAP_PENALTY, TRAP_PENALTY * len(hits))


def score_quality(
    case: dict[str, Any],
    content: str,
    meta: dict[str, Any],
    duration: float,
    exit_code: int,
) -> dict[str, Any]:
    """Original v1 deterministic scorer, retained byte-for-byte in semantics."""

    sections = section_map(content)
    section_hits = sum(1 for section in SECTION_NAMES if section in sections)
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
        precision = (
            min(len(matched), reported_issue_bullets) / reported_issue_bullets
            if reported_issue_bullets
            else 0.0
        )
    else:
        precision = 1.0 if reported_blockers <= 1 else 0.75

    fix_requirements = case.get("minimal_fix_requirements", [])
    fix_low = fix.lower()
    req_hits = sum(
        1 for requirement in fix_requirements if fix_requirement_hit(requirement, fix)
    )
    verification_hit = any(word in fix_low for word in VERIFY_WORDS)
    broad_penalty = (
        0.25 if any(word in fix_low for word in BROAD_REWRITE_WORDS) else 0.0
    )
    if fix_requirements:
        actionability = min(
            1.0,
            (req_hits / len(fix_requirements)) * 0.7
            + (0.3 if verification_hit else 0.0),
        )
        actionability = max(0.0, actionability - broad_penalty)
    else:
        actionability = 1.0 if fix.strip() else 0.0

    trap_hits = false_positive_hits(case, content)
    trap_penalty = false_positive_penalty(trap_hits)
    if known:
        quality = (
            0.25 * section_score
            + 0.35 * (recall or 0.0)
            + 0.20 * precision
            + 0.20 * actionability
        )
    else:
        quality = 0.55 * section_score + 0.45 * actionability
    quality = max(0.0, quality - trap_penalty)

    cost = 0.0
    model_duration = 0.0
    argoses: list[Any] = []
    for result in meta.get("results", []):
        cost += float(result.get("cost") or 0.0)
        model_duration += float(result.get("duration_sec") or 0.0)
        argoses.append(result.get("argos"))

    status = "pass" if exit_code == 0 else (
        "needs_human" if exit_code == 3 else "fail"
    )
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


def compare_expected(
    observed: dict[str, Any], expected: dict[str, Any]
) -> list[str]:
    failures: list[str] = []
    for key, value in expected.get("equals", {}).items():
        if observed.get(key) != value:
            failures.append(
                f"{key}: expected {value!r}, observed {observed.get(key)!r}"
            )
    for key, value in expected.get("min", {}).items():
        if observed.get(key, 0) < value:
            failures.append(
                f"{key}: expected >= {value!r}, observed {observed.get(key)!r}"
            )
    for key, value in expected.get("max", {}).items():
        if observed.get(key, 0) > value:
            failures.append(
                f"{key}: expected <= {value!r}, observed {observed.get(key)!r}"
            )
    return failures


def score_scorer_case(case: dict[str, Any]) -> dict[str, Any]:
    content = (ROOT / case["path"]).read_text(encoding="utf-8")
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


def summarize(values: Sequence[float | int | None]) -> dict[str, float | int | None]:
    usable = [float(value) for value in values if value is not None]
    if not usable:
        return {
            "count": 0,
            "total": 0.0,
            "mean": None,
            "median": None,
            "p50": None,
            "p95": None,
            "min": None,
            "max": None,
            "stdev": None,
        }
    ordered = sorted(usable)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    stdev = statistics.pstdev(ordered) if len(ordered) > 1 else 0.0
    median = statistics.median(ordered)
    return {
        "count": len(ordered),
        "total": round(sum(ordered), 6),
        "mean": round(statistics.mean(ordered), 6),
        "median": round(median, 6),
        "p50": round(median, 6),
        "p95": round(p95, 6),
        "min": round(ordered[0], 6),
        "max": round(ordered[-1], 6),
        "stdev": round(stdev, 6),
    }


def mean_score(rows: Sequence[dict[str, Any]], key: str) -> float:
    values = [
        float(row[key])
        for row in rows
        if row.get(key) is not None
    ]
    return round(statistics.mean(values), 6) if values else 0.0


def normalize_case_inputs(case: dict[str, Any]) -> list[tuple[str, str]]:
    """Return explicit, deterministic context inputs for v1 and v2 cases."""

    inputs: list[tuple[str, str]] = []
    input_spec = case.get("inputs") if isinstance(case.get("inputs"), dict) else {}
    file_values: list[str] = []
    directory_values: list[str] = []
    if case.get("path"):
        file_values.append(str(case["path"]))
    file_values.extend(str(value) for value in case.get("paths", []))
    file_values.extend(str(value) for value in input_spec.get("files", []))
    if case.get("dir"):
        directory_values.append(str(case["dir"]))
    directory_values.extend(str(value) for value in case.get("dirs", []))
    directory_values.extend(str(value) for value in input_spec.get("directories", []))
    for value in file_values:
        inputs.append(("file", str((ROOT / value).resolve())))
    for value in directory_values:
        inputs.append(("dir", str((ROOT / value).resolve())))
    return inputs


def build_common_context_args(case: dict[str, Any]) -> list[str]:
    command: list[str] = []
    for input_kind, value in normalize_case_inputs(case):
        command.extend(["--file" if input_kind == "file" else "--dir", value])
    input_spec = case.get("inputs") if isinstance(case.get("inputs"), dict) else {}
    for pattern in [*case.get("include", []), *input_spec.get("include", [])]:
        command.extend(["--include", str(pattern)])
    for pattern in [*case.get("exclude", []), *input_spec.get("exclude", [])]:
        command.extend(["--exclude", str(pattern)])
    limits = input_spec.get("limits") if isinstance(input_spec.get("limits"), dict) else {}
    if limits.get("max_files") is not None:
        command.extend(["--max-files", str(limits["max_files"])])
    if limits.get("max_file_chars") is not None:
        command.extend(["--max-file-chars", str(limits["max_file_chars"])])
    if limits.get("max_total_chars") is not None:
        command.extend(["--max-total-chars", str(limits["max_total_chars"])])
    return command


def referenced_case_paths(case: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for input_kind, value in normalize_case_inputs(case):
        path = Path(value)
        if input_kind == "file":
            paths.append(path)
            continue
        if path.is_dir():
            paths.extend(
                candidate
                for candidate in sorted(path.rglob("*"), key=lambda item: item.as_posix())
                if candidate.is_file()
            )
    return paths


def case_content_hash(case: dict[str, Any]) -> str:
    inputs = [
        {
            "path": path.relative_to(ROOT).as_posix()
            if path.is_relative_to(ROOT)
            else str(path),
            "sha256": file_sha256(path),
        }
        for path in referenced_case_paths(case)
    ]
    payload = {
        "case": case,
        "inputs": inputs,
    }
    return sha256_text(canonical_json(payload))


def corpus_hash(manifest: dict[str, Any]) -> str:
    cases = {
        str(case["case_id"]): case_content_hash(case)
        for case in manifest.get("cases", [])
    }
    replays = {}
    replay_entries = list(manifest.get("replays") or [])
    if not replay_entries:
        replay_entries = [
            item
            for item in manifest.get("launches", [])
            if normalize_launch(str(item.get("surface") or "replay")) == "replay"
        ]
    for replay in replay_entries:
        path = ROOT / str(replay["response_path"])
        replay_id = replay.get("replay_id") or replay.get("launch_id")
        replays[str(replay_id)] = file_sha256(path)
    return sha256_text(canonical_json({"cases": cases, "replays": replays}))


def scorer_contract_hash() -> str:
    contract = {
        "version": SCORER_VERSION,
        "weights": {
            "coverage": 0.45,
            "precision": 0.20,
            "actionability": 0.20,
            "structure": 0.15,
        },
        "penalties": {
            "forbidden": 0.20,
            "label_leak": 0.20,
            "clean_hallucination": 0.25,
        },
        "critical_gate": True,
        "clean_gate": True,
        "concept_match": "all_terms_and_one_any_term",
    }
    return sha256_text(canonical_json(contract))


def prompt_contract_hash(manifest: dict[str, Any]) -> str:
    prompts = {
        str(case["case_id"]): {
            "prompt": case.get("prompt", ""),
            "turns": case.get("turns", []),
            "mode": case.get("mode"),
        }
        for case in manifest.get("cases", [])
    }
    return sha256_text(
        canonical_json(
            {
                "version": PROMPT_PROTOCOL_VERSION,
                "prompts": prompts,
            }
        )
    )


def benchmark_contract(manifest: dict[str, Any]) -> dict[str, str]:
    manifest_hash = sha256_text(canonical_json(manifest))
    hashes = {
        "manifest_sha256": manifest_hash,
        "corpus_sha256": corpus_hash(manifest),
        "prompt_contract_sha256": prompt_contract_hash(manifest),
        "scorer_contract_sha256": scorer_contract_hash(),
        "measurement_protocol_version": MEASUREMENT_PROTOCOL_VERSION,
        "isolated_assignment_sha256": sha256_text(
            canonical_json(
                {
                    "version": ISOLATED_ASSIGNMENT_VERSION,
                    "assignment": ISOLATED_ASSIGNMENT,
                }
            )
        ),
    }
    hashes["contract_sha256"] = sha256_text(canonical_json(hashes))
    return hashes


def load_case_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(case["case_id"]): case
        for case in manifest.get("cases", [])
    }


def _ensure_string_list(value: Any, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{label} must be a list of strings")
        return []
    return list(value)


def validate_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    schema_version = manifest.get("schema_version")
    if schema_version != RESULT_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {RESULT_SCHEMA_VERSION}, "
            f"observed {schema_version!r}"
        )
    if not isinstance(manifest.get("version"), str):
        errors.append("version must be a string")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty list")
        cases = []
    replays = manifest.get("replays")
    if not isinstance(replays, list):
        replays = []
    if not replays:
        replays = [
            item
            for item in manifest.get("launches", [])
            if isinstance(item, dict)
            and normalize_launch(str(item.get("surface") or "replay")) == "replay"
        ]
    if not replays:
        errors.append("replays must be a non-empty list")
    launches = manifest.get("launches")
    if not isinstance(launches, list) or not launches:
        errors.append("launches must be a non-empty list")
        launches = []
    case_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"cases[{index}] must be an object")
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"cases[{index}].case_id must be a non-empty string")
            continue
        if case_id in case_ids:
            errors.append(f"duplicate case_id: {case_id}")
        case_ids.add(case_id)
        profiles = _ensure_string_list(
            case.get("profiles", []), f"{case_id}.profiles", errors
        )
        for profile in profiles:
            if profile not in PROFILE_DEFAULTS:
                errors.append(f"{case_id}: unknown profile {profile!r}")
        mode = case.get("mode")
        if not isinstance(mode, str) or not mode:
            errors.append(f"{case_id}.mode must be a non-empty string")
        paths = referenced_case_paths(case)
        if not paths:
            errors.append(f"{case_id}: no readable input files")
        for path in paths:
            if not path.is_file():
                errors.append(f"{case_id}: missing input {path}")
        expectations = case.get("expectations")
        if not isinstance(expectations, dict):
            errors.append(f"{case_id}.expectations must be an object")
        else:
            required = expectations.get("required", [])
            if not isinstance(required, list):
                errors.append(f"{case_id}.expectations.required must be a list")
            hidden_ids = {
                str(item.get("id"))
                for item in required
                if isinstance(item, dict) and item.get("id")
            }
            visible_prompt = "\n".join(
                [
                    str(case.get("prompt") or ""),
                    *[
                        str(turn.get("prompt") if isinstance(turn, dict) else turn)
                        for turn in case.get("turns", [])
                    ],
                ]
            )
            leaked = sorted(
                concept_id for concept_id in hidden_ids if concept_id in visible_prompt
            )
            if leaked:
                errors.append(f"{case_id}: hidden ids leaked in prompts: {leaked}")

    replay_ids: set[str] = set()
    replay_count = 0
    for index, replay in enumerate(replays):
        if not isinstance(replay, dict):
            errors.append(f"replays[{index}] must be an object")
            continue
        replay_id = replay.get("replay_id")
        if not isinstance(replay_id, str) or not replay_id:
            errors.append(f"replays[{index}].replay_id must be a non-empty string")
            continue
        if replay_id in replay_ids:
            errors.append(f"duplicate replay_id: {replay_id}")
        replay_ids.add(replay_id)
        replay_count += 1
        case_id = replay.get("case_id")
        if case_id not in case_ids:
            errors.append(f"{replay_id}: unknown case_id {case_id!r}")
        profiles = _ensure_string_list(
            replay.get("profiles", []), f"{replay_id}.profiles", errors
        )
        for profile in profiles:
            if profile not in PROFILE_DEFAULTS:
                errors.append(f"{replay_id}: unknown profile {profile!r}")
        response_path = ROOT / str(replay.get("response_path") or "")
        if not response_path.is_file():
            errors.append(f"{replay_id}: missing response {response_path}")
        if not isinstance(replay.get("expected"), dict):
            errors.append(f"{replay_id}.expected must be an object")

    coverage: set[str] = set()
    launch_ids: set[str] = set()
    for index, launch in enumerate(launches):
        if not isinstance(launch, dict):
            errors.append(f"launches[{index}] must be an object")
            continue
        launch_id = launch.get("launch_id")
        if not isinstance(launch_id, str) or not launch_id:
            errors.append(f"launches[{index}].launch_id must be a non-empty string")
            continue
        if launch_id in launch_ids:
            errors.append(f"duplicate launch_id: {launch_id}")
        launch_ids.add(launch_id)
        surface = launch.get("surface")
        if not isinstance(surface, str) or not surface:
            errors.append(f"{launch_id}.surface must be a non-empty string")
            continue
        try:
            normalized_surface = normalize_launch(surface)
        except BenchmarkConfigError:
            errors.append(f"{launch_id}: unsupported surface {surface!r}")
            continue
        profiles = _ensure_string_list(
            launch.get("profiles", []), f"{launch_id}.profiles", errors
        )
        for profile in profiles:
            if profile not in PROFILE_DEFAULTS:
                errors.append(f"{launch_id}: unknown profile {profile!r}")
        case_id = launch.get("case_id")
        if normalized_surface == "benchmark":
            continue
        if normalized_surface == "replay":
            if case_id not in case_ids:
                errors.append(f"{launch_id}: unknown case_id {case_id!r}")
            response_path = ROOT / str(launch.get("response_path") or "")
            if not response_path.is_file():
                errors.append(f"{launch_id}: missing response {response_path}")
            continue
        coverage.add(normalized_surface)
        if case_id not in case_ids:
            errors.append(f"{launch_id}: unknown case_id {case_id!r}")
            continue
        track = launch.get("track")
        try:
            normalized_track = normalize_track(str(track))
        except BenchmarkConfigError:
            errors.append(f"{launch_id}: unsupported track {track!r}")
            continue
        if normalized_surface == "harness":
            if normalized_track != "harness":
                errors.append(
                    f"{launch_id}: harness launch must use the harness track"
                )
        elif normalized_surface == "replay":
            if normalized_track not in {"replay", "isolated", "production"}:
                errors.append(
                    f"{launch_id}: replay launch track must be replay, "
                    "isolated or production"
                )
        elif normalized_track not in LIVE_TRACKS:
            errors.append(
                f"{launch_id}: live launch track must be isolated or production"
            )
        argoses = launch.get("argoses")
        if argoses is None:
            argoses = launch.get("argos")
        if argoses is not None:
            _ensure_string_list(argoses, f"{launch_id}.argoses", errors)
        case = next(
            (item for item in cases if item.get("case_id") == case_id),
            {},
        )
        if normalized_surface == "session" and len(case.get("turns", [])) < 2:
            errors.append(f"{launch_id}: session case requires at least two turns")
        if normalized_surface == "debate":
            debate = case.get("debate")
            rounds = debate.get("rounds") if isinstance(debate, dict) else None
            if not isinstance(rounds, int) or rounds < 1:
                errors.append(f"{launch_id}: debate case requires positive rounds")
    required_coverage = {"oneshot", "session", "council", "debate"}
    missing_coverage = sorted(required_coverage - coverage)
    if missing_coverage:
        errors.append(f"missing live launch coverage: {missing_coverage}")
    if errors:
        location = f" ({manifest_path})" if manifest_path else ""
        raise BenchmarkConfigError(
            "Invalid benchmark manifest"
            + location
            + ":\n- "
            + "\n- ".join(errors)
        )
    return {
        "case_count": len(cases),
        "replay_count": replay_count,
        "launch_coverage": sorted(coverage),
    }


def _concept_terms(concept: dict[str, Any]) -> tuple[list[str], list[str]]:
    all_terms = [str(term).lower() for term in concept.get("all", [])]
    any_terms = [str(term).lower() for term in concept.get("any", [])]
    if not all_terms and not any_terms and concept.get("terms"):
        any_terms = [str(term).lower() for term in concept.get("terms", [])]
    return all_terms, any_terms


def concept_hit(concept: dict[str, Any], text: str) -> bool:
    low = text.lower()
    all_terms, any_terms = _concept_terms(concept)
    if not all(term in low for term in all_terms):
        return False
    return not any_terms or any(term in low for term in any_terms)


def _concept_scope_text(
    concept: dict[str, Any],
    *,
    content: str,
    sections: dict[str, str],
) -> str:
    scope = str(concept.get("scope") or "full")
    if scope == "issues":
        return "\n".join(
            [sections.get("Blockers", ""), sections.get("Important issues", "")]
        )
    if scope == "blockers":
        return sections.get("Blockers", "")
    if scope == "important":
        return sections.get("Important issues", "")
    if scope == "fix":
        return sections.get("Minimal fix plan", "")
    return content


def score_output(case: dict[str, Any], content: str) -> dict[str, Any]:
    expectations = case.get("expectations", {})
    required = [
        item for item in expectations.get("required", []) if isinstance(item, dict)
    ]
    forbidden = [
        item for item in expectations.get("forbidden", []) if isinstance(item, dict)
    ]
    actionability_items = [
        item
        for item in expectations.get("actionability", [])
        if isinstance(item, dict)
    ]
    sections = section_map(content)

    matched_required: list[str] = []
    missed_required: list[str] = []
    matched_weight = 0.0
    total_weight = 0.0
    critical_misses: list[str] = []
    severity_expected = 0
    severity_hits = 0
    for concept in required:
        concept_id = str(concept.get("id") or "unnamed")
        weight = float(concept.get("weight", 1.0))
        total_weight += weight
        scoped_text = _concept_scope_text(
            concept, content=content, sections=sections
        )
        hit = concept_hit(concept, scoped_text)
        if hit:
            matched_required.append(concept_id)
            matched_weight += weight
        else:
            missed_required.append(concept_id)
            if concept.get("critical"):
                critical_misses.append(concept_id)
        severity = concept.get("severity")
        if severity in {"blocker", "important"}:
            severity_expected += 1
            severity_text = (
                sections.get("Blockers", "")
                if severity == "blocker"
                else sections.get("Important issues", "")
            )
            if concept_hit(concept, severity_text):
                severity_hits += 1

    clean_case = bool(expectations.get("clean"))
    reported_issue_count = bullet_count(
        sections.get("Blockers", "")
    ) + bullet_count(sections.get("Important issues", ""))
    max_issue_count = int(expectations.get("max_issue_count", 0 if clean_case else 999))
    issue_precision = bool(
        expectations.get("issue_precision", case.get("mode") == "review")
    )
    if clean_case:
        coverage = 1.0
        precision = 1.0 if reported_issue_count <= max_issue_count else 0.0
    elif not issue_precision:
        coverage = matched_weight / total_weight if total_weight else 1.0
        precision = 1.0
    else:
        coverage = matched_weight / total_weight if total_weight else 1.0
        precision = (
            min(len(matched_required), reported_issue_count)
            / reported_issue_count
            if reported_issue_count
            else (1.0 if not required else 0.0)
        )

    required_sections = [
        str(value) for value in expectations.get("required_sections", [])
    ]
    structure = (
        sum(1 for section in required_sections if section in sections)
        / len(required_sections)
        if required_sections
        else 1.0
    )
    actionability_hits = sum(
        1
        for item in actionability_items
        if concept_hit(
            item,
            _concept_scope_text(item, content=content, sections=sections),
        )
    )
    actionability = (
        actionability_hits / len(actionability_items)
        if actionability_items
        else 1.0
    )

    forbidden_hits = [
        str(item.get("id") or "forbidden")
        for item in forbidden
        if concept_hit(
            item,
            _concept_scope_text(item, content=content, sections=sections),
        )
    ]
    critical_forbidden_hits = [
        str(item.get("id") or "forbidden")
        for item in forbidden
        if item.get("critical")
        and concept_hit(
            item,
            _concept_scope_text(item, content=content, sections=sections),
        )
    ]
    hidden_label_hits = sorted(set(HIDDEN_LABEL_RE.findall(content)))
    clean_hallucination_count = max(0, reported_issue_count - max_issue_count)
    penalty = min(
        0.60,
        0.20 * len(forbidden_hits)
        + 0.20 * len(hidden_label_hits)
        + (0.25 if clean_hallucination_count else 0.0),
    )
    raw_score = (
        0.45 * coverage
        + 0.20 * precision
        + 0.20 * actionability
        + 0.15 * structure
    )
    score = max(0.0, min(1.0, raw_score - penalty))
    threshold = float(expectations.get("acceptance_threshold", 0.70))
    gate_failures: list[str] = []
    if critical_misses:
        gate_failures.append("critical_required_missed")
    if critical_forbidden_hits:
        gate_failures.append("critical_forbidden_hit")
    if clean_case and clean_hallucination_count:
        gate_failures.append("clean_case_hallucination")
    if score < threshold:
        gate_failures.append("quality_below_threshold")
    if expectations.get("require_all_sections") and structure < 1.0:
        gate_failures.append("required_section_missing")
    accepted = not gate_failures
    return {
        "score": round(score, 6),
        "accepted": accepted,
        "acceptance_threshold": threshold,
        "gate_failures": gate_failures,
        "coverage": round(coverage, 6),
        "precision": round(precision, 6),
        "actionability": round(actionability, 6),
        "structure": round(structure, 6),
        "severity_accuracy": (
            round(severity_hits / severity_expected, 6)
            if severity_expected
            else None
        ),
        "matched_concepts": matched_required,
        "missed_concepts": missed_required,
        "critical_misses": critical_misses,
        "forbidden_hits": forbidden_hits,
        "critical_forbidden_hits": critical_forbidden_hits,
        "hidden_label_hits": hidden_label_hits,
        "reported_issue_count": reported_issue_count,
        "clean_hallucination_count": clean_hallucination_count,
        "accepted_finding_count": len(matched_required),
        "penalty": round(penalty, 6),
    }


def calibration_failures(
    quality: dict[str, Any], expected: dict[str, Any]
) -> list[str]:
    failures: list[str] = []
    if "accepted" in expected and quality.get("accepted") is not expected["accepted"]:
        failures.append(
            f"accepted expected {expected['accepted']!r}, "
            f"observed {quality.get('accepted')!r}"
        )
    if "min_score" in expected and float(quality.get("score", 0.0)) < float(
        expected["min_score"]
    ):
        failures.append(
            f"score expected >= {expected['min_score']}, "
            f"observed {quality.get('score')}"
        )
    if "max_score" in expected and float(quality.get("score", 0.0)) > float(
        expected["max_score"]
    ):
        failures.append(
            f"score expected <= {expected['max_score']}, "
            f"observed {quality.get('score')}"
        )
    required_gate_failures = set(expected.get("gate_failures", []))
    observed_gate_failures = set(quality.get("gate_failures", []))
    missing = sorted(required_gate_failures - observed_gate_failures)
    if missing:
        failures.append(f"missing expected gate failures: {missing}")
    if "gate_failures" in expected:
        unexpected = sorted(observed_gate_failures - required_gate_failures)
        if unexpected:
            failures.append(f"unexpected gate failures: {unexpected}")
    required_matches = set(expected.get("matched_concepts", []))
    observed_matches = set(quality.get("matched_concepts", []))
    if not required_matches.issubset(observed_matches):
        failures.append(
            "missing expected matched concepts: "
            f"{sorted(required_matches - observed_matches)}"
        )
    return failures


@dataclass(frozen=True)
class RunSpec:
    spec_id: str
    track: str
    launch: str
    case_id: str | None = None
    argoses: tuple[str, ...] = ()
    repetition: int = 1
    replay_id: str | None = None
    requires_live: bool = False
    enabled: bool = True
    estimated_calls: int = 0
    estimated_cost_usd: float = 0.0
    cohort_key: str = ""
    semantic_fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["argoses"] = list(self.argoses)
        return payload


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    timed_out: bool = False
    launch_error: str | None = None


CommandRunner = Callable[..., CommandResult]


def normalize_track(value: str) -> str:
    aliases = {
        "isolated-model": "isolated",
        "production-route": "production",
    }
    normalized = aliases.get(value, value)
    if normalized not in TRACK_NAMES:
        raise BenchmarkConfigError(f"Unknown track: {value}")
    return normalized


def normalize_launch(value: str) -> str:
    aliases = {
        "benchmark": "harness",
        "run": "oneshot",
        "multi": "session",
        "start": "council",
    }
    normalized = aliases.get(value, value)
    if normalized not in LAUNCH_NAMES:
        raise BenchmarkConfigError(f"Unknown launch: {value}")
    return normalized


def _selected_values(
    explicit: Sequence[str] | None,
    defaults: Sequence[str],
    normalizer: Callable[[str], str],
) -> list[str]:
    values = explicit if explicit else defaults
    normalized: list[str] = []
    for value in values:
        item = normalizer(str(value))
        if item not in normalized:
            normalized.append(item)
    return normalized


def _case_profiles(case: dict[str, Any]) -> set[str]:
    profiles = case.get("profiles")
    return set(profiles) if isinstance(profiles, list) else set(PROFILE_DEFAULTS)


def _replay_profiles(replay: dict[str, Any]) -> set[str]:
    profiles = replay.get("profiles")
    return set(profiles) if isinstance(profiles, list) else set(PROFILE_DEFAULTS)


def estimated_calls_for(
    *,
    launch: str,
    case: dict[str, Any],
    track: str,
    argoses: Sequence[str],
) -> int:
    turns = max(1, len(case.get("turns", [])))
    participant_count = len(argoses)
    if not participant_count:
        participant_count = int(case.get("estimated_argoses", 3))
    if launch == "oneshot":
        return participant_count
    if launch in {"session", "council"}:
        return participant_count * turns
    if launch == "debate":
        rounds = int(case.get("debate", {}).get("rounds", 2))
        return participant_count * rounds + 1
    return 0


def _cohort_key(
    *,
    track: str,
    launch: str,
    case: dict[str, Any],
    argoses: Sequence[str],
    manifest_contract: dict[str, str],
) -> str:
    payload: dict[str, Any] = {
        "track": track,
        "launch": launch,
        "case_id": case["case_id"],
        "case_sha256": case_content_hash(case),
        "prompt_contract_sha256": manifest_contract["prompt_contract_sha256"],
        "scorer_contract_sha256": manifest_contract["scorer_contract_sha256"],
    }
    if track == "isolated":
        payload["assignment_sha256"] = manifest_contract[
            "isolated_assignment_sha256"
        ]
        payload["candidate_argoses"] = list(argoses)
    else:
        payload["route_argoses"] = list(argoses) or ["mode-default"]
    return sha256_text(canonical_json(payload))[:24]


def build_run_plan(
    manifest: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    defaults = PROFILE_DEFAULTS[args.profile]
    selected_tracks = _selected_values(
        getattr(args, "tracks", None), defaults["tracks"], normalize_track
    )
    selected_launches = _selected_values(
        getattr(args, "launches", None), defaults["launches"], normalize_launch
    )
    repetitions = int(
        args.repetitions
        if getattr(args, "repetitions", None) is not None
        else defaults["repetitions"]
    )
    if repetitions < 1 or repetitions > 20:
        raise BenchmarkConfigError("--repetitions must be between 1 and 20")
    selected_case_ids = set(getattr(args, "cases", None) or [])
    case_index = load_case_by_id(manifest)
    unknown_cases = sorted(selected_case_ids - set(case_index))
    if unknown_cases:
        raise BenchmarkConfigError(f"Unknown case ids: {unknown_cases}")
    argoses = list(getattr(args, "argoses", None) or defaults["argoses"])
    contract = benchmark_contract(manifest)
    cost_per_call = float(defaults["estimated_cost_per_call_usd"])
    specs: list[RunSpec] = []

    if "harness" in selected_tracks and "harness" in selected_launches:
        specs.append(
            RunSpec(
                spec_id="harness:internal",
                track="harness",
                launch="harness",
                cohort_key="harness:internal",
                semantic_fingerprint=sha256_text(
                    canonical_json(
                        {
                            "contract": contract["contract_sha256"],
                            "launch": "harness",
                        }
                    )
                ),
            )
        )

    if "replay" in selected_tracks and "replay" in selected_launches:
        for replay in manifest.get("replays", []):
            if not isinstance(replay, dict):
                continue
            replay_id = str(replay.get("replay_id") or "")
            case_id = str(replay.get("case_id") or "")
            if not replay_id or args.profile not in _replay_profiles(replay):
                continue
            if selected_case_ids and case_id not in selected_case_ids:
                continue
            case = case_index[case_id]
            cohort = _cohort_key(
                track="replay",
                launch="replay",
                case=case,
                argoses=[],
                manifest_contract=contract,
            )
            specs.append(
                RunSpec(
                    spec_id=f"replay:{replay_id}",
                    track="replay",
                    launch="replay",
                    case_id=case_id,
                    replay_id=replay_id,
                    cohort_key=cohort,
                    semantic_fingerprint=sha256_text(
                        canonical_json(
                            {
                                "contract": contract["contract_sha256"],
                                "case": case_content_hash(case),
                                "replay": file_sha256(
                                    ROOT / str(replay["response_path"])
                                ),
                            }
                        )
                    ),
                )
            )

    for launch in manifest.get("launches", []):
        if not isinstance(launch, dict):
            continue
        launch_id = str(launch.get("launch_id") or "")
        if not launch_id:
            continue
        if args.profile not in _replay_profiles(launch):
            continue
        surface = normalize_launch(str(launch.get("surface") or "oneshot"))
        track = normalize_track(str(launch.get("track") or "isolated"))
        case_id = str(launch.get("case_id") or "")
        if selected_case_ids and case_id not in selected_case_ids:
            continue
        if track not in selected_tracks or surface not in selected_launches:
            continue
        case = case_index[case_id]
        configured_group = tuple(
            str(value) for value in (launch.get("argos") or launch.get("argoses") or [])
        )
        if track == "isolated":
            candidates = (
                list(getattr(args, "argoses", None) or [])
                or list(configured_group)
                or list(defaults["argoses"])
            )
            route_groups = [(candidate,) for candidate in candidates]
        else:
            route_groups = [configured_group]
        for argos_group in route_groups:
            calls = estimated_calls_for(
                launch=surface,
                case=case,
                track=track,
                argoses=argos_group,
            )
            cohort = _cohort_key(
                track=track,
                launch=surface,
                case=case,
                argoses=argos_group,
                manifest_contract=contract,
            )
            for repetition in range(1, repetitions + 1):
                route_name = "+".join(argos_group) or "mode-default"
                spec_id = (
                    f"{track}:{surface}:{case_id}:{route_name}:"
                    f"r{repetition}"
                )
                fingerprint = sha256_text(
                    canonical_json(
                        {
                            "contract": contract["contract_sha256"],
                            "cohort": cohort,
                            "route": list(argos_group) or ["mode-default"],
                            "repetition": repetition,
                            "launch_id": launch_id,
                        }
                    )
                )
                specs.append(
                    RunSpec(
                        spec_id=spec_id,
                        track=track,
                        launch=surface,
                        case_id=case_id,
                        argoses=argos_group,
                        repetition=repetition,
                        requires_live=True,
                        enabled=bool(args.live),
                        estimated_calls=calls,
                        estimated_cost_usd=round(calls * cost_per_call, 6),
                        cohort_key=cohort,
                        semantic_fingerprint=fingerprint,
                        metadata={
                            "launch_id": launch_id,
                            **(
                                {
                                    "turns": list(launch.get("turns") or [])
                                }
                                if surface == "session"
                                else {}
                            ),
                            **(
                                {
                                    "debate": {
                                        key: launch.get(key)
                                        for key in (
                                            "rounds",
                                            "share_chars",
                                            "total_share_chars",
                                            "moderator",
                                        )
                                        if launch.get(key) is not None
                                    }
                                }
                                if surface == "debate"
                                else {}
                            ),
                        },
                    )
                )

    max_calls = int(
        args.max_calls
        if getattr(args, "max_calls", None) is not None
        else defaults["max_calls"]
    )
    max_wall_seconds = float(
        args.max_wall_seconds
        if getattr(args, "max_wall_seconds", None) is not None
        else defaults["max_wall_seconds"]
    )
    max_cost_usd = float(
        args.max_cost_usd
        if getattr(args, "max_cost_usd", None) is not None
        else defaults["max_cost_usd"]
    )
    if max_calls < 0 or max_wall_seconds <= 0 or max_cost_usd < 0:
        raise BenchmarkConfigError("budgets must be non-negative and wall time positive")
    enabled_live_specs = [spec for spec in specs if spec.requires_live and spec.enabled]
    estimated_live_calls = sum(spec.estimated_calls for spec in enabled_live_specs)
    estimated_live_cost = round(
        sum(spec.estimated_cost_usd for spec in enabled_live_specs), 6
    )
    if estimated_live_calls > max_calls:
        raise BenchmarkConfigError(
            f"planned live calls {estimated_live_calls} exceed --max-calls={max_calls}"
        )
    if estimated_live_cost > max_cost_usd:
        raise BenchmarkConfigError(
            "estimated live cost "
            f"${estimated_live_cost:.6f} exceeds --max-cost-usd=${max_cost_usd:.6f}"
        )
    if args.live and not enabled_live_specs:
        raise BenchmarkConfigError(
            "--live was provided but the selected matrix has no live specs"
        )
    selection = {
        "tracks": selected_tracks,
        "launches": selected_launches,
        "cases": sorted(selected_case_ids),
        "argoses": argoses,
        "repetitions": repetitions,
        "harness_iterations": int(args.harness_iterations),
        "command_timeout_seconds": float(args.timeout),
    }
    budgets = {
        "max_calls": max_calls,
        "max_wall_seconds": max_wall_seconds,
        "max_cost_usd": max_cost_usd,
        "estimated_live_calls": estimated_live_calls,
        "estimated_live_cost_usd": estimated_live_cost,
        "cost_estimate_is_upper_bound": False,
        "cost_estimate_note": (
            "Admission-control estimate only. Runtime rechecks reported cost "
            "between launches and between session turns. An atomic one-shot or "
            "debate command can still exceed the estimate before reporting "
            "telemetry; missing telemetry stops later live work."
        ),
    }
    spec_payloads = [spec.to_dict() for spec in specs]
    comparison_selection = {
        "profile": args.profile,
        "live": bool(args.live),
        "selection": selection,
        "budgets": budgets,
        "enabled_specs": [
            {
                "spec_id": spec["spec_id"],
                "semantic_fingerprint": spec["semantic_fingerprint"],
                "cohort_key": spec["cohort_key"],
                "repetition": spec["repetition"],
                "estimated_calls": spec["estimated_calls"],
            }
            for spec in spec_payloads
            if spec["enabled"]
        ],
    }
    plan = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "benchmark_version": manifest["version"],
        "profile": args.profile,
        "live": bool(args.live),
        "selection": selection,
        "contract": contract,
        "budgets": budgets,
        "specs": spec_payloads,
        "spec_count": len(specs),
        "enabled_spec_count": sum(1 for spec in specs if spec.enabled),
        "disabled_live_spec_count": sum(
            1 for spec in specs if spec.requires_live and not spec.enabled
        ),
    }
    plan["comparison_selection_sha256"] = sha256_text(
        canonical_json(comparison_selection)
    )
    return plan


def prepare_env(result_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["ARGOS_CONFIG_DIR"] = str((result_dir / "config").resolve())
    env["ARGOS_ARTIFACT_ROOT"] = str((result_dir / "argos-artifacts").resolve())
    env["ARGOS_LOCK_ROOT"] = str((result_dir / "locks").resolve())
    env["PYTHONUTF8"] = "1"
    return env


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
            if completed.returncode == 0 or process.poll() is not None:
                return
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except OSError:
            pass
    try:
        process.kill()
    except OSError:
        pass


def run_command(
    command: list[str],
    *,
    cwd: Path = ROOT,
    timeout: float = 900,
    env: dict[str, str] | None = None,
) -> CommandResult:
    started = time.perf_counter()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **(
                {
                    "creationflags": getattr(
                        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                    )
                }
                if os.name == "nt"
                else {"start_new_session": True}
            ),
        )
    except OSError as exc:
        return CommandResult(
            command=list(command),
            exit_code=127,
            stdout="",
            stderr=str(exc),
            duration_sec=round(time.perf_counter() - started, 6),
            launch_error=str(exc),
        )
    try:
        stdout, stderr = process.communicate(timeout=max(0.001, timeout))
        return CommandResult(
            command=list(command),
            exit_code=int(process.returncode or 0),
            stdout=stdout or "",
            stderr=stderr or "",
            duration_sec=round(time.perf_counter() - started, 6),
        )
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        stdout, stderr = process.communicate()
        return CommandResult(
            command=list(command),
            exit_code=124,
            stdout=stdout or "",
            stderr=stderr or "",
            duration_sec=round(time.perf_counter() - started, 6),
            timed_out=True,
        )


def run_cmd(
    command: list[str],
    *,
    cwd: Path = ROOT,
    timeout: int = 900,
) -> tuple[int, str, str, float]:
    """Compatibility wrapper for the original tuple-returning helper."""

    result = run_command(command, cwd=cwd, timeout=timeout)
    return (
        result.exit_code,
        result.stdout,
        result.stderr,
        result.duration_sec,
    )


def run_cmd_capture(
    command: list[str],
    *,
    cwd: Path = ROOT,
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = run_command(command, cwd=cwd, timeout=timeout, env=env)
    return {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration": result.duration_sec,
        "timed_out": result.timed_out,
        "launch_error": result.launch_error,
    }


def _error_text(meta: dict[str, Any], stderr: str, stdout: str = "") -> str:
    values = [stderr, stdout]
    for result in meta.get("results", []):
        values.append(str(result.get("error") or ""))
        values.append(str(result.get("status") or ""))
    synthesis = meta.get("synthesis")
    if isinstance(synthesis, dict):
        values.append(str(synthesis.get("error") or ""))
        values.append(str(synthesis.get("status") or ""))
    values.append(str(meta.get("error") or ""))
    values.append(str(meta.get("status") or ""))
    return "\n".join(values)


def classify_launch(
    exit_code: int,
    meta: dict[str, Any],
    stderr: str,
    timed_out: bool,
    surface: str,
    *,
    stdout: str = "",
    launch_error: str | None = None,
    persistent: bool = False,
) -> str:
    if normalize_launch(surface) == "replay":
        return "replay_ok"
    if launch_error:
        return "launcher_failed"
    text = _error_text(meta, stderr, stdout)
    low = text.lower()
    if exit_code == 3 or "needs_human" in low or re.search(
        r"\b(?:login|sign in|authentication required|unauthorized)\b", low
    ):
        return "needs_human"
    if timed_out:
        return "outcome_unknown" if persistent else "timeout"
    if exit_code == 0:
        if not meta:
            return "parse_error"
        result_statuses = [
            str(result.get("status") or "") for result in meta.get("results", [])
        ]
        if any(status == "needs_human" for status in result_statuses):
            return "needs_human"
        if any(status == "error" for status in result_statuses):
            return "provider_error"
        return "ok"
    if "eexist" in low and "opencode" in low:
        return "provider_bootstrap_failed"
    if any(
        term in low
        for term in (
            "connectionrefused",
            "connection refused",
            "provider unavailable",
            "no such host",
            "name or service not known",
            "could not resolve host",
            "network is unreachable",
            "service unavailable",
        )
    ):
        return "provider_unavailable"
    if any(term in low for term in ("timed out", "timeout", "exit_code\": 124")):
        return "outcome_unknown" if persistent else "timeout"
    if exit_code in {126, 127} or any(
        term in low for term in ("not recognized", "no such file or directory")
    ):
        return "launcher_failed"
    if not meta and stdout.strip():
        return "parse_error"
    return "provider_error"


def _safe_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    return safe[:100] or "item"


def _materialize_prompt(
    result_dir: Path,
    spec_id: str,
    turn_number: int,
    prompt: str,
) -> Path:
    path = (
        result_dir
        / "prompts"
        / f"{_safe_component(spec_id)}-turn-{turn_number:02d}.md"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt.rstrip() + "\n", encoding="utf-8")
    return path


def _base_argos_command(config_path: Path | None = None) -> list[str]:
    command = [sys.executable, str(ARGOS_PY)]
    if config_path is not None:
        command.extend(["--config", str(config_path)])
    return command


def isolated_config_path(
    result_dir: Path,
    argoses: Sequence[str],
    modes: Iterable[str],
) -> Path:
    path = result_dir / "config" / "isolated.json"
    default_assignments = {
        argos: dict(ISOLATED_ASSIGNMENT) for argos in sorted(set(argoses))
    }
    mode_assignments = {
        mode: {
            argos: dict(ISOLATED_ASSIGNMENT)
            for argos in sorted(set(argoses))
        }
        for mode in sorted(set(modes))
    }
    payload = {
        "version": 1,
        "assignments": {
            "default": default_assignments,
            **mode_assignments,
        },
        "concurrency": {
            "global": 1,
            "opencode_total": 1,
            "opencode_go": 1,
            "claude": 1,
            "minimax": 1,
        },
    }
    write_json(path, payload)
    return path


def _config_for_spec(
    spec: RunSpec,
    *,
    result_dir: Path,
    args: argparse.Namespace,
    case: dict[str, Any],
) -> Path | None:
    if spec.track == "isolated":
        return isolated_config_path(
            result_dir,
            spec.argoses,
            [str(case["mode"])],
        )
    if getattr(args, "config", None):
        return Path(args.config).expanduser().resolve()
    return None


def _turn_prompts(case: dict[str, Any]) -> list[dict[str, Any]]:
    turns = case.get("turns")
    if isinstance(turns, list) and turns:
        normalized: list[dict[str, Any]] = []
        for value in turns:
            if isinstance(value, dict):
                normalized.append(
                    {
                        "prompt": str(value.get("prompt") or ""),
                        "inputs": value.get("inputs"),
                    }
                )
            else:
                normalized.append({"prompt": str(value), "inputs": None})
        return normalized
    return [{"prompt": str(case.get("prompt") or ""), "inputs": None}]


def _argos_flags(argoses: Sequence[str], *, single_ok: bool) -> list[str]:
    flags: list[str] = []
    for argos in argoses:
        flags.extend(["--argos", str(argos)])
    if single_ok and len(argoses) == 1:
        flags.append("--single-ok")
    return flags


def _case_context_args(
    case: dict[str, Any],
    turn: dict[str, Any] | None = None,
) -> list[str]:
    if turn and isinstance(turn.get("inputs"), dict):
        turn_case = {"inputs": turn["inputs"]}
        return build_common_context_args(turn_case)
    return build_common_context_args(case)


def build_launch_command(
    launch: dict[str, Any],
    case: dict[str, Any] | None,
    result_dir: Path,
    artifact_root: Path,
) -> tuple[list[str], dict[str, str]]:
    """Compatibility command builder used by legacy callers and tests."""

    surface = normalize_launch(str(launch.get("surface") or launch.get("launch") or "oneshot"))
    env = prepare_env(result_dir)
    if surface == "replay":
        return [], env
    command = _base_argos_command()
    if surface == "harness":
        command.extend(
            [
                "benchmark",
                "--iterations",
                str(launch.get("iterations", 1)),
                "--artifact-root",
                str(artifact_root),
                "--json",
            ]
        )
        return command, env
    if case is None:
        raise BenchmarkConfigError(f"{surface} requires a case")
    mode = str(launch.get("mode") or case.get("mode") or "review")
    argoses = tuple(
        str(value)
        for value in (launch.get("argos") or launch.get("argoses") or [])
    )
    if surface == "session" and str(launch.get("surface")) == "multi":
        command.extend(["multi", mode])
        for turn in launch.get("turns", []):
            path = ROOT / str(turn)
            command.extend(["--turn", path.read_text(encoding="utf-8")])
        command.extend(_argos_flags(argoses, single_ok=bool(launch.get("single_ok"))))
        command.extend(build_common_context_args(case))
        command.extend(["--artifact-root", str(artifact_root)])
        return command, env
    prompt = str(launch.get("prompt") or case.get("prompt") or "")
    prompt_path = _materialize_prompt(
        result_dir,
        str(launch.get("launch_id") or case["case_id"]),
        1,
        prompt,
    )
    command_name = {
        "oneshot": "run",
        "session": "start",
        "council": "start",
        "debate": "debate",
    }[surface]
    command.extend([command_name, mode, "--prompt-file", str(prompt_path)])
    command.extend(_argos_flags(argoses, single_ok=bool(launch.get("single_ok", True))))
    command.extend(build_common_context_args(case))
    if surface == "debate":
        command.extend(["--rounds", str(launch.get("rounds", 2))])
    command.extend(["--artifact-root", str(artifact_root), "--json"])
    return command, env


def _parse_meta(command_result: CommandResult) -> tuple[dict[str, Any], str | None]:
    try:
        meta = parse_json_stdout(command_result.stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not meta:
        return {}, "stdout did not contain a JSON object"
    return meta, None


def _meta_results(meta: dict[str, Any]) -> list[dict[str, Any]]:
    results = meta.get("results")
    return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []


def _content_from_meta(meta: dict[str, Any], launch: str) -> str:
    if launch == "debate":
        synthesis = meta.get("synthesis")
        if isinstance(synthesis, dict):
            return str(synthesis.get("content") or "")
    contents = [
        str(result.get("content") or "")
        for result in _meta_results(meta)
        if result.get("content")
    ]
    return "\n\n".join(contents)


def _telemetry_from_metas(
    metas: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    provider_duration = 0.0
    provider_duration_count = 0
    costs: list[float] = []
    token_payloads: list[Any] = []
    providers: set[str] = set()
    models: set[str] = set()
    assignments: set[str] = set()
    prompt_hashes: set[str] = set()
    result_sample_count = 0
    for meta in metas:
        result_items = _meta_results(meta)
        synthesis = meta.get("synthesis")
        if isinstance(synthesis, dict):
            result_items = [*result_items, synthesis]
        for result in result_items:
            result_sample_count += 1
            duration = result.get("duration_sec")
            if duration is not None:
                provider_duration += float(duration)
                provider_duration_count += 1
            if result.get("cost") is not None:
                costs.append(float(result["cost"]))
            if result.get("tokens") is not None:
                token_payloads.append(result["tokens"])
            if result.get("provider"):
                providers.add(str(result["provider"]))
            if result.get("model"):
                models.add(str(result["model"]))
            assignment = result.get("assignment")
            if isinstance(assignment, dict) and assignment.get("hash"):
                assignments.add(str(assignment["hash"]))
            prompt_manifest = result.get("prompt_manifest")
            if isinstance(prompt_manifest, dict) and prompt_manifest.get("final_hash"):
                prompt_hashes.add(str(prompt_manifest["final_hash"]))
    return {
        "provider_duration_sec": (
            round(provider_duration, 6) if provider_duration_count else None
        ),
        "cost_usd": round(sum(costs), 6) if costs else None,
        "cost_sample_count": len(costs),
        "result_sample_count": result_sample_count,
        "cost_telemetry_complete": (
            result_sample_count > 0 and len(costs) == result_sample_count
        ),
        "token_payloads": token_payloads,
        "providers": sorted(providers),
        "models": sorted(models),
        "assignment_hashes": sorted(assignments),
        "prompt_hashes": sorted(prompt_hashes),
    }


def _read_effective_config_hash(meta: dict[str, Any]) -> str | None:
    artifact_dir = meta.get("artifact_dir")
    if not artifact_dir:
        return None
    path = Path(str(artifact_dir)) / "effective_config.json"
    if not path.is_absolute():
        path = ROOT / path
    return file_sha256(path) if path.is_file() else None


def _base_result_row(spec: RunSpec) -> dict[str, Any]:
    return {
        "spec_id": spec.spec_id,
        "track": spec.track,
        "launch": spec.launch,
        "case_id": spec.case_id,
        "argoses": list(spec.argoses),
        "repetition": spec.repetition,
        "cohort_key": spec.cohort_key,
        "semantic_fingerprint": spec.semantic_fingerprint,
        "status": None,
        "reason": None,
        "quality": None,
        "wall_duration_sec": None,
        "provider_duration_sec": None,
        "cost_usd": None,
        "models": [],
        "providers": [],
        "artifact_dir": None,
        "commands": [],
    }


def execute_replay_spec(
    spec: RunSpec,
    *,
    manifest: dict[str, Any],
    case_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    replay_entries = list(manifest.get("replays") or [])
    if not replay_entries:
        replay_entries = [
            item
            for item in manifest.get("launches", [])
            if normalize_launch(str(item.get("surface") or "replay")) == "replay"
        ]
    replay = next(
        item
        for item in replay_entries
        if item.get("replay_id") == spec.replay_id
        or item.get("launch_id") == spec.replay_id
    )
    case = case_index[str(spec.case_id)]
    response_path = ROOT / str(replay["response_path"])
    content = response_path.read_text(encoding="utf-8")
    quality = score_output(case, content)
    failures = calibration_failures(quality, replay.get("expected", {}))
    row = _base_result_row(spec)
    row.update(
        {
            "status": "replay_ok" if not failures else "replay_failed",
            "reason": None if not failures else "; ".join(failures),
            "quality": quality,
            "source": "scorer_calibration_replay",
            "response_path": str(response_path),
            "response_sha256": file_sha256(response_path),
            "calibration_expected": replay.get("expected", {}),
            "calibration_failures": failures,
            "wall_duration_sec": 0.0,
        }
    )
    return row


def _remaining_timeout(
    *,
    benchmark_started: float,
    max_wall_seconds: float,
    command_timeout: float,
) -> float:
    remaining = max_wall_seconds - (time.perf_counter() - benchmark_started)
    return max(0.0, min(command_timeout, remaining))


def _command_record(result: CommandResult) -> dict[str, Any]:
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "duration_sec": result.duration_sec,
        "timed_out": result.timed_out,
        "launch_error": result.launch_error,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


def execute_harness_spec(
    spec: RunSpec,
    *,
    result_dir: Path,
    args: argparse.Namespace,
    command_runner: CommandRunner,
    benchmark_started: float,
    max_wall_seconds: float,
) -> dict[str, Any]:
    artifact_root = result_dir / "harness-artifacts"
    command = _base_argos_command()
    command.extend(
        [
            "benchmark",
            "--iterations",
            str(getattr(args, "harness_iterations", 2)),
            "--artifact-root",
            str(artifact_root),
            "--json",
        ]
    )
    timeout = _remaining_timeout(
        benchmark_started=benchmark_started,
        max_wall_seconds=max_wall_seconds,
        command_timeout=float(args.timeout),
    )
    row = _base_result_row(spec)
    if timeout <= 0:
        row.update(
            {
                "status": "budget_skipped",
                "reason": "wall-time budget exhausted before harness launch",
            }
        )
        return row
    result = command_runner(
        command,
        cwd=ROOT,
        timeout=timeout,
        env=prepare_env(result_dir),
    )
    meta, parse_error = _parse_meta(result)
    status = classify_launch(
        result.exit_code,
        meta,
        result.stderr,
        result.timed_out,
        "harness",
        stdout=result.stdout,
        launch_error=result.launch_error,
    )
    if status == "needs_human" and meta.get("status") == "pass":
        status = "ok"
    if parse_error and status == "ok":
        status = "parse_error"
    passed = status == "ok" and meta.get("status") == "pass"
    row.update(
        {
            "status": "ok" if passed else (
                "harness_failed" if status == "ok" else status
            ),
            "reason": parse_error or (
                None if passed else f"internal status={meta.get('status')!r}"
            ),
            "wall_duration_sec": result.duration_sec,
            "artifact_dir": meta.get("artifact_dir"),
            "commands": [_command_record(result)],
            "harness": {
                "suite": meta.get("suite_id") or meta.get("suite"),
                "suite_version": meta.get("suite_version"),
                "problem_set_version": meta.get("problem_set_version"),
                "status": meta.get("status"),
                "normalized_score": meta.get("normalized_score"),
                "score": meta.get("score"),
                "max_score": meta.get("max_score"),
                "surface_counts": meta.get("surface_counts"),
                "provider_availability": meta.get("provider_availability"),
                "benchmark_fingerprint": meta.get("benchmark_fingerprint"),
            },
        }
    )
    return row


def _build_oneshot_command(
    spec: RunSpec,
    case: dict[str, Any],
    *,
    result_dir: Path,
    artifact_root: Path,
    config_path: Path | None,
) -> list[str]:
    turn = _turn_prompts(case)[0]
    prompt_path = _materialize_prompt(
        result_dir, spec.spec_id, 1, str(turn["prompt"])
    )
    command = _base_argos_command(config_path)
    command.extend(
        [
            "run",
            str(case["mode"]),
            "--prompt-file",
            str(prompt_path),
        ]
    )
    command.extend(_argos_flags(spec.argoses, single_ok=True))
    command.extend(_case_context_args(case, turn))
    command.extend(["--artifact-root", str(artifact_root), "--json"])
    return command


def _build_start_command(
    spec: RunSpec,
    case: dict[str, Any],
    *,
    result_dir: Path,
    artifact_root: Path,
    config_path: Path | None,
) -> list[str]:
    turn = _turn_prompts(case)[0]
    prompt_path = _materialize_prompt(
        result_dir, spec.spec_id, 1, str(turn["prompt"])
    )
    mode = "council" if spec.launch == "council" else str(case["mode"])
    command = _base_argos_command(config_path)
    command.extend(["start", mode, "--prompt-file", str(prompt_path)])
    command.extend(_argos_flags(spec.argoses, single_ok=True))
    command.extend(_case_context_args(case, turn))
    command.extend(["--artifact-root", str(artifact_root), "--json"])
    return command


def _build_ask_command(
    spec: RunSpec,
    case: dict[str, Any],
    *,
    turn: dict[str, Any],
    turn_number: int,
    session_id: str,
    result_dir: Path,
    artifact_root: Path,
    config_path: Path | None,
) -> list[str]:
    prompt_path = _materialize_prompt(
        result_dir, spec.spec_id, turn_number, str(turn["prompt"])
    )
    command = _base_argos_command(config_path)
    command.extend(
        [
            "ask",
            session_id,
            "--prompt-file",
            str(prompt_path),
        ]
    )
    if spec.argoses:
        command.extend(_argos_flags(spec.argoses, single_ok=False))
    command.extend(_case_context_args(case, turn))
    command.extend(["--artifact-root", str(artifact_root), "--json"])
    return command


def _build_debate_command(
    spec: RunSpec,
    case: dict[str, Any],
    *,
    result_dir: Path,
    artifact_root: Path,
    config_path: Path | None,
) -> list[str]:
    turn = _turn_prompts(case)[0]
    prompt_path = _materialize_prompt(
        result_dir, spec.spec_id, 1, str(turn["prompt"])
    )
    debate = spec.metadata.get("debate")
    if not isinstance(debate, dict):
        debate = case.get("debate") if isinstance(case.get("debate"), dict) else {}
    command = _base_argos_command(config_path)
    command.extend(
        [
            "debate",
            str(case["mode"]),
            "--prompt-file",
            str(prompt_path),
        ]
    )
    command.extend(_argos_flags(spec.argoses, single_ok=True))
    command.extend(_case_context_args(case, turn))
    command.extend(
        [
            "--rounds",
            str(debate.get("rounds", 2)),
            "--share-chars",
            str(debate.get("share_chars", 8000)),
            "--total-share-chars",
            str(debate.get("total_share_chars", 24000)),
        ]
    )
    if debate.get("moderator"):
        command.extend(["--moderator", str(debate["moderator"])])
    command.extend(["--artifact-root", str(artifact_root), "--json"])
    return command


def _invoke(
    command: list[str],
    *,
    result_dir: Path,
    args: argparse.Namespace,
    command_runner: CommandRunner,
    benchmark_started: float,
    max_wall_seconds: float,
) -> tuple[CommandResult | None, str | None]:
    timeout = _remaining_timeout(
        benchmark_started=benchmark_started,
        max_wall_seconds=max_wall_seconds,
        command_timeout=float(args.timeout),
    )
    if timeout <= 0:
        return None, "wall-time budget exhausted"
    result = command_runner(
        command,
        cwd=ROOT,
        timeout=timeout,
        env=prepare_env(result_dir),
    )
    return result, None


def _classify_result(
    result: CommandResult,
    meta: dict[str, Any],
    *,
    launch: str,
    parse_error: str | None,
    persistent: bool,
) -> str:
    status = classify_launch(
        result.exit_code,
        meta,
        result.stderr,
        result.timed_out,
        launch,
        stdout=result.stdout,
        launch_error=result.launch_error,
        persistent=persistent,
    )
    if parse_error and status == "ok":
        return "parse_error"
    return status


def _classified_reason(
    status: str,
    result: CommandResult,
    meta: dict[str, Any],
    parse_error: str | None,
) -> str | None:
    if status == "ok":
        return None
    if status == "timeout":
        return f"command timed out after {result.duration_sec:.3f}s"
    if status == "outcome_unknown":
        return (
            f"persistent command timed out after {result.duration_sec:.3f}s; "
            "provider outcome is unknown"
        )
    if status == "parse_error":
        return parse_error or "command output could not be parsed"
    error_text = _error_text(meta, result.stderr, result.stdout).strip()
    if error_text:
        return error_text[-2000:]
    return status.replace("_", " ")


def _run_single_or_debate(
    spec: RunSpec,
    case: dict[str, Any],
    *,
    result_dir: Path,
    artifact_root: Path,
    config_path: Path | None,
    args: argparse.Namespace,
    command_runner: CommandRunner,
    benchmark_started: float,
    max_wall_seconds: float,
) -> tuple[str, list[dict[str, Any]], list[CommandResult], str | None]:
    command = (
        _build_oneshot_command(
            spec,
            case,
            result_dir=result_dir,
            artifact_root=artifact_root,
            config_path=config_path,
        )
        if spec.launch == "oneshot"
        else _build_debate_command(
            spec,
            case,
            result_dir=result_dir,
            artifact_root=artifact_root,
            config_path=config_path,
        )
    )
    result, budget_reason = _invoke(
        command,
        result_dir=result_dir,
        args=args,
        command_runner=command_runner,
        benchmark_started=benchmark_started,
        max_wall_seconds=max_wall_seconds,
    )
    if result is None:
        return "budget_skipped", [], [], budget_reason
    meta, parse_error = _parse_meta(result)
    status = _classify_result(
        result,
        meta,
        launch=spec.launch,
        parse_error=parse_error,
        persistent=spec.launch == "debate",
    )
    return (
        status,
        [meta] if meta else [],
        [result],
        _classified_reason(status, result, meta, parse_error),
    )


def _run_session(
    spec: RunSpec,
    case: dict[str, Any],
    *,
    result_dir: Path,
    artifact_root: Path,
    config_path: Path | None,
    args: argparse.Namespace,
    command_runner: CommandRunner,
    benchmark_started: float,
    max_wall_seconds: float,
    remaining_cost_usd: float,
) -> tuple[str, list[dict[str, Any]], list[CommandResult], str | None]:
    turns = spec.metadata.get("turns")
    if not isinstance(turns, list) or not turns:
        turns = _turn_prompts(case)
    start_command = _build_start_command(
        spec,
        case,
        result_dir=result_dir,
        artifact_root=artifact_root,
        config_path=config_path,
    )
    start_result, budget_reason = _invoke(
        start_command,
        result_dir=result_dir,
        args=args,
        command_runner=command_runner,
        benchmark_started=benchmark_started,
        max_wall_seconds=max_wall_seconds,
    )
    if start_result is None:
        return "budget_skipped", [], [], budget_reason
    start_meta, parse_error = _parse_meta(start_result)
    status = _classify_result(
        start_result,
        start_meta,
        launch=spec.launch,
        parse_error=parse_error,
        persistent=True,
    )
    metas = [start_meta] if start_meta else []
    command_results = [start_result]
    if status != "ok":
        return (
            status,
            metas,
            command_results,
            _classified_reason(status, start_result, start_meta, parse_error),
        )
    session_id = start_meta.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return "parse_error", metas, command_results, "missing session_id"
    if len(turns) > 1:
        start_telemetry = _telemetry_from_metas([start_meta])
        if not start_telemetry["cost_telemetry_complete"]:
            return (
                "budget_telemetry_missing",
                metas,
                command_results,
                "start turn omitted complete cost telemetry; later turns were not launched",
            )
        if float(start_telemetry["cost_usd"]) >= remaining_cost_usd:
            return (
                "budget_exhausted",
                metas,
                command_results,
                "reported cost cap reached before the next session turn",
            )
    for turn_number, turn in enumerate(turns[1:], start=2):
        ask_command = _build_ask_command(
            spec,
            case,
            turn=turn,
            turn_number=turn_number,
            session_id=session_id,
            result_dir=result_dir,
            artifact_root=artifact_root,
            config_path=config_path,
        )
        ask_result, budget_reason = _invoke(
            ask_command,
            result_dir=result_dir,
            args=args,
            command_runner=command_runner,
            benchmark_started=benchmark_started,
            max_wall_seconds=max_wall_seconds,
        )
        if ask_result is None:
            return "budget_skipped", metas, command_results, budget_reason
        ask_meta, parse_error = _parse_meta(ask_result)
        if ask_meta:
            metas.append(ask_meta)
        command_results.append(ask_result)
        status = _classify_result(
            ask_result,
            ask_meta,
            launch=spec.launch,
            parse_error=parse_error,
            persistent=True,
        )
        if status != "ok":
            return (
                status,
                metas,
                command_results,
                _classified_reason(status, ask_result, ask_meta, parse_error),
            )
        if turn_number < len(turns):
            telemetry = _telemetry_from_metas(metas)
            if not telemetry["cost_telemetry_complete"]:
                return (
                    "budget_telemetry_missing",
                    metas,
                    command_results,
                    "a session turn omitted complete cost telemetry; "
                    "later turns were not launched",
                )
            if float(telemetry["cost_usd"]) >= remaining_cost_usd:
                return (
                    "budget_exhausted",
                    metas,
                    command_results,
                    "reported cost cap reached before the next session turn",
                )
    return "ok", metas, command_results, None


def execute_live_spec(
    spec: RunSpec,
    *,
    manifest: dict[str, Any],
    case_index: dict[str, dict[str, Any]],
    result_dir: Path,
    args: argparse.Namespace,
    command_runner: CommandRunner,
    benchmark_started: float,
    max_wall_seconds: float,
    remaining_cost_usd: float,
) -> dict[str, Any]:
    del manifest  # carried by the caller for a uniform executor signature
    case = case_index[str(spec.case_id)]
    row = _base_result_row(spec)
    artifact_root = result_dir / "live-artifacts" / _safe_component(spec.spec_id)
    config_path = _config_for_spec(
        spec, result_dir=result_dir, args=args, case=case
    )
    if spec.launch in {"oneshot", "debate"}:
        status, metas, command_results, reason = _run_single_or_debate(
            spec,
            case,
            result_dir=result_dir,
            artifact_root=artifact_root,
            config_path=config_path,
            args=args,
            command_runner=command_runner,
            benchmark_started=benchmark_started,
            max_wall_seconds=max_wall_seconds,
        )
    else:
        status, metas, command_results, reason = _run_session(
            spec,
            case,
            result_dir=result_dir,
            artifact_root=artifact_root,
            config_path=config_path,
            args=args,
            command_runner=command_runner,
            benchmark_started=benchmark_started,
            max_wall_seconds=max_wall_seconds,
            remaining_cost_usd=remaining_cost_usd,
        )
    wall_duration = round(
        sum(result.duration_sec for result in command_results), 6
    )
    telemetry = _telemetry_from_metas(metas)
    final_meta = metas[-1] if metas else {}
    content = _content_from_meta(final_meta, spec.launch) if status == "ok" else ""
    # A Council `start` returns partner contributions, not the host's final
    # synthesis.  Recording quality here would mislabel contributions as the
    # Council output.  Replay controls exercise the synthesis scorer instead.
    quality = (
        score_output(case, content)
        if status == "ok" and spec.launch != "council" and content.strip()
        else None
    )
    if status == "ok" and spec.launch != "council" and not content.strip():
        status = "parse_error"
        reason = reason or "successful command contained no scoreable output"
    effective_config_hash = next(
        (
            config_hash
            for meta in metas
            if (config_hash := _read_effective_config_hash(meta))
        ),
        None,
    )
    row.update(
        {
            "status": status,
            "reason": reason,
            "quality": quality,
            "wall_duration_sec": wall_duration,
            "provider_duration_sec": telemetry["provider_duration_sec"],
            "cost_usd": telemetry["cost_usd"],
            "cost_sample_count": telemetry["cost_sample_count"],
            "result_sample_count": telemetry["result_sample_count"],
            "cost_telemetry_complete": telemetry["cost_telemetry_complete"],
            "token_payloads": telemetry["token_payloads"],
            "providers": telemetry["providers"],
            "models": telemetry["models"],
            "assignment_hashes": telemetry["assignment_hashes"],
            "prompt_hashes": telemetry["prompt_hashes"],
            "effective_config_sha256": effective_config_hash,
            "artifact_dir": final_meta.get("artifact_dir"),
            "commands": [_command_record(result) for result in command_results],
            "output_sha256": sha256_text(content) if content else None,
            "output_kind": (
                "partner_contributions"
                if spec.launch == "council" and status == "ok"
                else "model_output"
            ),
            "quality_omission_reason": (
                "Council host synthesis is not produced by the CLI launch; "
                "partner contributions remain readiness/conversation evidence."
                if spec.launch == "council" and status == "ok"
                else None
            ),
        }
    )
    return row


def resolve_prompt_value(
    launch: dict[str, Any],
) -> tuple[str, str | None]:
    if launch.get("prompt") is not None:
        return str(launch["prompt"]), None
    if launch.get("prompt_file"):
        path = ROOT / str(launch["prompt_file"])
        return path.read_text(encoding="utf-8"), str(path)
    return "", None


def launch_inputs_hash(
    launch: dict[str, Any],
    case: dict[str, Any] | None,
) -> str:
    return case_content_hash(case) if case else sha256_text(canonical_json(launch))


def launch_fingerprint(
    manifest: dict[str, Any],
    launch: dict[str, Any],
    case: dict[str, Any] | None = None,
) -> str:
    return sha256_text(
        canonical_json(
            {
                "benchmark_version": manifest.get("version"),
                "launch": launch,
                "case_hash": case_content_hash(case) if case else None,
            }
        )
    )


def comparable_launch_key(
    manifest: dict[str, Any],
    launch: dict[str, Any],
    case: dict[str, Any] | None = None,
) -> str:
    payload = {
        "benchmark_version": manifest.get("version"),
        "track": normalize_track(str(launch.get("track", "replay"))),
        "surface": normalize_launch(str(launch.get("surface", "replay"))),
        "case_id": case.get("case_id") if case else launch.get("case_id"),
        "case_hash": case_content_hash(case) if case else None,
        "prompt_contract": PROMPT_PROTOCOL_VERSION,
        "scorer": SCORER_VERSION,
    }
    return sha256_text(canonical_json(payload))


def build_quality_row(
    manifest: dict[str, Any],
    case: dict[str, Any],
    launch: dict[str, Any],
    result_dir: Path,
    artifact_root: Path,
    timeout: int,
) -> dict[str, Any]:
    """Compatibility adapter for the first v2 prototype's direct helpers."""

    surface = normalize_launch(str(launch.get("surface", "replay")))
    if surface == "replay":
        response_path = ROOT / str(launch["response_path"])
        content = response_path.read_text(encoding="utf-8")
        legacy = score_quality(case, content, {"results": []}, 0.0, 0)
        legacy.update(
            {
                "launch_id": launch.get("launch_id"),
                "track": launch.get("track"),
                "surface": "replay",
                "status": "replayed",
                "fingerprint": launch_fingerprint(manifest, launch, case),
                "comparable_key": comparable_launch_key(
                    manifest, launch, case
                ),
                "command": "replay",
            }
        )
        return legacy
    command, env = build_launch_command(
        launch, case, result_dir, artifact_root
    )
    result = run_command(command, timeout=timeout, env=env)
    meta, _ = _parse_meta(result)
    status = classify_launch(
        result.exit_code,
        meta,
        result.stderr,
        result.timed_out,
        surface,
        stdout=result.stdout,
        launch_error=result.launch_error,
        persistent=surface in {"session", "council", "debate"},
    )
    content = _content_from_meta(meta, surface)
    legacy = score_quality(
        case, content, meta, result.duration_sec, result.exit_code
    )
    legacy.update(
        {
            "launch_id": launch.get("launch_id"),
            "track": launch.get("track"),
            "surface": surface,
            "status": status,
            "fingerprint": launch_fingerprint(manifest, launch, case),
            "comparable_key": comparable_launch_key(manifest, launch, case),
            "command": command,
        }
    )
    return legacy


def _status_counts(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _pairwise_jaccard(sets: Sequence[set[str]]) -> float | None:
    if len(sets) < 2:
        return None
    values: list[float] = []
    for left_index, left in enumerate(sets):
        for right in sets[left_index + 1 :]:
            union = left | right
            values.append(len(left & right) / len(union) if union else 1.0)
    return round(statistics.mean(values), 6) if values else None


def _observation_identity(items: Sequence[dict[str, Any]]) -> dict[str, list[str]]:
    def values_for(key: str) -> list[str]:
        values: set[str] = set()
        for item in items:
            value = item.get(key)
            if isinstance(value, list):
                values.update(str(entry) for entry in value if entry)
            elif value:
                values.add(str(value))
        return sorted(values)

    return {
        "models": values_for("models"),
        "providers": values_for("providers"),
        "effective_config_sha256": values_for("effective_config_sha256"),
        "assignment_hashes": values_for("assignment_hashes"),
        "prompt_hashes": values_for("prompt_hashes"),
    }


def _quality_cohorts(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") != "ok" or not isinstance(row.get("quality"), dict):
            continue
        grouped.setdefault(str(row["cohort_key"]), []).append(row)
    summaries: dict[str, Any] = {}
    for cohort, items in grouped.items():
        quality_rows = [item["quality"] for item in items]
        concept_sets = [
            set(quality.get("matched_concepts", [])) for quality in quality_rows
        ]
        summaries[cohort] = {
            "track": items[0].get("track"),
            "launch": items[0].get("launch"),
            "case_id": items[0].get("case_id"),
            "argoses": items[0].get("argoses"),
            "sample_count": len(items),
            "observation_identity": _observation_identity(items),
            "score": summarize(
                [float(quality.get("score", 0.0)) for quality in quality_rows]
            ),
            "acceptance_rate": round(
                sum(1 for quality in quality_rows if quality.get("accepted"))
                / len(quality_rows),
                6,
            ),
            "coverage": summarize(
                [float(quality.get("coverage", 0.0)) for quality in quality_rows]
            ),
            "precision": summarize(
                [float(quality.get("precision", 0.0)) for quality in quality_rows]
            ),
            "concept_jaccard": _pairwise_jaccard(concept_sets),
        }
    return summaries


def _performance_cohorts(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        grouped.setdefault(str(row["cohort_key"]), []).append(row)
    summaries: dict[str, Any] = {}
    for cohort, items in grouped.items():
        quality_items = [
            item for item in items if isinstance(item.get("quality"), dict)
        ]
        costs = [
            float(item["cost_usd"])
            for item in items
            if item.get("cost_usd") is not None
        ]
        provider_durations = [
            float(item["provider_duration_sec"])
            for item in items
            if item.get("provider_duration_sec") is not None
        ]
        wall_durations = [
            float(item["wall_duration_sec"])
            for item in items
            if item.get("wall_duration_sec") is not None
        ]
        accepted_findings = sum(
            int(item["quality"].get("accepted_finding_count", 0))
            for item in quality_items
        )
        cost_coverage_complete = len(costs) == len(items)
        summaries[cohort] = {
            "track": items[0].get("track"),
            "launch": items[0].get("launch"),
            "case_id": items[0].get("case_id"),
            "argoses": items[0].get("argoses"),
            "sample_count": len(items),
            "quality_sample_count": len(quality_items),
            "observation_identity": _observation_identity(items),
            "wall_latency_sec": summarize(wall_durations),
            "provider_duration_sec": summarize(provider_durations),
            "cost_usd": summarize(costs),
            "cost_telemetry_coverage": round(len(costs) / len(items), 6),
            "provider_duration_coverage": round(
                len(provider_durations) / len(items), 6
            ),
            "accepted_finding_count": accepted_findings,
            "cost_per_accepted_finding_usd": (
                round(sum(costs) / accepted_findings, 6)
                if accepted_findings and cost_coverage_complete
                else None
            ),
            "wall_seconds_per_accepted_finding": (
                round(sum(wall_durations) / accepted_findings, 6)
                if accepted_findings
                else None
            ),
        }
    return summaries


def build_summaries(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    harness_rows = [row for row in rows if row.get("track") == "harness"]
    replay_rows = [row for row in rows if row.get("track") == "replay"]
    live_rows = [
        row for row in rows if row.get("track") in LIVE_TRACKS
    ]
    live_quality_rows = [
        row
        for row in live_rows
        if row.get("status") == "ok" and isinstance(row.get("quality"), dict)
    ]
    attempted_live_rows = [
        row for row in live_rows if row.get("status") != "budget_skipped"
    ]
    readiness_durations = [
        float(row["wall_duration_sec"])
        for row in live_rows
        if row.get("wall_duration_sec") is not None
    ]
    return {
        "harness": {
            "status": (
                "not_run"
                if not harness_rows
                else (
                    "pass"
                    if all(row.get("status") == "ok" for row in harness_rows)
                    else "fail"
                )
            ),
            "status_counts": _status_counts(harness_rows),
            "rows": harness_rows,
        },
        "scorer_calibration": {
            "status": (
                "not_run"
                if not replay_rows
                else (
                    "pass"
                    if all(row.get("status") == "replay_ok" for row in replay_rows)
                    else "fail"
                )
            ),
            "status_counts": _status_counts(replay_rows),
            "rows": replay_rows,
        },
        "readiness": {
            "status_counts": _status_counts(live_rows),
            "selected_count": len(live_rows),
            "attempted_count": len(attempted_live_rows),
            "skipped_count": len(live_rows) - len(attempted_live_rows),
            "successful_count": sum(
                1 for row in attempted_live_rows if row.get("status") == "ok"
            ),
            "time_to_terminal_sec": summarize(readiness_durations),
            "rows": [
                {
                    key: row.get(key)
                    for key in (
                        "spec_id",
                        "track",
                        "launch",
                        "case_id",
                        "argoses",
                        "status",
                        "reason",
                        "wall_duration_sec",
                        "models",
                        "providers",
                        "artifact_dir",
                    )
                }
                for row in live_rows
            ],
        },
        "quality": {
            "live_answer_count": len(live_quality_rows),
            "unscored_success_count": sum(
                1
                for row in live_rows
                if row.get("status") == "ok" and row.get("quality") is None
            ),
            "cohorts": _quality_cohorts(live_rows),
            "rows": [
                row for row in live_rows if isinstance(row.get("quality"), dict)
            ],
            "interpretation": (
                "No live model-quality baseline was produced."
                if not live_quality_rows
                else "Quality is reported per comparable cohort; cohorts are not averaged."
            ),
        },
        "performance": {
            "cohorts": _performance_cohorts(live_rows),
            "interpretation": (
                "Only successful live outputs are included. Replay timings and "
                "readiness failures are excluded."
            ),
        },
    }


def compare_benchmark_results(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    current_contract = (
        current.get("protocol", {})
        .get("contract", {})
        .get("contract_sha256")
    )
    baseline_contract = (
        baseline.get("protocol", {})
        .get("contract", {})
        .get("contract_sha256")
    )
    current_selection = current.get("run_plan", {}).get(
        "comparison_selection_sha256"
    )
    baseline_selection = baseline.get("run_plan", {}).get(
        "comparison_selection_sha256"
    )
    reasons: list[str] = []
    if not current_contract or not baseline_contract:
        reasons.append("missing v2 benchmark contract hash")
    elif current_contract != baseline_contract:
        reasons.append(
            f"contract hash differs: {baseline_contract} -> {current_contract}"
        )
    if not current_selection or not baseline_selection:
        reasons.append("missing run-selection comparison hash")
    elif current_selection != baseline_selection:
        reasons.append(
            "run selection or budgets differ: "
            f"{baseline_selection} -> {current_selection}"
        )
    if reasons:
        return {
            "status": "incompatible",
            "comparable": False,
            "reasons": reasons,
            "harness": {},
            "quality_cohorts": {},
            "performance_cohorts": {},
            "cohorts": {},
        }

    def metric_delta(before: Any, after: Any) -> float | None:
        if before is None or after is None:
            return None
        return round(float(after) - float(before), 6)

    def harness_identity(rows: Sequence[dict[str, Any]]) -> dict[str, list[str]]:
        identity: dict[str, list[str]] = {}
        for key in ("suite_version", "problem_set_version", "max_score"):
            identity[key] = sorted(
                {
                    str(row.get("harness", {}).get(key))
                    for row in rows
                    if row.get("harness", {}).get(key) is not None
                }
            )
        return identity

    def identity_check(
        before: dict[str, Any], after: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        identity_reasons: list[str] = []
        required = ("models", "providers", "effective_config_sha256")
        for label, identity in (("baseline", before), ("current", after)):
            missing = [key for key in required if not identity.get(key)]
            if missing:
                identity_reasons.append(
                    f"{label} observation identity is missing {missing}"
                )
        if before != after:
            identity_reasons.append(
                "observed model/provider/config/prompt assignment differs"
            )
        return not identity_reasons, identity_reasons

    current_harness_rows = current.get("harness", {}).get("rows", [])
    baseline_harness_rows = baseline.get("harness", {}).get("rows", [])
    current_harness_wall = [
        float(row["wall_duration_sec"])
        for row in current_harness_rows
        if row.get("status") == "ok" and row.get("wall_duration_sec") is not None
    ]
    baseline_harness_wall = [
        float(row["wall_duration_sec"])
        for row in baseline_harness_rows
        if row.get("status") == "ok" and row.get("wall_duration_sec") is not None
    ]
    current_harness_summary = summarize(current_harness_wall)
    baseline_harness_summary = summarize(baseline_harness_wall)
    current_harness_identity = harness_identity(current_harness_rows)
    baseline_harness_identity = harness_identity(baseline_harness_rows)
    harness_overlap = bool(current_harness_wall and baseline_harness_wall)
    harness_identity_complete = all(
        current_harness_identity.get(key) and baseline_harness_identity.get(key)
        for key in ("suite_version", "problem_set_version", "max_score")
    )
    harness_comparable = (
        harness_overlap
        and harness_identity_complete
        and current_harness_identity == baseline_harness_identity
    )
    harness_comparison = {
        "comparable": harness_comparable,
        "sample_count_before": len(baseline_harness_wall),
        "sample_count_after": len(current_harness_wall),
        "identity_before": baseline_harness_identity,
        "identity_after": current_harness_identity,
        "wall_latency_sec_before": baseline_harness_summary,
        "wall_latency_sec_after": current_harness_summary,
        "wall_latency_mean_delta_sec": (
            metric_delta(
                baseline_harness_summary.get("mean"),
                current_harness_summary.get("mean"),
            )
            if harness_comparable
            else None
        ),
        "omission_reason": (
            None
            if harness_comparable
            else (
                "no overlapping successful harness samples"
                if not harness_overlap
                else "harness suite identity is missing or differs"
            )
        ),
    }

    current_quality = current.get("quality", {}).get("cohorts", {})
    baseline_quality = baseline.get("quality", {}).get("cohorts", {})
    quality_overlap = sorted(set(current_quality) & set(baseline_quality))
    quality_deltas: dict[str, Any] = {}
    for cohort in quality_overlap:
        after = current_quality[cohort]
        before = baseline_quality[cohort]
        before_identity = before.get("observation_identity", {})
        after_identity = after.get("observation_identity", {})
        identity_comparable, identity_reasons = identity_check(
            before_identity, after_identity
        )
        current_score = after.get("score", {}).get("mean")
        baseline_score = before.get("score", {}).get("mean")
        quality_deltas[cohort] = {
            "comparable": identity_comparable,
            "reasons": identity_reasons,
            "identity_before": before_identity,
            "identity_after": after_identity,
            "score_mean_before": baseline_score,
            "score_mean_after": current_score,
            "score_mean_delta": (
                metric_delta(baseline_score, current_score)
                if identity_comparable
                else None
            ),
            "acceptance_rate_before": before.get("acceptance_rate"),
            "acceptance_rate_after": after.get("acceptance_rate"),
            "acceptance_rate_delta": (
                metric_delta(
                    before.get("acceptance_rate"),
                    after.get("acceptance_rate"),
                )
                if identity_comparable
                else None
            ),
        }

    current_performance = current.get("performance", {}).get("cohorts", {})
    baseline_performance = baseline.get("performance", {}).get("cohorts", {})
    performance_overlap = sorted(
        set(current_performance) & set(baseline_performance)
    )
    performance_deltas: dict[str, Any] = {}
    for cohort in performance_overlap:
        after = current_performance[cohort]
        before = baseline_performance[cohort]
        before_identity = before.get("observation_identity", {})
        after_identity = after.get("observation_identity", {})
        identity_comparable, identity_reasons = identity_check(
            before_identity, after_identity
        )
        before_wall = before.get("wall_latency_sec", {}).get("mean")
        after_wall = after.get("wall_latency_sec", {}).get("mean")
        before_provider = before.get("provider_duration_sec", {}).get("mean")
        after_provider = after.get("provider_duration_sec", {}).get("mean")
        before_cost = before.get("cost_usd", {}).get("mean")
        after_cost = after.get("cost_usd", {}).get("mean")
        complete_cost = (
            before.get("cost_telemetry_coverage") == 1.0
            and after.get("cost_telemetry_coverage") == 1.0
        )
        performance_deltas[cohort] = {
            "comparable": identity_comparable,
            "reasons": identity_reasons,
            "identity_before": before_identity,
            "identity_after": after_identity,
            "wall_latency_mean_sec_before": before_wall,
            "wall_latency_mean_sec_after": after_wall,
            "wall_latency_mean_delta_sec": (
                metric_delta(before_wall, after_wall)
                if identity_comparable
                else None
            ),
            "provider_duration_mean_sec_before": before_provider,
            "provider_duration_mean_sec_after": after_provider,
            "provider_duration_mean_delta_sec": (
                metric_delta(before_provider, after_provider)
                if identity_comparable
                else None
            ),
            "cost_mean_usd_before": before_cost,
            "cost_mean_usd_after": after_cost,
            "cost_mean_delta_usd": (
                metric_delta(before_cost, after_cost)
                if identity_comparable and complete_cost
                else None
            ),
            "cost_delta_omission_reason": (
                None
                if identity_comparable and complete_cost
                else (
                    "observation identity differs"
                    if not identity_comparable
                    else "cost telemetry is incomplete in at least one run"
                )
            ),
        }

    comparable_quality_count = sum(
        1 for item in quality_deltas.values() if item["comparable"]
    )
    comparable_performance_count = sum(
        1 for item in performance_deltas.values() if item["comparable"]
    )
    comparable_axis_count = (
        int(harness_comparable)
        + comparable_quality_count
        + comparable_performance_count
    )
    mismatched_cohort_count = (
        len(quality_overlap)
        + len(performance_overlap)
        - comparable_quality_count
        - comparable_performance_count
    )
    comparison_reasons: list[str] = []
    if comparable_axis_count == 0:
        comparison_reasons.append(
            "matching contract but no overlapping comparable harness or live cohort"
        )
    if mismatched_cohort_count:
        comparison_reasons.append(
            f"{mismatched_cohort_count} overlapping cohort axes have "
            "different or incomplete observation identity"
        )
    comparison_status = (
        "no_overlap"
        if comparable_axis_count == 0
        else "partially_comparable"
        if mismatched_cohort_count
        else "comparable"
    )
    return {
        "status": comparison_status,
        "comparable": comparable_axis_count > 0,
        "reasons": comparison_reasons,
        "harness": harness_comparison,
        "overlapping_cohort_count": len(quality_overlap),
        "overlapping_quality_cohort_count": len(quality_overlap),
        "overlapping_performance_cohort_count": len(performance_overlap),
        "comparable_quality_cohort_count": comparable_quality_count,
        "comparable_performance_cohort_count": comparable_performance_count,
        "only_current": sorted(set(current_quality) - set(baseline_quality)),
        "only_baseline": sorted(set(baseline_quality) - set(current_quality)),
        "performance_only_current": sorted(
            set(current_performance) - set(baseline_performance)
        ),
        "performance_only_baseline": sorted(
            set(baseline_performance) - set(current_performance)
        ),
        "quality_cohorts": quality_deltas,
        "performance_cohorts": performance_deltas,
        "cohorts": quality_deltas,
    }


def _result_status(
    summaries: dict[str, Any],
    *,
    live_requested: bool,
) -> str:
    if summaries["harness"]["status"] == "fail":
        return "fail"
    if summaries["scorer_calibration"]["status"] == "fail":
        return "fail"
    readiness = summaries["readiness"]
    if live_requested:
        status_counts = readiness["status_counts"]
        non_success_count = sum(
            count for status, count in status_counts.items() if status != "ok"
        )
        if non_success_count:
            return "degraded"
    return "pass"


def render_report(payload: dict[str, Any]) -> str:
    protocol = payload["protocol"]
    plan = payload["run_plan"]
    harness = payload["harness"]
    calibration = payload["scorer_calibration"]
    readiness = payload["readiness"]
    quality = payload["quality"]
    performance = payload["performance"]
    lines = [
        f"# Argos benchmark v{payload['benchmark_version']} — {payload['profile']}",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Run: `{payload['run_id']}`",
        f"Status: `{payload['status']}`",
        f"Live opt-in: `{plan['live']}`",
        f"Result directory: `{payload['result_dir']}`",
        "",
        "> This report intentionally has no global model score. Harness health, "
        "provider readiness, output quality and performance are independent.",
        "",
        "## Protocol",
        "",
        f"- contract: `{protocol['contract']['contract_sha256']}`",
        f"- manifest: `{protocol['contract']['manifest_sha256']}`",
        f"- corpus: `{protocol['contract']['corpus_sha256']}`",
        f"- scorer: `{protocol['contract']['scorer_contract_sha256']}`",
        f"- prompt contract: `{protocol['contract']['prompt_contract_sha256']}`",
        f"- measurement protocol: `{protocol['measurement_protocol_version']}`",
        f"- tracks: `{', '.join(plan['selection']['tracks'])}`",
        f"- launches: `{', '.join(plan['selection']['launches'])}`",
        f"- planned live calls: `{plan['budgets']['estimated_live_calls']}` / "
        f"`{plan['budgets']['max_calls']}`",
        "",
        "## Harness health",
        "",
        f"- status: `{harness['status']}`",
        f"- outcomes: `{canonical_json(harness['status_counts'])}`",
    ]
    for row in harness.get("rows", []):
        internal = row.get("harness") or {}
        lines.append(
            f"- `{row['spec_id']}`: status=`{row['status']}`, "
            f"internal=`{internal.get('status')}`, "
            f"normalized=`{internal.get('normalized_score')}`"
        )
    lines.extend(
        [
            "",
            "## Scorer calibration (replays, not model results)",
            "",
            f"- status: `{calibration['status']}`",
            f"- outcomes: `{canonical_json(calibration['status_counts'])}`",
        ]
    )
    for row in calibration.get("rows", []):
        quality_row = row.get("quality") or {}
        lines.append(
            f"- `{row['spec_id']}`: status=`{row['status']}`, "
            f"score=`{quality_row.get('score')}`, "
            f"accepted=`{quality_row.get('accepted')}`"
        )
    lines.extend(
        [
            "",
            "## Provider and launcher readiness",
            "",
            f"- selected: `{readiness['selected_count']}`",
            f"- attempted: `{readiness['attempted_count']}`",
            f"- skipped: `{readiness['skipped_count']}`",
            f"- successful: `{readiness['successful_count']}`",
            f"- outcomes: `{canonical_json(readiness['status_counts'])}`",
        ]
    )
    for row in readiness.get("rows", []):
        lines.append(
            f"- `{row['spec_id']}`: `{row['status']}` in "
            f"`{row.get('wall_duration_sec')}`s; providers="
            f"`{','.join(row.get('providers') or []) or 'unknown'}`"
        )
    lines.extend(
        [
            "",
            "## Live output quality",
            "",
            quality["interpretation"],
            "",
        ]
    )
    for cohort, summary in quality.get("cohorts", {}).items():
        lines.append(
            f"- `{cohort}` ({summary['track']}/{summary['launch']}/"
            f"{summary['case_id']}): n=`{summary['sample_count']}`, "
            f"mean=`{summary['score']['mean']}`, "
            f"acceptance=`{summary['acceptance_rate']}`, "
            f"stability-jaccard=`{summary['concept_jaccard']}`"
        )
    lines.extend(
        [
            "",
            "## Live performance",
            "",
            performance["interpretation"],
            "",
        ]
    )
    for cohort, summary in performance.get("cohorts", {}).items():
        lines.append(
            f"- `{cohort}`: latency-p50=`{summary['wall_latency_sec']['p50']}`s, "
            f"p95=`{summary['wall_latency_sec']['p95']}`s, "
            f"cost-coverage=`{summary['cost_telemetry_coverage']}`, "
            f"cost/finding=`{summary['cost_per_accepted_finding_usd']}`"
        )
    comparison = payload.get("comparison")
    if comparison is not None:
        lines.extend(
            [
                "",
                "## Comparison",
                "",
                f"- status: `{comparison['status']}`",
                f"- comparable: `{comparison['comparable']}`",
            ]
        )
        for reason in comparison.get("reasons", []):
            lines.append(f"- refusal reason: {reason}")
        harness_delta = comparison.get("harness", {}).get(
            "wall_latency_mean_delta_sec"
        )
        if harness_delta is not None:
            lines.append(
                f"- harness wall-latency mean delta: `{harness_delta}`s"
            )
        for cohort, delta in comparison.get("quality_cohorts", {}).items():
            lines.append(
                f"- quality `{cohort}`: score-mean delta="
                f"`{delta.get('score_mean_delta')}`"
            )
        for cohort, delta in comparison.get(
            "performance_cohorts", {}
        ).items():
            lines.append(
                f"- performance `{cohort}`: wall-mean delta="
                f"`{delta.get('wall_latency_mean_delta_sec')}`s, "
                f"provider-mean delta="
                f"`{delta.get('provider_duration_mean_delta_sec')}`s, "
                f"cost-mean delta=`{delta.get('cost_mean_delta_usd')}`"
            )
    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- Harness 100/100 means the deterministic Argos contract passed; "
            "it is not a model score.",
            "- Provider failures are readiness observations and have no quality score.",
            "- Replay rows validate the scorer and are never model-performance data.",
            "- Different cohort keys are not averaged or ranked against one another.",
        ]
    )
    return "\n".join(lines) + "\n"


def execute_benchmark(
    manifest: dict[str, Any],
    args: argparse.Namespace,
    *,
    command_runner: CommandRunner = run_command,
) -> tuple[dict[str, Any], int]:
    plan = build_run_plan(manifest, args)
    if args.dry_run:
        payload = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "command": "dry-run",
            "generated_at": utc_now(),
            "run_plan": plan,
        }
        return payload, 0

    run_id = f"{utc_stamp()}-v{manifest['version']}-{args.profile}"
    result_dir = (
        Path(args.result_dir).expanduser().resolve()
        if args.result_dir
        else Path(args.artifact_root).expanduser().resolve() / run_id
    )
    result_dir.mkdir(parents=True, exist_ok=False)
    write_json(result_dir / "run-plan.json", plan)
    case_index = load_case_by_id(manifest)
    specs = [
        RunSpec(
            spec_id=str(item["spec_id"]),
            track=str(item["track"]),
            launch=str(item["launch"]),
            case_id=item.get("case_id"),
            argoses=tuple(item.get("argoses") or []),
            repetition=int(item.get("repetition", 1)),
            replay_id=item.get("replay_id"),
            requires_live=bool(item.get("requires_live")),
            enabled=bool(item.get("enabled")),
            estimated_calls=int(item.get("estimated_calls", 0)),
            estimated_cost_usd=float(item.get("estimated_cost_usd", 0.0)),
            cohort_key=str(item.get("cohort_key") or ""),
            semantic_fingerprint=str(item.get("semantic_fingerprint") or ""),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in plan["specs"]
    ]
    benchmark_started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    observed_calls = 0
    observed_cost = 0.0
    missing_cost_seen = False
    max_wall_seconds = float(plan["budgets"]["max_wall_seconds"])
    max_cost_usd = float(plan["budgets"]["max_cost_usd"])
    needs_human_seen = False
    for spec in specs:
        if not spec.enabled:
            continue
        if spec.requires_live:
            if missing_cost_seen:
                row = _base_result_row(spec)
                row.update(
                    {
                        "status": "budget_skipped",
                        "reason": (
                            "a prior live launch omitted complete cost telemetry; "
                            "further calls stopped to preserve the cost cap"
                        ),
                    }
                )
                rows.append(row)
                continue
            if observed_cost >= max_cost_usd:
                row = _base_result_row(spec)
                row.update(
                    {
                        "status": "budget_skipped",
                        "reason": "reported cost budget exhausted",
                    }
                )
                rows.append(row)
                continue
            if observed_cost + spec.estimated_cost_usd > max_cost_usd:
                row = _base_result_row(spec)
                row.update(
                    {
                        "status": "budget_skipped",
                        "reason": (
                            "the next launch estimate would exceed the "
                            "remaining reported cost budget"
                        ),
                    }
                )
                rows.append(row)
                continue
        if spec.launch == "harness":
            row = execute_harness_spec(
                spec,
                result_dir=result_dir,
                args=args,
                command_runner=command_runner,
                benchmark_started=benchmark_started,
                max_wall_seconds=max_wall_seconds,
            )
        elif spec.launch == "replay":
            row = execute_replay_spec(
                spec,
                manifest=manifest,
                case_index=case_index,
            )
        else:
            row = execute_live_spec(
                spec,
                manifest=manifest,
                case_index=case_index,
                result_dir=result_dir,
                args=args,
                command_runner=command_runner,
                benchmark_started=benchmark_started,
                max_wall_seconds=max_wall_seconds,
                remaining_cost_usd=max_cost_usd - observed_cost,
            )
            observed_calls += spec.estimated_calls
            if (
                row.get("status") == "budget_telemetry_missing"
                or (
                    row.get("status") == "ok"
                    and not row.get("cost_telemetry_complete")
                )
            ):
                missing_cost_seen = True
            elif row.get("cost_usd") is not None:
                observed_cost += float(row["cost_usd"])
            if row.get("status") == "needs_human":
                needs_human_seen = True
        rows.append(row)
        write_json(
            result_dir / "rows" / f"{_safe_component(spec.spec_id)}.json",
            row,
        )
    summaries = build_summaries(rows)
    payload: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "benchmark_version": manifest["version"],
        "profile": args.profile,
        "run_id": run_id,
        "generated_at": utc_now(),
        "manifest": str(Path(args.manifest).resolve()),
        "result_dir": str(result_dir),
        "protocol": {
            "prompt_protocol_version": PROMPT_PROTOCOL_VERSION,
            "scorer_version": SCORER_VERSION,
            "measurement_protocol_version": MEASUREMENT_PROTOCOL_VERSION,
            "isolated_assignment_version": ISOLATED_ASSIGNMENT_VERSION,
            "contract": plan["contract"],
        },
        "run_plan": plan,
        "budget_observed": {
            "estimated_calls_consumed": observed_calls,
            "reported_cost_usd": round(observed_cost, 6),
            "missing_cost_seen": missing_cost_seen,
            "wall_duration_sec": round(
                time.perf_counter() - benchmark_started, 6
            ),
        },
        "rows": rows,
        **summaries,
    }
    payload["status"] = _result_status(
        summaries, live_requested=bool(args.live)
    )
    comparison_exit = 0
    if args.compare:
        baseline_path = Path(args.compare).expanduser().resolve()
        if baseline_path.is_dir():
            baseline_path = baseline_path / "results.json"
        baseline = load_json(baseline_path)
        payload["comparison"] = compare_benchmark_results(payload, baseline)
        if not payload["comparison"]["comparable"]:
            comparison_exit = 2
    write_json(result_dir / "results.json", payload)
    (result_dir / "report.md").write_text(
        render_report(payload), encoding="utf-8"
    )
    if needs_human_seen:
        return payload, 3
    if payload["status"] == "fail":
        return payload, 1
    return payload, comparison_exit


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
    source_events = sum(
        value.get("error", 0) + value.get("skipped", 0)
        for value in health.values()
        if isinstance(value, dict)
    )
    if expected == "ok":
        score = (
            1.0
            if status_match
            and invalid_count == missing_count == unexpected_count == 0
            else 0.0
        )
    else:
        score = (
            1.0
            if status_match
            and invalid_count + missing_count + unexpected_count > 0
            else 0.0
        )
    return {
        "case_id": case["case_id"],
        "status": "pass" if score else "fail",
        "score": score,
        "verification_status": verification.get("status"),
        "invalid_evidence_ids": invalid_count,
        "missing_citations": missing_count,
        "unexpected_urls": unexpected_count,
        "source_quality_counts": counts,
        "dead_or_skipped_source_events": source_events,
    }


def run_quality_case(
    case: dict[str, Any],
    argos: str,
    artifact_root: Path,
    timeout: int,
) -> dict[str, Any]:
    prompt = (
        "Benchmark v1 compatibility case. Review only the attached benchmark "
        "brief. Return the required four sections and make concrete, minimal, "
        "testable findings."
    )
    prompt_path = artifact_root / "prompts" / f"{case['case_id']}.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    command = _base_argos_command()
    command.extend(
        [
            "run",
            str(case["mode"]).lstrip("@"),
            "--prompt-file",
            str(prompt_path),
            "--argos",
            argos,
            "--single-ok",
        ]
    )
    command.extend(build_common_context_args(case))
    command.extend(["--artifact-root", str(artifact_root), "--json"])
    result = run_command(
        command,
        timeout=timeout,
        env=prepare_env(artifact_root.parent),
    )
    meta, parse_error = _parse_meta(result)
    status = classify_launch(
        result.exit_code,
        meta,
        result.stderr,
        result.timed_out,
        "oneshot",
        stdout=result.stdout,
        launch_error=result.launch_error,
    )
    content = _content_from_meta(meta, "oneshot")
    score = score_quality(
        case, content, meta, result.duration_sec, result.exit_code
    )
    score["status"] = status
    score["command"] = command
    score["parse_error"] = parse_error
    return score


def run_infra_case(
    case: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    command = _base_argos_command()
    command.extend(
        [
            "benchmark",
            "--artifact-root",
            str(artifact_root),
            "--json",
        ]
    )
    result = run_command(
        command,
        timeout=180,
        env=prepare_env(artifact_root.parent),
    )
    meta, parse_error = _parse_meta(result)
    status = classify_launch(
        result.exit_code,
        meta,
        result.stderr,
        result.timed_out,
        "harness",
        stdout=result.stdout,
        launch_error=result.launch_error,
    )
    score = float(meta.get("normalized_score", 0.0)) / 100.0
    passed = status == "ok" and meta.get("status") == case.get("expected_status")
    return {
        "case_id": case["case_id"],
        "status": "pass" if passed else "fail",
        "score": round(score, 6),
        "internal_status": meta.get("status"),
        "artifact_dir": meta.get("artifact_dir"),
        "wall_duration_sec": result.duration_sec,
        "parse_error": parse_error,
    }


def run_legacy_benchmark(
    manifest: dict[str, Any],
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    if not args.live:
        raise BenchmarkConfigError(
            "v1 manifests make provider calls; pass --live explicitly or use v2 offline"
        )
    argos = (args.argoses or ["minimax"])[0]
    result_dir = (
        Path(args.result_dir).expanduser().resolve()
        if args.result_dir
        else Path(args.artifact_root).expanduser().resolve()
        / f"{utc_stamp()}-v{manifest['version']}-{args.profile}-{argos}"
    )
    result_dir.mkdir(parents=True, exist_ok=False)
    artifact_root = result_dir / "argos-artifacts"
    selected = [
        case
        for case in manifest["cases"]
        if args.profile == "full" or case.get("cheap")
    ]
    quality_rows = [
        run_quality_case(case, argos, artifact_root, args.timeout)
        for case in selected
    ]
    sota_rows = [
        score_sota_case(case) for case in manifest.get("sota_cases", [])
    ]
    infra_rows = [
        run_infra_case(case, artifact_root)
        for case in manifest.get("infra_cases", [])
    ]
    scorer_rows = [
        score_scorer_case(case)
        for case in manifest.get("scorer_cases", [])
    ]
    quality_score = mean_score(quality_rows, "score")
    sota_score = mean_score(sota_rows, "score")
    infra_score = mean_score([*infra_rows, *scorer_rows], "score")
    costs = [
        float(row["cost"])
        for row in quality_rows
        if row.get("cost") is not None
    ]
    latencies = [
        float(row["wall_duration_sec"])
        for row in quality_rows
        if row.get("wall_duration_sec") is not None
    ]
    payload = {
        "benchmark_version": manifest["version"],
        "profile": args.profile,
        "argos": argos,
        "generated_at": utc_now(),
        "manifest": str(Path(args.manifest).resolve()),
        "artifact_root": str(artifact_root),
        "result_dir": str(result_dir),
        "legacy_composite_score": round(
            quality_score * 45 + sota_score * 20 + infra_score * 25 + 10,
            6,
        ),
        "axis_scores": {
            "axis1_quality_45": round(quality_score * 45, 6),
            "axis2_sota_20": round(sota_score * 20, 6),
            "axis3_infra_25": round(infra_score * 25, 6),
            "axis4_telemetry_presence_10": 10.0,
        },
        "quality_cases": quality_rows,
        "sota_cases": sota_rows,
        "infra_cases": infra_rows,
        "scorer_cases": scorer_rows,
        "cost": summarize(costs),
        "latency_sec": summarize(latencies),
        "warning": (
            "Legacy v1 composite retained only for compatibility. Do not compare "
            "it with v2 orthogonal sections."
        ),
    }
    write_json(result_dir / "results.json", payload)
    return payload, 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark Argos harness health, provider readiness, output quality "
            "and performance without conflating the axes."
        )
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_DEFAULTS),
        default="offline",
    )
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument(
        "--track",
        dest="tracks",
        action="append",
        help="harness, replay, isolated or production; repeatable",
    )
    parser.add_argument(
        "--launch",
        dest="launches",
        action="append",
        help=(
            "harness, replay, oneshot, session, council or debate; repeatable"
        ),
    )
    parser.add_argument(
        "--case",
        dest="cases",
        action="append",
        help="case id filter; repeatable",
    )
    parser.add_argument(
        "--argos",
        dest="argoses",
        action="append",
        help="logical argos for the standardized isolated track; repeatable",
    )
    parser.add_argument("--repetitions", type=int)
    parser.add_argument(
        "--live",
        action="store_true",
        help="explicitly allow provider/model calls",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="render the exact plan without processes or output artifacts",
    )
    parser.add_argument("--max-calls", type=int)
    parser.add_argument(
        "--max-wall-seconds",
        "--max-seconds",
        dest="max_wall_seconds",
        type=float,
    )
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--harness-iterations", type=int, default=2)
    parser.add_argument("--config", help="production-route Argos config path")
    parser.add_argument(
        "--artifact-root",
        default=str(ROOT / "benchmarks/results"),
        help="base directory for generated benchmark runs",
    )
    parser.add_argument(
        "--result-dir",
        help="exact result directory; must not already exist",
    )
    parser.add_argument(
        "--compare",
        "--compare-with",
        dest="compare",
        help="v2 results.json or its containing directory",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def cli_main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    manifest_path = Path(args.manifest).expanduser().resolve()
    try:
        manifest = load_json(manifest_path)
        is_v2_manifest = bool(manifest.get("launches")) or int(
            manifest.get("schema_version", 0) or 0
        ) >= RESULT_SCHEMA_VERSION
        if not is_v2_manifest:
            payload, exit_code = run_legacy_benchmark(manifest, args)
        else:
            validation = validate_manifest(
                manifest, manifest_path=manifest_path
            )
            payload, exit_code = execute_benchmark(manifest, args)
            if args.dry_run:
                payload["manifest_validation"] = validation
    except (BenchmarkConfigError, FileNotFoundError, json.JSONDecodeError) as exc:
        error = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "status": "configuration_error",
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(error, ensure_ascii=False, indent=2))
        else:
            print(f"benchmark configuration error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.dry_run:
        print(
            "Argos benchmark dry-run: "
            f"{payload['run_plan']['spec_count']} specs, "
            f"{payload['run_plan']['budgets']['estimated_live_calls']} live calls"
        )
    else:
        print(
            f"Argos benchmark {payload.get('benchmark_version')}: "
            f"status={payload.get('status', 'legacy')} "
            f"results={payload.get('result_dir')}"
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(cli_main())
