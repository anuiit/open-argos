import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bench_advisor_quality.py"
SPEC = importlib.util.spec_from_file_location("bench_advisor_quality", MODULE_PATH)
bench = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bench)


def test_bullet_count_only_treats_standalone_none_markers_as_empty() -> None:
    assert bench.bullet_count("(none)") == 0
    assert bench.bullet_count("- (none)\n- real issue") == 1
    assert bench.bullet_count("- Aucun E3 visible; count is inflated") == 1
    assert bench.bullet_count('- Silent `None` default for `duration_sec` violates contract') == 1


def test_score_quality_precision_counts_bullets_that_mention_none_words() -> None:
    case = {
        "case_id": "injected-cost-latency-008",
        "kind": "injected",
        "mode": "review",
        "known_defects": [
            {
                "id": "D1",
                "expected_terms": ["missing cost", "duration"],
            }
        ],
        "minimal_fix_requirements": ["cost", "duration", "test"],
    }
    content = """## Blockers
- Silent `None` default for `duration_sec` violates cost/duration presence.
- Missing cost is not rejected.
## Important issues
- No type check.
## Preferences
- (none)
## Minimal fix plan
1. Validate cost and duration.
2. Add pytest regression test.
"""
    result = bench.score_quality(case, content, {"results": []}, 0.0, 0)
    assert result["matched_defects"] == ["D1"]
    assert result["reported_issue_bullets"] == 3
    assert result["precision"] == 0.333333


def test_false_positive_traps_ignore_negated_dependency_guidance() -> None:
    assert not bench.false_positive_hit("do not add dependencies unless necessary", "Keep stdlib only; do not add dependencies.")
    assert not bench.false_positive_hit("do not add dependencies unless necessary", "Fix this without new dependencies.")


def test_false_positive_traps_penalize_positive_dependency_recommendations() -> None:
    case = {
        "case_id": "trap-case",
        "kind": "injected",
        "mode": "review",
        "known_defects": [{"id": "D1", "expected_terms": ["path traversal"]}],
        "minimal_fix_requirements": ["test"],
        "false_positive_traps": ["do not add dependencies unless necessary"],
    }
    content = """## Blockers
- Path traversal allows escaping base_dir.
## Important issues
- Add a new dependency to sanitize paths.
## Preferences
- (none)
## Minimal fix plan
1. Add a pytest regression test.
"""
    result = bench.score_quality(case, content, {"results": []}, 0.0, 0)
    assert result["false_positive_hits"] == ["do not add dependencies unless necessary"]
    assert result["false_positive_penalty"] == 0.15
    assert result["score"] == 0.75


def test_false_positive_traps_cap_penalty() -> None:
    hits = ["a", "b", "c"]
    assert bench.false_positive_penalty(hits) == 0.30


def test_false_positive_traps_ignore_not_dependency_guidance() -> None:
    assert not bench.false_positive_hit("do not add dependencies unless necessary", "We should not add a dependency here.")


def test_false_positive_traps_cover_broad_rewrite_path() -> None:
    assert not bench.false_positive_hit("do not propose broad rewrite without evidence", "Do not rewrite the whole module.")
    assert bench.false_positive_hit("do not propose broad rewrite without evidence", "A broad rewrite is the simplest fix.")


def test_false_positive_traps_cover_repo_access_claim_path() -> None:
    assert not bench.false_positive_hit("do not claim access to omitted repository files", "I reviewed the attached brief only.")
    assert bench.false_positive_hit("do not claim access to omitted repository files", "Elsewhere in the repo, this helper already exists.")


def test_score_quality_applies_trap_penalty_cap_through_full_path() -> None:
    case = {
        "case_id": "multi-trap-case",
        "kind": "real",
        "mode": "review",
        "known_defects": [],
        "minimal_fix_requirements": [],
        "false_positive_traps": [
            "do not add dependencies unless necessary",
            "do not propose broad rewrite without evidence",
            "do not claim access to omitted repository files",
        ],
    }
    content = """## Blockers
- Add a new dependency.
- A broad rewrite is required.
- Elsewhere in the repo, a solution exists.
## Important issues
- (none)
## Preferences
- (none)
## Minimal fix plan
1. Install a package.
"""
    result = bench.score_quality(case, content, {"results": []}, 0.0, 0)
    assert len(result["false_positive_hits"]) == 3
    assert result["false_positive_penalty"] == 0.30
    assert result["score"] == 0.70


def test_manifest_false_positive_traps_have_known_routes() -> None:
    manifest = bench.load_json(bench.MANIFEST)
    traps = {
        trap
        for case in manifest["cases"]
        for trap in case.get("false_positive_traps", [])
    }
    assert traps
    unrouted = sorted(trap for trap in traps if bench.false_positive_trap_route(trap) is None)
    assert unrouted == []


def test_static_scorer_cases_pass() -> None:
    manifest = bench.load_json(bench.MANIFEST)
    rows = [bench.score_scorer_case(case) for case in manifest.get("scorer_cases", [])]
    assert rows
    assert {row["status"] for row in rows} == {"pass"}


def test_real_cases_have_case_specific_actionability_anchors() -> None:
    manifest = bench.load_json(bench.MANIFEST)
    generic = {"structured_fix_steps", "concrete_fix_target"}
    real_cases = [case for case in manifest["cases"] if case.get("kind") == "real"]
    assert real_cases
    for case in real_cases:
        requirements = set(case.get("minimal_fix_requirements", []))
        assert requirements - generic, case["case_id"]


def test_real_case_actionability_discriminates_structured_concrete_fix_plan() -> None:
    case = {
        "case_id": "real-actionability",
        "kind": "real",
        "mode": "review",
        "known_defects": [],
        "minimal_fix_requirements": ["structured_fix_steps", "concrete_fix_target"],
    }
    strong = """## Blockers
- (none)
## Important issues
- (none)
## Preferences
- (none)
## Minimal fix plan
1. Update `advisor.py` to validate the status field.
2. Add `test_status_validation` and run pytest.
"""
    weak = """## Blockers
- (none)
## Important issues
- (none)
## Preferences
- (none)
## Minimal fix plan
Fix it later.
"""
    strong_score = bench.score_quality(case, strong, {"results": []}, 0.0, 0)
    weak_score = bench.score_quality(case, weak, {"results": []}, 0.0, 0)
    assert strong_score["actionability"] == 1.0
    assert weak_score["actionability"] == 0.0
    assert strong_score["score"] > weak_score["score"]


def test_concrete_fix_target_rejects_generic_backticks_and_single_target() -> None:
    generic = """1. Investigate the issue.\n2. Run `it` again.\n"""
    one_target = """1. Update `advisor.py`.\n2. Run tests.\n"""
    two_targets = """1. Update `advisor.py`.\n2. Add `test_status_validation`.\n"""
    assert not bench.fix_requirement_hit("concrete_fix_target", generic)
    assert not bench.fix_requirement_hit("concrete_fix_target", one_target)
    assert bench.fix_requirement_hit("concrete_fix_target", two_targets)
