from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "argos_benchmark_v2.py"
SPEC = importlib.util.spec_from_file_location("bench_argos_quality_v2", MODULE_PATH)
bench = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = bench
SPEC.loader.exec_module(bench)


def manifest() -> dict[str, Any]:
    return bench.load_json(bench.MANIFEST)


def parsed_args(*values: str):
    return bench.build_parser().parse_args(list(values))


def command_result(
    command: list[str],
    payload: dict[str, Any],
    *,
    exit_code: int = 0,
    stderr: str = "",
    duration: float = 0.01,
):
    return bench.CommandResult(
        command=command,
        exit_code=exit_code,
        stdout=json.dumps(payload),
        stderr=stderr,
        duration_sec=duration,
    )


def harness_payload() -> dict[str, Any]:
    return {
        "status": "pass",
        "suite": "argos-internal-quality",
        "suite_version": "2.0.0",
        "problem_set_version": "2.0.0",
        "normalized_score": 100.0,
        "score": 9,
        "max_score": 9,
        "surface_counts": {
            "one_shot": 7,
            "multi_turn": 2,
            "harness": 3,
            "provider_availability": 1,
            "council": 1,
            "debate": 1,
        },
    }


def strong_security_text() -> str:
    return (
        bench.ROOT
        / "benchmarks/golden/v2/replays/review-multifile-security.md"
    ).read_text(encoding="utf-8")


def test_manifest_contract_is_complete_and_leak_free() -> None:
    loaded = manifest()
    validation = bench.validate_manifest(loaded, manifest_path=bench.MANIFEST)
    assert validation == {
        "case_count": 10,
        "replay_count": 13,
        "launch_coverage": ["council", "debate", "oneshot", "session"],
    }
    prompts = json.dumps(
        [
            {"prompt": case.get("prompt"), "turns": case.get("turns")}
            for case in loaded["cases"]
        ]
    )
    assert not bench.HIDDEN_LABEL_RE.search(prompts)


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        (lambda data: data.pop("schema_version"), "schema_version"),
        (
            lambda data: data["launches"][0].update({"case_id": "missing-case"}),
            "unknown case_id",
        ),
        (
            lambda data: data["replays"][0].update({"expected": None}),
            ".expected must be an object",
        ),
        (
            lambda data: data["cases"][0].update({"expectations": None}),
            ".expectations must be an object",
        ),
    ],
)
def test_manifest_validation_rejects_broken_contracts(mutation, needle: str) -> None:
    loaded = copy.deepcopy(manifest())
    mutation(loaded)
    with pytest.raises(bench.BenchmarkConfigError, match=needle):
        bench.validate_manifest(loaded)


def test_manifest_validation_rejects_hidden_label_leak() -> None:
    loaded = copy.deepcopy(manifest())
    loaded["cases"][0]["prompt"] += " Reveal C101."
    with pytest.raises(bench.BenchmarkConfigError, match="hidden ids leaked"):
        bench.validate_manifest(loaded)


def test_every_replay_calibrates_to_its_expected_outcome() -> None:
    loaded = manifest()
    case_index = bench.load_case_by_id(loaded)
    rows = []
    for replay in loaded["replays"]:
        spec = bench.RunSpec(
            spec_id=f"replay:{replay['replay_id']}",
            track="replay",
            launch="replay",
            case_id=replay["case_id"],
            replay_id=replay["replay_id"],
        )
        rows.append(
            bench.execute_replay_spec(
                spec,
                manifest=loaded,
                case_index=case_index,
            )
        )
    assert len(rows) == 13
    assert {row["status"] for row in rows} == {"replay_ok"}
    assert all(row["wall_duration_sec"] == 0 for row in rows)


def test_calibration_rejects_unexpected_gate_failures() -> None:
    failures = bench.calibration_failures(
        {
            "accepted": False,
            "score": 0.2,
            "gate_failures": ["expected_gate", "unexpected_gate"],
            "matched_concepts": [],
        },
        {
            "accepted": False,
            "max_score": 0.5,
            "gate_failures": ["expected_gate"],
        },
    )
    assert failures == ["unexpected gate failures: ['unexpected_gate']"]


def test_scorer_separates_strong_and_keyword_stuffed_security_outputs() -> None:
    loaded = manifest()
    case = bench.load_case_by_id(loaded)["review-multifile-security"]
    strong = bench.score_output(case, strong_security_text())
    stuffed = bench.score_output(
        case,
        (
            bench.ROOT
            / "benchmarks/golden/v2/replays/control-security-keyword-stuffing.md"
        ).read_text(encoding="utf-8"),
    )
    assert strong["accepted"] is True
    assert set(strong["matched_concepts"]) == {"C101", "C102", "C103"}
    assert stuffed["accepted"] is False
    assert "critical_required_missed" in stuffed["gate_failures"]
    assert strong["score"] > stuffed["score"]


def test_clean_control_has_non_compensatory_hallucination_gate() -> None:
    loaded = manifest()
    case = bench.load_case_by_id(loaded)["review-clean-control"]
    clean = bench.score_output(
        case,
        (
            bench.ROOT / "benchmarks/golden/v2/replays/review-clean-control.md"
        ).read_text(encoding="utf-8"),
    )
    hallucinated = bench.score_output(
        case,
        (
            bench.ROOT
            / "benchmarks/golden/v2/replays/control-clean-hallucination.md"
        ).read_text(encoding="utf-8"),
    )
    assert clean["accepted"] is True
    assert clean["reported_issue_count"] == 0
    assert hallucinated["accepted"] is False
    assert "clean_case_hallucination" in hallucinated["gate_failures"]


def test_default_offline_plan_contains_only_enabled_provider_free_work() -> None:
    plan = bench.build_run_plan(manifest(), parsed_args())
    assert plan["profile"] == "offline"
    assert plan["spec_count"] == 14
    assert plan["budgets"]["estimated_live_calls"] == 0
    assert all(spec["enabled"] for spec in plan["specs"])
    assert not any(spec["requires_live"] for spec in plan["specs"])


def test_non_live_cheap_plan_disables_every_provider_spec() -> None:
    args = parsed_args("--profile", "cheap")
    plan = bench.build_run_plan(manifest(), args)
    live_specs = [spec for spec in plan["specs"] if spec["requires_live"]]
    assert live_specs
    assert all(spec["enabled"] is False for spec in live_specs)
    assert plan["budgets"]["estimated_live_calls"] == 0


def test_smoke_plan_is_exactly_one_bounded_live_call() -> None:
    args = parsed_args("--profile", "smoke", "--live")
    plan = bench.build_run_plan(manifest(), args)
    live_specs = [
        spec
        for spec in plan["specs"]
        if spec["requires_live"] and spec["enabled"]
    ]
    assert len(live_specs) == 1
    assert live_specs[0]["argoses"] == ["sonnet"]
    assert live_specs[0]["launch"] == "oneshot"
    assert plan["budgets"]["estimated_live_calls"] == 1


def test_isolated_candidates_have_distinct_model_cohorts() -> None:
    args = parsed_args(
        "--profile",
        "cheap",
        "--live",
        "--track",
        "isolated",
        "--launch",
        "oneshot",
        "--case",
        "review-multifile-security",
        "--argos",
        "sonnet",
        "--argos",
        "kimi3",
        "--repetitions",
        "1",
    )
    plan = bench.build_run_plan(manifest(), args)
    specs = [spec for spec in plan["specs"] if spec["requires_live"]]
    assert [spec["argoses"] for spec in specs] == [["sonnet"], ["kimi3"]]
    assert len({spec["cohort_key"] for spec in specs}) == 2


def test_full_plan_covers_all_launch_families_within_budgets() -> None:
    plan = bench.build_run_plan(
        manifest(),
        parsed_args("--profile", "full", "--live"),
    )
    assert {spec["launch"] for spec in plan["specs"]} == {
        "harness",
        "replay",
        "oneshot",
        "session",
        "council",
        "debate",
    }
    assert plan["budgets"]["estimated_live_calls"] <= plan["budgets"]["max_calls"]
    assert (
        plan["budgets"]["estimated_live_cost_usd"]
        <= plan["budgets"]["max_cost_usd"]
    )


def test_live_plan_over_budget_is_rejected_before_execution() -> None:
    args = parsed_args(
        "--profile",
        "smoke",
        "--live",
        "--max-calls",
        "0",
    )
    with pytest.raises(bench.BenchmarkConfigError, match="exceed --max-calls"):
        bench.build_run_plan(manifest(), args)


def test_dry_run_calls_no_subprocess_and_writes_no_result_dir(tmp_path: Path) -> None:
    result_dir = tmp_path / "must-not-exist"
    args = parsed_args(
        "--profile",
        "smoke",
        "--live",
        "--dry-run",
        "--result-dir",
        str(result_dir),
    )

    def forbidden_runner(*_args, **_kwargs):
        raise AssertionError("dry-run launched a subprocess")

    payload, exit_code = bench.execute_benchmark(
        manifest(),
        args,
        command_runner=forbidden_runner,
    )
    assert exit_code == 0
    assert payload["command"] == "dry-run"
    assert not result_dir.exists()


def test_oneshot_command_uses_python_prompt_file_directory_and_isolation(
    tmp_path: Path,
) -> None:
    loaded = manifest()
    case = bench.load_case_by_id(loaded)["review-multifile-security"]
    spec = bench.RunSpec(
        spec_id="isolated-security",
        track="isolated",
        launch="oneshot",
        case_id=case["case_id"],
        argoses=("sonnet",),
    )
    command = bench._build_oneshot_command(
        spec,
        case,
        result_dir=tmp_path,
        artifact_root=tmp_path / "artifacts",
        config_path=tmp_path / "config.json",
    )
    assert command[:4] == [
        bench.sys.executable,
        str(bench.ARGOS_PY),
        "--config",
        str(tmp_path / "config.json"),
    ]
    assert command[4:6] == ["run", "review"]
    assert "--prompt-file" in command
    assert "--dir" in command
    assert "--argos" in command
    assert "--single-ok" in command
    assert command[-1] == "--json"


def test_session_builders_start_then_ask_with_same_session(tmp_path: Path) -> None:
    loaded = manifest()
    case = bench.load_case_by_id(loaded)["session-correction"]
    spec = bench.RunSpec(
        spec_id="session-correction",
        track="isolated",
        launch="session",
        case_id=case["case_id"],
        argoses=("minimax",),
    )
    start = bench._build_start_command(
        spec,
        case,
        result_dir=tmp_path,
        artifact_root=tmp_path / "artifacts",
        config_path=None,
    )
    ask = bench._build_ask_command(
        spec,
        case,
        turn=bench._turn_prompts(case)[1],
        turn_number=2,
        session_id="adv_123",
        result_dir=tmp_path,
        artifact_root=tmp_path / "artifacts",
        config_path=None,
    )
    assert start[2:4] == ["start", "review"]
    assert ask[2:4] == ["ask", "adv_123"]
    assert "--prompt-file" in start and "--prompt-file" in ask
    assert "--file" in start and "--file" in ask


def test_debate_builder_is_bounded_and_has_moderator(tmp_path: Path) -> None:
    loaded = manifest()
    case = bench.load_case_by_id(loaded)["plan-technology-choice"]
    spec = bench.RunSpec(
        spec_id="plan-debate",
        track="production",
        launch="debate",
        case_id=case["case_id"],
        argoses=("fable", "kimi3"),
    )
    command = bench._build_debate_command(
        spec,
        case,
        result_dir=tmp_path,
        artifact_root=tmp_path / "artifacts",
        config_path=None,
    )
    assert command[2:4] == ["debate", "plan"]
    assert command[command.index("--rounds") + 1] == "2"
    assert command[command.index("--share-chars") + 1] == "8000"
    assert command[command.index("--total-share-chars") + 1] == "24000"
    assert command[command.index("--moderator") + 1] == "fable"


def test_fake_runner_smoke_scores_live_output_and_separates_axes(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "smoke"
    seen_envs: list[dict[str, str]] = []

    def fake_runner(command, *, cwd, timeout, env):
        del cwd, timeout
        seen_envs.append(env)
        if "benchmark" in command:
            return command_result(command, harness_payload(), duration=0.2)
        return command_result(
            command,
            {
                "status": "ok",
                "results": [
                    {
                        "status": "ok",
                        "content": strong_security_text(),
                        "duration_sec": 1.25,
                        "cost": 0.01,
                        "provider": "fake",
                        "model": "fake-model",
                        "assignment": {"hash": "assignment"},
                        "prompt_manifest": {"final_hash": "prompt"},
                    }
                ],
            },
            duration=1.5,
        )

    args = parsed_args(
        "--profile",
        "smoke",
        "--live",
        "--result-dir",
        str(result_dir),
    )
    payload, exit_code = bench.execute_benchmark(
        manifest(),
        args,
        command_runner=fake_runner,
    )
    assert exit_code == 0
    assert payload["status"] == "pass"
    assert payload["harness"]["status"] == "pass"
    assert payload["scorer_calibration"]["status"] == "pass"
    assert payload["readiness"]["successful_count"] == 1
    assert payload["quality"]["live_answer_count"] == 1
    assert len(payload["quality"]["cohorts"]) == 1
    assert len(payload["performance"]["cohorts"]) == 1
    assert all(
        Path(env["ARGOS_CONFIG_DIR"]).is_relative_to(result_dir)
        and Path(env["ARGOS_ARTIFACT_ROOT"]).is_relative_to(result_dir)
        and Path(env["ARGOS_LOCK_ROOT"]).is_relative_to(result_dir)
        for env in seen_envs
    )
    assert (result_dir / "results.json").is_file()
    assert "no global model score" in (result_dir / "report.md").read_text(
        encoding="utf-8"
    )


def test_provider_bootstrap_failure_is_readiness_not_quality(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "failed-smoke"

    def fake_runner(command, *, cwd, timeout, env):
        del cwd, timeout, env
        if "benchmark" in command:
            return command_result(command, harness_payload())
        return bench.CommandResult(
            command=command,
            exit_code=1,
            stdout="",
            stderr="EEXIST opencode bootstrap",
            duration_sec=0.05,
        )

    payload, exit_code = bench.execute_benchmark(
        manifest(),
        parsed_args(
            "--profile",
            "smoke",
            "--live",
            "--result-dir",
            str(result_dir),
        ),
        command_runner=fake_runner,
    )
    live_row = next(
        row for row in payload["rows"] if row["track"] in bench.LIVE_TRACKS
    )
    assert exit_code == 0
    assert payload["status"] == "degraded"
    assert live_row["status"] == "provider_bootstrap_failed"
    assert live_row["quality"] is None
    assert payload["quality"]["live_answer_count"] == 0
    assert payload["performance"]["cohorts"] == {}


def test_needs_human_is_local_to_one_spec_and_does_not_truncate_matrix(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "needs-human"
    call_count = 0

    def fake_runner(command, *, cwd, timeout, env):
        nonlocal call_count
        del cwd, timeout, env
        call_count += 1
        if call_count == 1:
            return command_result(
                command,
                {"status": "needs_human"},
                exit_code=3,
                stderr="needs_human",
            )
        return command_result(
            command,
            {
                "status": "ok",
                "results": [
                    {
                        "status": "ok",
                        "content": strong_security_text(),
                        "duration_sec": 0.1,
                        "cost": 0.01,
                        "provider": "fake",
                        "model": "fake-model",
                    }
                ],
            },
        )

    payload, exit_code = bench.execute_benchmark(
        manifest(),
        parsed_args(
            "--profile",
            "cheap",
            "--live",
            "--track",
            "isolated",
            "--launch",
            "oneshot",
            "--case",
            "review-multifile-security",
            "--case",
            "review-clean-control",
            "--argos",
            "fake",
            "--repetitions",
            "1",
            "--max-calls",
            "2",
            "--max-cost-usd",
            "10",
            "--result-dir",
            str(result_dir),
        ),
        command_runner=fake_runner,
    )
    assert call_count == 2
    assert exit_code == 3
    assert payload["status"] == "degraded"
    assert [row["status"] for row in payload["rows"]] == [
        "needs_human",
        "ok",
    ]


def test_session_cost_cap_stops_before_later_turn(tmp_path: Path) -> None:
    result_dir = tmp_path / "session-budget"
    call_count = 0

    def fake_runner(command, *, cwd, timeout, env):
        nonlocal call_count
        del cwd, timeout, env
        call_count += 1
        return command_result(
            command,
            {
                "status": "ok",
                "session_id": "session-1",
                "results": [
                    {
                        "status": "ok",
                        "content": strong_security_text(),
                        "duration_sec": 0.1,
                        "cost": 0.31,
                        "provider": "fake",
                        "model": "fake-model",
                    }
                ],
            },
        )

    payload, exit_code = bench.execute_benchmark(
        manifest(),
        parsed_args(
            "--profile",
            "cheap",
            "--live",
            "--track",
            "isolated",
            "--launch",
            "session",
            "--case",
            "session-correction",
            "--argos",
            "fake",
            "--repetitions",
            "1",
            "--max-calls",
            "2",
            "--max-cost-usd",
            "0.31",
            "--result-dir",
            str(result_dir),
        ),
        command_runner=fake_runner,
    )
    assert call_count == 1
    assert exit_code == 0
    assert payload["status"] == "degraded"
    assert payload["rows"][0]["status"] == "budget_exhausted"
    assert payload["rows"][0]["cost_usd"] == 0.31


def test_missing_cost_stops_subsequent_live_calls(tmp_path: Path) -> None:
    result_dir = tmp_path / "cost-stop"
    call_count = 0

    def fake_runner(command, *, cwd, timeout, env):
        nonlocal call_count
        del cwd, timeout, env
        call_count += 1
        return command_result(
            command,
            {
                "status": "ok",
                "results": [
                    {
                        "status": "ok",
                        "content": strong_security_text(),
                        "duration_sec": 0.1,
                        "provider": "fake",
                        "model": "fake",
                    }
                ],
            },
        )

    args = parsed_args(
        "--profile",
        "cheap",
        "--live",
        "--track",
        "isolated",
        "--launch",
        "oneshot",
        "--case",
        "review-multifile-security",
        "--case",
        "review-clean-control",
        "--argos",
        "fake",
        "--repetitions",
        "1",
        "--max-calls",
        "2",
        "--max-cost-usd",
        "10",
        "--result-dir",
        str(result_dir),
    )
    payload, _ = bench.execute_benchmark(
        manifest(),
        args,
        command_runner=fake_runner,
    )
    assert call_count == 1
    assert [row["status"] for row in payload["rows"]] == [
        "ok",
        "budget_skipped",
    ]
    assert payload["budget_observed"]["missing_cost_seen"] is True


def test_budget_telemetry_failure_stops_repeated_live_specs(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "session-cost-stop"
    call_count = 0

    def fake_runner(command, *, cwd, timeout, env):
        nonlocal call_count
        del cwd, timeout, env
        call_count += 1
        return command_result(
            command,
            {
                "status": "ok",
                "session_id": f"fake-session-{call_count}",
                "content": "Started without cost telemetry.",
                "provider": "fake",
                "model": "fake",
            },
        )

    args = parsed_args(
        "--profile",
        "cheap",
        "--live",
        "--track",
        "isolated",
        "--launch",
        "session",
        "--case",
        "session-correction",
        "--argos",
        "fake",
        "--repetitions",
        "2",
        "--max-calls",
        "4",
        "--max-cost-usd",
        "10",
        "--result-dir",
        str(result_dir),
    )
    payload, _ = bench.execute_benchmark(
        manifest(),
        args,
        command_runner=fake_runner,
    )
    assert call_count == 1
    assert [row["status"] for row in payload["rows"]] == [
        "budget_telemetry_missing",
        "budget_skipped",
    ]
    assert payload["budget_observed"]["missing_cost_seen"] is True


def test_harness_only_and_replay_only_are_valid_partial_benchmarks() -> None:
    harness = bench.build_summaries(
        [{"track": "harness", "status": "ok", "wall_duration_sec": 1.0}]
    )
    replay = bench.build_summaries(
        [{"track": "replay", "status": "replay_ok", "wall_duration_sec": 0.0}]
    )
    assert harness["harness"]["status"] == "pass"
    assert harness["scorer_calibration"]["status"] == "not_run"
    assert bench._result_status(harness, live_requested=False) == "pass"
    assert replay["harness"]["status"] == "not_run"
    assert replay["scorer_calibration"]["status"] == "pass"
    assert bench._result_status(replay, live_requested=False) == "pass"


def test_comparison_refuses_contract_changes_and_accepts_matching_contracts() -> None:
    current = {
        "protocol": {"contract": {"contract_sha256": "same"}},
        "run_plan": {"comparison_selection_sha256": "same-selection"},
        "harness": {
            "rows": [
                {
                    "status": "ok",
                    "wall_duration_sec": 1.0,
                    "harness": {
                        "suite_version": "2",
                        "problem_set_version": "2",
                        "max_score": 9,
                    },
                }
            ]
        },
        "quality": {"cohorts": {}},
    }
    baseline = copy.deepcopy(current)
    compatible = bench.compare_benchmark_results(current, baseline)
    assert compatible["comparable"] is True
    baseline["protocol"]["contract"]["contract_sha256"] = "different"
    incompatible = bench.compare_benchmark_results(current, baseline)
    assert incompatible["comparable"] is False
    assert incompatible["cohorts"] == {}


def test_comparison_refuses_different_run_selection() -> None:
    current = {
        "protocol": {"contract": {"contract_sha256": "same"}},
        "run_plan": {"comparison_selection_sha256": "selection-a"},
    }
    baseline = copy.deepcopy(current)
    baseline["run_plan"]["comparison_selection_sha256"] = "selection-b"
    comparison = bench.compare_benchmark_results(current, baseline)
    assert comparison["comparable"] is False
    assert comparison["status"] == "incompatible"
    assert "selection" in " ".join(comparison["reasons"])


def test_comparison_refuses_live_cohort_when_observed_model_differs() -> None:
    identity = {
        "models": ["model-a"],
        "providers": ["provider"],
        "effective_config_sha256": ["config"],
        "assignment_hashes": ["assignment"],
        "prompt_hashes": ["prompt"],
    }
    baseline = {
        "protocol": {"contract": {"contract_sha256": "same"}},
        "run_plan": {"comparison_selection_sha256": "same-selection"},
        "quality": {
            "cohorts": {
                "shared": {
                    "observation_identity": identity,
                    "score": {"mean": 0.7},
                    "acceptance_rate": 1.0,
                }
            }
        },
        "performance": {"cohorts": {}},
    }
    current = copy.deepcopy(baseline)
    current["quality"]["cohorts"]["shared"]["observation_identity"][
        "models"
    ] = ["model-b"]
    current["quality"]["cohorts"]["shared"]["score"]["mean"] = 0.9
    comparison = bench.compare_benchmark_results(current, baseline)
    assert comparison["comparable"] is False
    assert comparison["status"] == "no_overlap"
    assert comparison["quality_cohorts"]["shared"]["comparable"] is False
    assert comparison["quality_cohorts"]["shared"]["score_mean_delta"] is None


def test_performance_keeps_successful_unscored_council_output() -> None:
    summaries = bench.build_summaries(
        [
            {
                "track": "production",
                "launch": "council",
                "case_id": "council-retention",
                "argoses": ["fable", "kimi3"],
                "cohort_key": "council-cohort",
                "status": "ok",
                "quality": None,
                "wall_duration_sec": 3.0,
                "provider_duration_sec": 2.5,
                "cost_usd": 0.04,
            }
        ]
    )
    performance = summaries["performance"]["cohorts"]["council-cohort"]
    assert performance["sample_count"] == 1
    assert performance["quality_sample_count"] == 0
    assert performance["wall_latency_sec"]["mean"] == 3.0
    assert performance["cost_usd"]["mean"] == 0.04
    assert performance["cost_per_accepted_finding_usd"] is None


def test_comparison_reports_harness_and_performance_deltas() -> None:
    contract = {"contract_sha256": "same"}
    baseline = {
        "protocol": {"contract": contract},
        "run_plan": {"comparison_selection_sha256": "same-selection"},
        "harness": {
            "rows": [
                {
                    "status": "ok",
                    "wall_duration_sec": 2.0,
                    "harness": {
                        "suite_version": "2",
                        "problem_set_version": "2",
                        "max_score": 9,
                    },
                },
            ]
        },
        "quality": {"cohorts": {}},
        "performance": {
            "cohorts": {
                "shared": {
                    "observation_identity": {
                        "models": ["model"],
                        "providers": ["provider"],
                        "effective_config_sha256": ["config"],
                        "assignment_hashes": ["assignment"],
                        "prompt_hashes": ["prompt"],
                    },
                    "wall_latency_sec": {"mean": 5.0},
                    "provider_duration_sec": {"mean": 4.0},
                    "cost_usd": {"mean": 0.10},
                    "cost_telemetry_coverage": 1.0,
                }
            }
        },
    }
    current = copy.deepcopy(baseline)
    current["harness"]["rows"][0]["wall_duration_sec"] = 1.5
    current["performance"]["cohorts"]["shared"].update(
        {
            "wall_latency_sec": {"mean": 4.0},
            "provider_duration_sec": {"mean": 3.5},
            "cost_usd": {"mean": 0.08},
        }
    )
    comparison = bench.compare_benchmark_results(current, baseline)
    assert comparison["harness"]["wall_latency_mean_delta_sec"] == -0.5
    assert comparison["overlapping_performance_cohort_count"] == 1
    assert (
        comparison["performance_cohorts"]["shared"][
            "wall_latency_mean_delta_sec"
        ]
        == -1.0
    )
    assert (
        comparison["performance_cohorts"]["shared"]["cost_mean_delta_usd"]
        == -0.02
    )


def test_comparison_omits_cost_delta_when_telemetry_is_incomplete() -> None:
    baseline = {
        "protocol": {"contract": {"contract_sha256": "same"}},
        "run_plan": {"comparison_selection_sha256": "same-selection"},
        "quality": {"cohorts": {}},
        "performance": {
            "cohorts": {
                "shared": {
                    "observation_identity": {
                        "models": ["model"],
                        "providers": ["provider"],
                        "effective_config_sha256": ["config"],
                        "assignment_hashes": ["assignment"],
                        "prompt_hashes": ["prompt"],
                    },
                    "wall_latency_sec": {"mean": 5.0},
                    "provider_duration_sec": {"mean": None},
                    "cost_usd": {"mean": 0.10},
                    "cost_telemetry_coverage": 0.5,
                }
            }
        },
    }
    current = copy.deepcopy(baseline)
    current["performance"]["cohorts"]["shared"]["cost_usd"]["mean"] = 0.08
    comparison = bench.compare_benchmark_results(current, baseline)
    performance = comparison["performance_cohorts"]["shared"]
    assert performance["cost_mean_delta_usd"] is None
    assert "incomplete" in performance["cost_delta_omission_reason"]


def test_windows_tree_kill_falls_back_when_taskkill_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 1234

        def __init__(self) -> None:
            self.killed = False

        def poll(self):
            return None

        def kill(self) -> None:
            self.killed = True

    process = FakeProcess()
    monkeypatch.setattr(bench.os, "name", "nt")
    monkeypatch.setattr(
        bench.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    bench._kill_process_tree(process)
    assert process.killed is True


def test_timeout_reason_takes_precedence_over_secondary_parse_error() -> None:
    result = bench.CommandResult(
        command=["argos"],
        exit_code=124,
        stdout="",
        stderr="",
        duration_sec=12.5,
        timed_out=True,
    )
    reason = bench._classified_reason(
        "timeout",
        result,
        {},
        "stdout did not contain a JSON object",
    )
    assert reason == "command timed out after 12.500s"


@pytest.mark.parametrize(
    ("exit_code", "stderr", "timed_out", "persistent", "expected"),
    [
        (1, "ConnectionRefused", False, False, "provider_unavailable"),
        (1, "EEXIST opencode", False, False, "provider_bootstrap_failed"),
        (3, "needs_human", False, False, "needs_human"),
        (124, "", True, False, "timeout"),
        (124, "", True, True, "outcome_unknown"),
        (127, "", False, False, "launcher_failed"),
    ],
)
def test_failure_taxonomy(
    exit_code: int,
    stderr: str,
    timed_out: bool,
    persistent: bool,
    expected: str,
) -> None:
    assert (
        bench.classify_launch(
            exit_code,
            {},
            stderr,
            timed_out,
            "oneshot",
            persistent=persistent,
        )
        == expected
    )
