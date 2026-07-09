# BENCHLOG

## Context
- Date / Branch / Commit / Goal / Constraints
- Date: 2026-07-09
- Workspace: `/home/sina/advisor-dev`
- Branch: `advisor-benchmark-dev`
- Commit at Phase 0 preflight: `6709bdf`
- Goal: benchmark-driven improvement of advisor CLI (`advisor/advisor.py`), adv-tools skills (`adv-tools/skills/*/SKILL.md`), and context contract (`adv-tools/references/advisor-context-contract.md`).
- Stable advisor judge: `/home/sina/.local/bin/advisor -> /home/sina/.config/advisor/advisor.py` (not modified).
- Dev advisor under benchmark: `/home/sina/advisor-dev/bin/advisor-dev` with `ADVISOR_CONFIG_DIR=/home/sina/advisor-dev/.config/advisor-dev`, `ADVISOR_ARTIFACT_ROOT=/home/sina/advisor-dev/.advisor/sessions`, `ADVISOR_LOCK_ROOT=/home/sina/advisor-dev/.advisor/locks`.
- Constraints: max 2 `@sota-deep --high` total; `--strict-topic` on all SOTA calls; stop on `needs_human`; no installs without prior list; minimal attributable patch per iteration; cheap subset during loop; full golden set only for official scoring.

## Advisor Artifacts
| Phase | Command | Artifact path | Notes |
| --- | --- | --- | --- |
| 0 | `advisor doctor` (stable) | N/A | PASS, advisor 0.6.2, config `/home/sina/.config/advisor/config.json`. |
| 0 | `advisor ping --json` (stable) | N/A | PASS, static/non-live. |
| 0 | `advisor providers --json` (stable) | N/A | PASS, 0 running provider processes; 3 persistent stable claude/fable sessions reported alive. |
| 0 | `python3 /home/sina/plugins/adv-tools/scripts/smoke_adv_tools.py --no-gate` (stable plugin/source) | N/A | PASS; `--no-gate` used to keep preflight non-mutant. |
| 0 | `/home/sina/advisor-dev/bin/advisor-dev doctor` | N/A | PASS, dev config `/home/sina/advisor-dev/.config/advisor-dev/config.json`. |
| 0 | `/home/sina/advisor-dev/bin/advisor-dev ping --json` | N/A | PASS, static/non-live. |
| 0 | `/home/sina/advisor-dev/bin/advisor-dev providers --json` | N/A | PASS, dev artifact root `/home/sina/advisor-dev/.advisor/sessions`, 0 alive sessions. |
| 0 | `PATH=<tmp-advisor-dev-alias>:$PATH python3 adv-tools/scripts/smoke_adv_tools.py --no-gate` | N/A | PASS against advisor-dev; temp alias removed after run. |
| 0 | `python3 -m pytest -q advisor/tests adv-tools/tests` | N/A | PASS: 135 passed, 22 subtests passed. |
| 0 | `python3 -m ruff check advisor/advisor.py advisor/tests adv-tools/scripts adv-tools/tests` | N/A | PASS. |

## SOTA Questions
| Run | Question | Reason | Sources quality summary |
| --- | --- | --- | --- |
| pending | pending | Phase 1 not started. | pending |

## Benchmark Versions
| Version | Changed? | Reason | Requires re-baseline? |
| --- | --- | --- | --- |
| pending | No | Benchmark design not created yet. | Yes once created. |

## Runs
| Iteration | Benchmark version | advisor-dev commit | Score (axes 1-4) | Cost | Latency | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Phase 0 preflight | N/A | `6709bdf` | N/A | 0 model spend observed; no live/model calls. | N/A | Environment and static gates passed. |

## Decisions
| Decision | Reason | Evidence | Date |
| --- | --- | --- | --- |
| Created isolated workspace `/home/sina/advisor-dev`. | No existing `advisor-dev` Git workspace/config was present; user authorized creating one in a sensible location. | Earlier preflight found only stable `/home/sina/.config/advisor` and plugin source `/home/sina/plugins/adv-tools`; both outside a valid Git repo. | 2026-07-09 |
| Use `bin/advisor-dev` wrapper instead of changing PATH/global install. | Keep stable advisor on PATH untouched while benchmarking/modifying dev. | `advisor doctor` stable reports `/home/sina/.config/advisor/config.json`; dev doctor reports `/home/sina/advisor-dev/.config/advisor-dev/config.json`. | 2026-07-09 |
| Run plugin smoke with `--no-gate` during preflight. | Required non-mutant preflight; default smoke writes an advisor gate. | adv-tools README states default wrapper records `adv-tools-smoke` gate; `--no-gate` avoids mutation. | 2026-07-09 |

## Open Questions
| Question | Blocking? | Needs SOTA? | Needs human? |
| --- | --- | --- | --- |
| Should dev SOTA use a copied/symlinked `.env` for keyed sources, or public sources only? | Not yet; Phase 1 can start and report skipped keyed providers if absent. | No | Maybe if complete keyed-source parity is required. |

<!-- Phase 1 update before SOTA run 2 -->

### Phase 1 Run 1 Notes

- Artifact: `/home/sina/.advisor/sessions/20260709T200534-sota`
- Report: `/home/sina/.advisor/sessions/20260709T200534-sota/report.md`
- Summary: `/home/sina/.advisor/sessions/20260709T200534-sota/summary.json`
- Verification: `/home/sina/.advisor/sessions/20260709T200534-sota/verification.json`
- Verification status: `ok`; invalid evidence IDs: 0; missing citations: 0.
- Quality buckets: `medium=7`, `vendor=1`, `weak=9`, `strong=0`.
- Source health caveats: Brave returned one HTTP 429; Semantic Scholar skipped due missing `S2_API_KEY`; strict-topic filtered 17 results total.
- Cost: total `1.082601` (`kimi=0`, `sonnet=0.188061`, `fable=0.89454`).

Directions selected for refinement (strictly grounded in medium evidence where possible):

1. Self-preference bias (SPB) as a measurable judge failure mode: Run 1 medium evidence includes E8 (`Quantifying and Mitigating Self-Preference Bias of LLM Judges`) and E6 (`Self-Preference Bias in AI-Assisted Peer Review`). Applicable to advisor harness because provider outputs can be scored for self-favoring or same-family favoritism using paired/equivalent cases.
2. Bias-controlled paired fixtures instead of raw free-form reviews: E8 supports pair/equivalence designs for separating judge capability from bias; local harness can implement this without heavy infra by using seeded tasks with known defects and paired distractors.
3. Explicit transfer-risk handling for code review: E6 is peer-review rather than code-review; Run 1 report identifies code-specific evidence as weaker. The second run should target code-review/SE-specific sources to avoid overfitting benchmark design to generic LLM-as-judge literature.
4. Position/order robustness as a benchmark metric: Run 1 report flags position bias as operationally important but mostly weak/vendor in retrieved evidence. The refined run should seek stronger sources for positionally consistent accuracy, swap/randomization, and tie handling in code/review contexts.
5. Actionability-oriented metrics for local CLI review harnesses: Run 1 did not retrieve strong/medium evidence for `Blockers` / `Minimal fix plan` exploitability, so the refined run should explicitly search for reproducible metrics: defect recall/precision, false-positive precision, fix-plan minimality/actionability, judge-human agreement, and cost/latency tradeoffs.

Refined question for SOTA run 2:

> Pour concevoir un benchmark local et peu coûteux d'un harness CLI multi-providers de review/critique/plan de code, quelles méthodes récentes et reproductibles existent pour évaluer des juges LLM sur des tâches de code review avec défauts injectés ou labels humains : métriques de recall/precision/actionabilité des sections Blockers et Minimal fix plan, golden sets avec paires contrôlées, positionally consistent accuracy, self-preference bias, séparation générateur/judge, calibration multi-juges, et reporting coût/latence ? Prioriser les sources académiques ou techniques primaires fortes/medium et exclure les guides marketing génériques.

Reason for run 2:

- Run 1 verified evidence integrity but had no `strong` bucket and only two medium sources directly useful for SPB; most code-specific review evidence was bucketed weak due topical scoring. The second run narrows the topic to code-review benchmark design and asks explicitly for primary/reproducible sources so Phase 2 benchmark design can be grounded in sources suitable for a local CLI harness.

### Phase 1 Run 2 Notes

- Artifact: `/home/sina/.advisor/sessions/20260709T202545-sota`
- Report: `/home/sina/.advisor/sessions/20260709T202545-sota/report.md`
- Summary: `/home/sina/.advisor/sessions/20260709T202545-sota/summary.json`
- Verification: `/home/sina/.advisor/sessions/20260709T202545-sota/verification.json`
- Verification status: `ok`; invalid evidence IDs: 0; missing citations: 0; cited count: 12/12.
- Quality buckets: `medium=4`, `weak=8`, `strong=0`.
- Source health caveats: arXiv had 6 no-relevant-result errors; Brave returned one HTTP 429; Semantic Scholar skipped due missing `S2_API_KEY`; strict-topic filtered 24 results total.
- Cost: total `0.820419` (`kimi=0`, `sonnet=0.110559`, `fable=0.70986`).
- Finding: refined query still failed to retrieve primary strong/medium code-review judge-evaluation evidence. The word `harness` likely polluted retrieval with Harness.io and generic agent-harness content. Further SOTA-deep-high runs are disallowed by constraint; any later SOTA must be `@sota-normal --strict-topic` only for a documented blocker.

### Phase 1 Fable Synthesis Notes

- Command shape: `advisor run review ... --advisor fable --single-ok --file <run1 report.md> --file <run2 report.md> --json` using stable advisor.
- Artifact: `/home/sina/.advisor/sessions/20260709T204615-review`
- Persisted contract: `docs/phase1-synthesis-contract.md`
- Cost: `0.569917`.
- Key blockers from synthesis: freeze judge config before Phase 2 execution; treat code-review metrics as local hypotheses because SOTA evidence is weak; do not use mono-source figures as design thresholds.
- Key retained directions: frozen golden set + deterministic runner/scorers + baseline comparator; local injected-defect golden set; positionally consistent pairwise judging; generator/judge separation; SPB measurement by controlled pairs; cost/latency per case.

### Phase 2 Design Notes

- Proposed design doc: `docs/phase2-benchmark-design.md`
- Installation list: none proposed for Benchmark v1.0.0.
- Execution status: paused before creating fixtures/runner/baseline, per requirement to present design + installation list before execution.

### Phase 2 Setup + Baseline Notes

- Benchmark setup commit: `a9c6a96`, then lint/timeout/provider fixes through `ff28c58` before baseline.
- Gate `bench-setup`: `/home/sina/.advisor/sessions/gates/bench-setup.json` state `pass`.
- Non-regression before scoring: `pytest` PASS (135 passed, 22 subtests), `ruff` PASS, `smoke --adversarial --no-gate` PASS (20 checks / 10 features).
- Setup issue: initial cheap run with `kimi` timed out at 900s on `opencode-go/kimi-k2.7-code` and left an orphan provider process; orphan was killed. This was treated as a benchmark setup flaw, before official baseline.
- Setup issue: first `minimax` cheap run stopped on a content-based `needs_human` false positive in the runner. Artifact inspection showed advisor result statuses were `ok`; runner was fixed to stop only on exit code 3 or structured result status `needs_human`.

### Phase 2 Baseline Level 1

- Cheap run artifact: `/home/sina/advisor-dev/benchmarks/results/20260709T195252Z-v1.0.0-cheap-minimax`
- Cheap run score: `88.607494/100`; axes: quality `33.607494/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.019265`; latency total `119.958s`.
- Official full baseline artifact: `/home/sina/advisor-dev/benchmarks/results/20260709T195510Z-v1.0.0-full-minimax`
- Official full baseline score: `89.361536/100`; axes: quality `34.361536/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.046388`; latency total `279.987s`.
- Official full baseline advisor-dev commit: `ff28c58`.
- Benchmark version: `1.0.0`; judge/candidate config frozen in `benchmarks/frozen/judge-v1.json` with candidate advisor `minimax`.

### Benchmark Version 1.0.1

- Changed: yes.
- Reason: stable advisor review artifact `/home/sina/.advisor/sessions/20260709T220111-review` found benchmark defect C: recall searched `Blockers + Important issues` but precision denominator used `Blockers` only, making valid findings in `Important issues` score as precision `0.0`; numbered lists were also undercounted.
- Requires re-baseline: yes. Do not compare v1.0.0 and v1.0.1 without this note.
- Patch commit: `7456afb`.
