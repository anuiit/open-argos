# Argos benchmark

The v2 benchmark measures four independent things:

1. deterministic Argos harness health;
2. deterministic scorer calibration on frozen strong and adversarial replays;
3. provider and launcher readiness;
4. quality and performance of successful live outputs.

It deliberately has no global score. A harness pass is not model quality, a
provider failure is not a bad answer, and replay timing is not model latency.

## Corpus

`golden/v2/manifest.json` defines ten realistic cases and thirteen frozen
replays. The live matrix covers:

- one-shot review, planning, research, clean-control, long-context and
  attachment-injection tasks;
- multi-turn correction and persistent-state recovery;
- a bounded two-model debate;
- a persistent Council contribution.

The cases use both individual files and directory-shaped projects. Hidden
concept IDs, critical misses, forbidden claims, clean-case hallucinations,
actionability and required output sections are scored deterministically.
Strong replays must pass their expected thresholds; adversarial replays must be
rejected. This calibration gate runs before any model comparison is trusted.

## Tracks and launch surfaces

| Track | Purpose | Provider calls |
| --- | --- | --- |
| `harness` | Run Argos' internal deterministic benchmark | No |
| `replay` | Calibrate the v2 scorer against frozen outputs | No |
| `isolated` | Give each candidate the same prompt and context contract | Yes |
| `production` | Exercise the configured Argos route as users invoke it | Yes |

The launch surfaces are `harness`, `replay`, `oneshot`, `session`, `debate`
and `council`. Isolated candidates get distinct cohort keys; production routes
are not silently compared with isolated candidates.

## Profiles

| Profile | Repetitions | Live-call cap | Wall cap | Cost cap | Intended use |
| --- | ---: | ---: | ---: | ---: | --- |
| `offline` | 1 | 0 | 180 s | $0 | Harness plus all scorer replays |
| `smoke` | 1 | 1 | 300 s | $0.50 | Offline gates plus one Sonnet one-shot |
| `cheap` | 2 | 32 | 2,400 s | $5 | One-shot and session comparison |
| `full` | 3 | 140 | 14,400 s | $30 | All tracks and launch families |

Live calls are opt-in. Omitting `--live` keeps live specs in the run plan but
disables them. The exact expanded plan can always be inspected without
creating artifacts or starting subprocesses:

```powershell
python scripts\bench_argos_quality.py --profile full --live --dry-run
```

## Recommended runs

Run the provider-free baseline first:

```powershell
python scripts\bench_argos_quality.py --profile offline
```

Measure the harness alone and the scorer alone:

```powershell
python scripts\bench_argos_quality.py --profile offline --track harness --launch harness
python scripts\bench_argos_quality.py --profile offline --track replay --launch replay
```

Run the bounded live smoke only after those pass:

```powershell
python scripts\bench_argos_quality.py --profile smoke --live
```

Filter experiments by track, launch, case or candidate:

```powershell
python scripts\bench_argos_quality.py --profile cheap --live `
  --track isolated --launch oneshot `
  --case review-multifile-security `
  --argos sonnet --argos kimi3
```

Use `--result-dir` for a stable artifact path. A result directory must not
already exist, so a run can never overwrite earlier evidence.

## Results and comparison

Every run writes:

- `run-plan.json`: selected specs, semantic fingerprints and budgets;
- `rows/*.json`: one immutable observation per executed spec;
- `results.json`: machine-readable protocol, axes, cohorts and telemetry;
- `report.md`: human-readable interpretation;
- `prompts/` and Argos artifact directories for live runs.

Successful live answers are grouped by comparable cohort. Each cohort reports
quality score, acceptance rate, concept coverage, precision, wall/provider
latency, cost telemetry coverage and cost/time per accepted finding when the
required telemetry exists. Missing cost telemetry stops later live calls so a
cost cap cannot be claimed without evidence. The runner also checks reported
cost between multi-turn session commands. A one-shot or debate is an atomic
CLI command, so its provider spend cannot be interrupted before that command
returns; profile cost values are admission-control limits, not provider-side
hard caps.

Compare only runs produced under the same corpus, prompt, scorer and isolated
assignment contract:

```powershell
python scripts\bench_argos_quality.py --profile offline `
  --compare benchmarks\results\<baseline>\results.json
```

The runner refuses comparison when the corpus contract, selected matrix,
budgets or repetition shape differs. Live cohort deltas additionally require
the same observed model, provider, effective configuration, assignment and
prompt identity. A `needs_human` outcome is recorded for its spec without
truncating later independent specs. Provider unavailability, bootstrap
failure, timeout, launcher failure, parse error, `needs_human` and unknown
outcome remain readiness states and never receive a quality score.

## Judge lane

`frozen/judge-v2.json` reserves an optional model-judge lane, disabled by
default. Deterministic scoring is the primary benchmark. Judge observations
must remain separate, blinded from candidate identity where possible, and
cannot replace replay calibration or create a global score.

Generated results under `benchmarks/results/` are intentionally gitignored.
