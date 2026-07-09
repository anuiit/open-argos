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
