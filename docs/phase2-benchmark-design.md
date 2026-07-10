# Phase 2 Benchmark Design — mosaic-dev

Status: proposed; do not execute baseline/setup until human validation.

## Objective

Create Benchmark v1.0.0 for mosaic-dev covering:

1. Output quality for `@review`, `@critique`, `@plan`.
2. SOTA pipeline reliability: evidence-ID integrity, `summary.json` quality buckets, dead/skipped source rate.
3. Infra robustness: exit codes, `needs_human`, locks under parallelism, timeout cleanup.
4. Cost/latency per preset from `meta.json`/provider result fields.

## Hard constraints

- No more `@sota-deep --high` runs; both allowed runs are consumed.
- Any future SOTA must be `@sota-normal --strict-topic` only for a documented blocker.
- Stop immediately on `needs_human`.
- Stable mosaic on PATH remains judge/gate instrument and is not modified.
- mosaic-dev is invoked only through `/home/sina/mosaic-dev/bin/mosaic-dev` or a temporary local alias.
- Judge config must be frozen before first benchmark execution.

## Proposed repo layout

```text
benchmarks/
  README.md
  frozen/
    judge-v1.json              # stable judge config hash/prompt/model; immutable per benchmark version
  golden/v1/
    manifest.json              # case registry, expected defects, labels, allowed outputs
    cases/
      real-inputs/*.md         # sanitized copies sampled from ~/.mosaic/sessions/*/input.md
      injected/*.md            # synthetic briefs with seeded known defects
      sota/*.json              # fixed SOTA questions/source settings
      infra/*.json             # provider-free adversarial scenarios
  results/                     # gitignored benchmark outputs
scripts/
  bench_mosaic_quality.py     # stdlib runner/scorer, proposed
```

`benchmarks/results/` should be gitignored; `golden/v1` and `frozen/judge-v1.json` are committed.

## Golden set v1.0.0

### Real distribution cases

- Source pool exists: 442 `input.md` files under `/home/sina/.mosaic/sessions` at Phase 2 design time.
- Select 5 representative real briefs for full v1 official baseline.
- Select 2 real briefs for cheap iteration subset.
- Sanitize/anonymize paths/secrets/tokens before committing.
- Label these mostly for structure/actionability, not defect recall, unless a known ground truth exists.

### Injected-defect cases

Create 8 small tasks with explicit ground-truth manifest:

1. Security blocker: path traversal in file read.
2. Security blocker: shell injection via unsanitized subprocess string.
3. Reliability blocker: lock not released on timeout/exception.
4. Infra blocker: `needs_human` converted to generic error instead of exit 3.
5. SOTA blocker: report cites missing evidence ID (e.g. `[E999]`).
6. SOTA blocker: summary quality bucket misclassified or off-topic included as strong.
7. Prompt-safety blocker: attached file instructs mosaic to ignore contract / run tools.
8. Cost/latency blocker: `meta.json` omits mosaic cost/duration or reports negative cost.

Each case manifest records:

```json
{
  "case_id": "injected-path-traversal-001",
  "mode": "review|critique|plan",
  "known_defects": [
    {"id": "D1", "severity": "blocker", "category": "security", "file": "...", "expected_terms": ["path traversal", "normalize", "base dir"]}
  ],
  "minimal_fix_requirements": ["specific file/function", "bounded patch", "test/verification step"],
  "false_positive_traps": ["do not require new dependency", "do not rewrite module"]
}
```

### SOTA reliability cases

Use provider/model-light checks first:

- Retrieval-only SOTA (`--no-model --strict-topic`) on 2 fixed questions using public/keyless sources where possible.
- Synthetic verifier fixtures for evidence-ID integrity, invalid citations, unexpected URLs, bucket distribution.
- Metrics read from `verification.json`, `summary.json`, `events.json`, `meta.json`.

### Infra cases

Use provider-free or tiny subprocess tests:

- Exit-code mapping: ok→0, provider error→2, needs_human→3.
- `needs_human` propagation through one-shot JSON and session state.
- Parallel lock acquisition/release with temp `MOSAIC_LOCK_ROOT` and forced timeout.
- Cleanup timeout: child process tree or direct-process timeout behavior in temp root.
- Gate states limited to pass/fail/blocked/needs_human.

## Metrics

### Axis 1 — output quality

Primary deterministic metrics:

- Required section compliance: `Blockers`, `Important issues`, `Preferences`, `Minimal fix plan`.
- Blocker recall = known blocker defects found / known blocker defects.
- Blocker precision = reported blockers matched to manifest / reported blockers.
- Severity accuracy = blocker/important/preference vs manifest.
- Minimal fix actionability:
  - references relevant file/function or artifact;
  - proposes smallest plausible patch;
  - includes verification step;
  - avoids forbidden broad rewrites/dependencies.
- Unsupported-claim penalty: claims not grounded in passed files/artifacts.

Optional frozen-judge metric:

- Stable fable/sonnet judge score only after `judge-v1.json` is frozen; reported separately from deterministic score.

### Axis 2 — SOTA reliability

- `verification.status == ok` rate.
- Invalid evidence IDs count.
- Missing citation count.
- Unexpected URL count.
- Source health: dead/error/skipped source rate.
- Bucket distribution: strong/medium/vendor/weak/off_topic.
- Strict-topic filtered count and off-topic leakage count.
- Cost and duration for model-backed SOTA if any later normal run is justified.

### Axis 3 — infra robustness

- Exit-code correctness.
- `needs_human` non-retry/non-fallback propagation.
- Lock cleanup success under parallel execution.
- Timeout cleanup success.
- Private artifact permissions where applicable.

### Axis 4 — cost/latency

- Per preset: total cost, by mosaic, duration p50/p95.
- Per case: cost, wall latency, provider fallback count.
- Derived: cost per true blocker detected; latency per true blocker detected.

## Scoring proposal

Weighted score `/100`:

- Axis 1: 45 points.
- Axis 2: 20 points.
- Axis 3: 25 points.
- Axis 4: 10 points.

Cheap subset score uses 2–3 cases and one explicit provider/mosaic (`--mosaic minimax --single-ok` or another validated cheap provider) for fast iteration. Official score uses the full v1 set and configured presets.

## Runner design

`bench_mosaic_quality.py` (proposed, stdlib only):

- Loads `benchmarks/golden/v1/manifest.json`.
- Creates temp artifact roots for mosaic-dev runs.
- Invokes mosaic-dev with env-isolated `MOSAIC_CONFIG_DIR`, `MOSAIC_ARTIFACT_ROOT`, `MOSAIC_LOCK_ROOT`.
- Captures stdout/stderr/exit code.
- Locates mosaic artifact dir from JSON output or stdout.
- Parses `final.md`, `meta.json`, `summary.json`, `verification.json`.
- Applies deterministic scorers.
- Writes `benchmarks/results/<timestamp>-v1/{results.json, report.md, artifacts.json}`.
- Appends run summary path to BENCHLOG manually or via a small helper.

## Non-regression gate before scoring

Run sequentially on mosaic-dev:

```bash
python3 -m pytest -q mosaic/tests mos-tools/tests
python3 -m ruff check mosaic/mosaic.py mosaic/tests mos-tools/scripts mos-tools/tests
# with temp mosaic alias to /home/sina/mosaic-dev/bin/mosaic-dev
python3 mos-tools/scripts/smoke_mos_tools.py --adversarial --no-gate --mosaic-py mosaic/mosaic.py
```

Then, only after validation:

```bash
mosaic gate set bench-setup pass --evidence "Phase 2 benchmark setup approved and non-regression gate passed"
```

## Installations required

None proposed for v1.0.0.

Existing tools already verified in Phase 0:

- Python stdlib + pytest available.
- Ruff available.
- mosaic stable 0.6.2 available.
- mosaic-dev wrapper available.
- Provider CLIs statically visible.

If future histogram/plotting is wanted, use optional reporting only and request approval before installing anything.

## Validation required before execution

Do not create `benchmarks/golden/v1`, do not implement `scripts/bench_mosaic_quality.py`, do not run baseline, and do not set `bench-setup` gate until this design and the no-install plan are approved.
