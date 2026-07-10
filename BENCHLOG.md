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
| 1 | `advisor @sota-deep --high --strict-topic <initial question> --json` | `/home/sina/.advisor/sessions/20260709T200534-sota` | Verification ok; cost 1.082601. |
| 1 | `advisor @sota-deep --high --strict-topic <refined question> --json` | `/home/sina/.advisor/sessions/20260709T202545-sota` | Verification ok; cost 0.820419. |
| 1 | `advisor run review --advisor fable --single-ok --file <run1 report> --file <run2 report> --json` | `/home/sina/.advisor/sessions/20260709T204615-review` | Phase 1 synthesis contract. |
| 2 | `advisor gate set bench-setup` | `/home/sina/.advisor/sessions/gates/bench-setup.json` | Gate state pass. |
| 2 | `scripts/bench_advisor_quality.py --profile cheap --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260709T195252Z-v1.0.0-cheap-minimax` | v1.0.0 cheap baseline. |
| 2 | `scripts/bench_advisor_quality.py --profile full --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260709T195510Z-v1.0.0-full-minimax` | v1.0.0 official full baseline. |
| 3-pre | `advisor @review ... --file <v1.0.0 baseline/results/BENCHLOG/code> --json` | `/home/sina/.advisor/sessions/20260709T220111-review` | Stable review found benchmark defect C; no needs_human status. |
| 2 | `scripts/bench_advisor_quality.py --profile full --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260709T201952Z-v1.0.1-full-minimax` | v1.0.1 rebaseline. |
| 3.1 | `scripts/bench_advisor_quality.py --profile cheap --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260709T202839Z-v1.0.1-cheap-minimax` | Iteration 1 cheap score. |
| 3.1 | `scripts/bench_advisor_quality.py --profile full --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260709T203235Z-v1.0.1-full-minimax` | Iteration 1 full score. |
| 3.1 | `advisor @review ... --file <BENCHLOG/results/code/skills> --json` | `/home/sina/.advisor/sessions/20260709T224006-review` | Stable review: status ok, but Kimi/Minimax content says human decision required before next patch. |
| 3.C | `scripts/bench_advisor_quality.py --profile full --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260709T210254Z-v1.0.2-full-minimax` | v1.0.2 full rebaseline. |
| 3.C | `scripts/bench_advisor_quality.py --profile cheap --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260709T210958Z-v1.0.2-cheap-minimax` | Cheap noise run 1. |
| 3.C | `scripts/bench_advisor_quality.py --profile cheap --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260709T211239Z-v1.0.2-cheap-minimax` | Cheap noise run 2. |
| 3.C | `scripts/bench_advisor_quality.py --profile cheap --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260709T211442Z-v1.0.2-cheap-minimax` | Cheap noise run 3. |
| 3.C | `advisor @review ... --file <BENCHLOG/scorer/tests/manifest/results> --json` | `/home/sina/.advisor/sessions/20260709T231845-review` | Stable review: v1.0.2 fix valid; next metric redesign needs human decision. |
| 3.C2 | `scripts/bench_advisor_quality.py --profile cheap --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260710T074935Z-v1.0.3-cheap-minimax` | v1.0.3 cheap score; no false-positive trap hits in this sample. |
| 3.C2 | `scripts/bench_advisor_quality.py --profile full --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260710T075258Z-v1.0.3-full-minimax` | v1.0.3 full score; no false-positive trap hits in this sample. |
| 3.C2 | `advisor @review ... --file <BENCHLOG/scorer/tests/manifest/results> --json` | `/home/sina/.advisor/sessions/20260710T100335-review` | Stable review: no blockers; next issues are C benchmark calibration/tests/full-noise. |
| 3.C3 | `scripts/bench_advisor_quality.py --profile cheap --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260710T082058Z-v1.0.4-cheap-minimax` | v1.0.4 cheap score; all `false_positive_hits=[]`. |
| 3.C3 | `scripts/bench_advisor_quality.py --profile full --advisor minimax --json` | `/home/sina/advisor-dev/benchmarks/results/20260710T082557Z-v1.0.4-full-minimax` | v1.0.4 full score; all `false_positive_hits=[]`. |
| 3.C3 | `advisor @review ... --file <BENCHLOG/scorer/tests/manifest/results> --json` | `/home/sina/.advisor/sessions/20260710T104008-review` | Stable review: no blockers; remaining work C benchmark calibration/measurement hygiene. |

## SOTA Questions
| Run | Question | Reason | Sources quality summary |
| --- | --- | --- | --- |
| 1 | LLM-as-judge/code-review pipeline evaluation: metrics, injected-defect golden sets, self-preference and position bias. | Initial SOTA grounding for benchmark design. | Verification ok; buckets medium=7, vendor=1, weak=9, strong=0; artifact `/home/sina/.advisor/sessions/20260709T200534-sota`. |
| 2 | Refined local low-cost multi-provider CLI code-review benchmark design: recall/precision/actionability, controlled pairs, SPB, generator/judge separation, cost/latency. | Run 1 lacked strong code-review-specific sources; refine toward local reproducible benchmark design. | Verification ok; buckets medium=4, weak=8, strong=0; artifact `/home/sina/.advisor/sessions/20260709T202545-sota`. |

## Benchmark Versions
| Version | Changed? | Reason | Requires re-baseline? |
| --- | --- | --- | --- |
| 1.0.0 | Initial | Phase 2 golden set/scorer/runner. | Baseline created. |
| 1.0.1 | Yes | Fixed benchmark defect C: precision denominator and numbered-list counting. | Yes; v1.0.1 rebaseline done. Do not compare v1.0.0 and v1.0.1 without note. |
| 1.0.2 | Yes | Scorer bugfix C: standalone none markers only count as empty; bullets containing words like `None`/`aucun` are now counted. | Yes; rebaseline required before comparing with v1.0.2. |
| 1.0.3 | Yes | Scorer adds conservative `false_positive_traps` penalty while preserving existing precision formula. | Yes; rebaseline required before comparing with v1.0.3. |
| 1.0.4 | Yes | Scorer calibrates `false_positive_traps` negation handling and covers dependency/rewrite/repo-access trap paths. | Yes; rebaseline required before comparing with v1.0.4. |

## Runs
| Iteration | Benchmark version | advisor-dev commit | Score (axes 1-4) | Cost | Latency | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Phase 0 preflight | N/A | `6709bdf` | N/A | 0 model spend observed; no live/model calls. | N/A | Environment and static gates passed. |
| Phase 2 cheap baseline | 1.0.0 | `ff28c58` | 88.607494 (33.607494/20/25/10) | 0.019265 | 119.958s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260709T195252Z-v1.0.0-cheap-minimax`. |
| Phase 2 full baseline | 1.0.0 | `ff28c58` | 89.361536 (34.361536/20/25/10) | 0.046388 | 279.987s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260709T195510Z-v1.0.0-full-minimax`. |
| Phase 2 v1.0.1 rebaseline | 1.0.1 | `7456afb` | 87.518267 (32.518267/20/25/10) | 0.047724 | 343.772s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260709T201952Z-v1.0.1-full-minimax`. |
| Iteration 1 cheap | 1.0.1 | `c69d0be` | 88.872139 (33.872139/20/25/10) | 0.023539 | 209.760s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260709T202839Z-v1.0.1-cheap-minimax`. |
| Iteration 1 full | 1.0.1 | `c69d0be` | 87.857418 (32.857418/20/25/10) | 0.050098 | 392.562s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260709T203235Z-v1.0.1-full-minimax`; delta vs v1.0.1 rebaseline +0.339151, below likely noise. |
| Benchmark fix rebaseline | 1.0.2 | `9f98f4d` | 89.667993 (34.667993/20/25/10) | 0.055010 | 381.100s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260709T210254Z-v1.0.2-full-minimax`; C scorer fix, not comparable to v1.0.1 without version note. |
| Benchmark fix noise cheap #1 | 1.0.2 | `9f98f4d` | 88.804279 (33.804279/20/25/10) | 0.021340 | 149.202s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260709T210958Z-v1.0.2-cheap-minimax`. |
| Benchmark fix noise cheap #2 | 1.0.2 | `9f98f4d` | 88.367509 (33.367509/20/25/10) | 0.014134 | 118.040s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260709T211239Z-v1.0.2-cheap-minimax`. |
| Benchmark fix noise cheap #3 | 1.0.2 | `9f98f4d` | 88.527142 (33.527142/20/25/10) | 0.022025 | 190.830s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260709T211442Z-v1.0.2-cheap-minimax`. |
| False-positive trap cheap | 1.0.3 | `fdda965` | 88.644997 (33.644997/20/25/10) | 0.023650 | 197.890s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260710T074935Z-v1.0.3-cheap-minimax`; all `false_positive_hits=[]`. |
| False-positive trap full | 1.0.3 | `fdda965` | 88.859475 (33.859475/20/25/10) | 0.055155 | 604.495s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260710T075258Z-v1.0.3-full-minimax`; all `false_positive_hits=[]`; not comparable to v1.0.2 without version note. |
| Trap calibration cheap | 1.0.4 | `3e42c4d` | 89.127136 (34.127136/20/25/10) | 0.024433 | 291.789s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260710T082058Z-v1.0.4-cheap-minimax`; all `false_positive_hits=[]`. |
| Trap calibration full | 1.0.4 | `3e42c4d` | 88.408654 (33.408654/20/25/10) | 0.057371 | 820.466s | Artifact `/home/sina/advisor-dev/benchmarks/results/20260710T082557Z-v1.0.4-full-minimax`; all `false_positive_hits=[]`; not comparable to v1.0.3 without version note. |

## Decisions
| Decision | Reason | Evidence | Date |
| --- | --- | --- | --- |
| Created isolated workspace `/home/sina/advisor-dev`. | No existing `advisor-dev` Git workspace/config was present; user authorized creating one in a sensible location. | Earlier preflight found only stable `/home/sina/.config/advisor` and plugin source `/home/sina/plugins/adv-tools`; both outside a valid Git repo. | 2026-07-09 |
| Use `bin/advisor-dev` wrapper instead of changing PATH/global install. | Keep stable advisor on PATH untouched while benchmarking/modifying dev. | `advisor doctor` stable reports `/home/sina/.config/advisor/config.json`; dev doctor reports `/home/sina/advisor-dev/.config/advisor-dev/config.json`. | 2026-07-09 |
| Run plugin smoke with `--no-gate` during preflight. | Required non-mutant preflight; default smoke writes an advisor gate. | adv-tools README states default wrapper records `adv-tools-smoke` gate; `--no-gate` avoids mutation. | 2026-07-09 |
| Applied Iteration 1 A/B patch to severity + verification contract. | Stable review of v1.0.1 baseline recommended improving Blockers/Minimal fix plan exploitability; patch was low-risk and attributable. | Commit `c69d0be`; gates passed (`pytest`, `ruff`, adversarial smoke). | 2026-07-09 |
| Stop before next patch. | Stable `@review` artifact contains advisor content saying human decision required before proceeding; user constraint says stop on `needs_human`/human blocker. | `/home/sina/.advisor/sessions/20260709T224006-review`; Kimi and Minimax blockers. | 2026-07-09 |
| User selected benchmark/scorer C next. | Resolved prior human choice by selecting option 1. | User reply `1`; v1.0.2 scorer patch commit `9f98f4d`. | 2026-07-09 |
| Stop before metric redesign. | Stable review says precision semantics and false-positive-trap scoring are methodology/product decisions requiring explicit human answer before further scorer patching. | `/home/sina/.advisor/sessions/20260709T231845-review`; Sonnet Blockers and Kimi Minimal fix plan. | 2026-07-09 |

## Open Questions
| Question | Blocking? | Needs SOTA? | Needs human? |
| --- | --- | --- | --- |
| Should dev SOTA use a copied/symlinked `.env` for keyed sources, or public sources only? | Not yet; Phase 1 can start and report skipped keyed providers if absent. | No | Maybe if complete keyed-source parity is required. |
| Before next patch, should we prioritize fixing benchmark scorer C/noise estimation or tune A/B persona/contract for minimax? | Resolved: prioritize C scorer/noise. | No (deep SOTA budget exhausted; no SOTA-normal blocker yet). | User chose option 1 on 2026-07-09. |
| For remaining C work, what precision semantics and false-positive-trap scoring should the benchmark use? | Yes before further scorer metric redesign. | No. | Yes; stable review flagged this as a true human decision. |

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


### Phase 3 Iteration 1 Notes

- Non-regression gate before scoring at commit `c69d0be`: `pytest` PASS (`135 passed, 22 subtests`), `ruff` PASS, `smoke --adversarial --no-gate` PASS (`20 checks / 10 features`).
- Patch commit: `c69d0be` (`advisor: clarify severity and verification contract`). Files changed: `advisor/advisor.py`, `advisor/tests/test_advisor.py`, `adv-tools/references/advisor-context-contract.md`, `adv-tools/skills/adv-review/SKILL.md`, `adv-tools/skills/adv-critique/SKILL.md`, `adv-tools/skills/adv-plan/SKILL.md`.
- Patch classification: A (CLI advisor output contract) + B (adv-tools skills/context contract). No benchmark modification in this iteration.
- Cheap benchmark artifact: `/home/sina/advisor-dev/benchmarks/results/20260709T202839Z-v1.0.1-cheap-minimax`; score `88.872139`; axes quality `33.872139/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.023539`; latency total `209.760s`.
- Official full benchmark artifact: `/home/sina/advisor-dev/benchmarks/results/20260709T203235Z-v1.0.1-full-minimax`; score `87.857418`; axes quality `32.857418/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.050098`; latency total `392.562s`.
- Comparable baseline: v1.0.1 full `/home/sina/advisor-dev/benchmarks/results/20260709T201952Z-v1.0.1-full-minimax`; score `87.518267`; axes quality `32.518267/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.047724`; latency total `343.772s`.
- Delta vs comparable v1.0.1 baseline: `+0.339151` total / `+0.339151` axis1 quality. Treat as not significant until variance/noise is measured.
- Stable advisor review artifact: `/home/sina/.advisor/sessions/20260709T224006-review`; command used stable `/home/sina/.local/bin/advisor` with `@review` on BENCHLOG, baseline/final results, CLI and skill/context files.
- Stable review classification:
  - A: no high-confidence CLI defect beyond possible future persona/prompt tuning; changing minimax persona requires a human/product decision.
  - B: skills/context improved, but future work may require stricter brief structure for acceptance criteria/known risks and cost/latency/provider constraints.
  - C: likely remaining benchmark/scorer issues: matcher and precision denominator may still scan different surfaces for cases with `matched_defects=[D1]` and `reported_issue_bullets=0`; run-to-run noise around `0.34` points; real-case actionability may measure brief construction more than advisor quality.
- Stop condition reached: stable review content from Kimi/Minimax says human decision required before the next patch. No further benchmark modification or A/B patch applied.


### Benchmark Version 1.0.2 Notes

- User decision after Iteration 1 stop: prioritize option 1, benchmark/scorer C and noise estimation.
- Confirmed defect C: `scripts/bench_advisor_quality.py::bullet_count` treated any section containing `(none)`, `none`, or `aucun` as empty. Old full artifacts had valid bullets containing `Aucun E3 visible` and ``None` default`, producing `reported_issue_bullets=0` despite `matched_defects=["D1"]`.
- Patch: count only standalone none markers as empty; count non-none bullet/list items even when the text mentions `None` or `aucun`. Added `tests/test_bench_advisor_quality.py` regression.
- Targeted no-model validation on old v1.0.1 artifacts after patch:
  - `injected-sota-bucket-006`: `reported_issue_bullets=9`, `precision=0.111111`, `score=0.728889` (previous full result had `reported_issue_bullets=0`, `precision=0.0`, `score=0.706667`).
  - `injected-cost-latency-008`: `reported_issue_bullets=9`, `precision=0.111111`, `score=0.822222` (previous full result had `reported_issue_bullets=0`, `precision=0.0`, `score=0.8`).
- Gates before rebaseline: `pytest` PASS (`137 passed, 22 subtests`), `ruff` PASS, `smoke --adversarial --no-gate` PASS (`20 checks / 10 features`).
- Requires rebaseline: yes. Do not compare v1.0.1 and v1.0.2 scores without this note.


### Benchmark Version 1.0.2 Rebaseline + Noise

- Full rebaseline artifact: `/home/sina/advisor-dev/benchmarks/results/20260709T210254Z-v1.0.2-full-minimax`; score `89.667993`; axes quality `34.667993/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.055010`; latency total `381.100s`.
- Cheap noise artifacts:
  1. `/home/sina/advisor-dev/benchmarks/results/20260709T210958Z-v1.0.2-cheap-minimax` — score `88.804279`; cost `0.021340`; latency `149.202s`.
  2. `/home/sina/advisor-dev/benchmarks/results/20260709T211239Z-v1.0.2-cheap-minimax` — score `88.367509`; cost `0.014134`; latency `118.040s`.
  3. `/home/sina/advisor-dev/benchmarks/results/20260709T211442Z-v1.0.2-cheap-minimax` — score `88.527142`; cost `0.022025`; latency `190.830s`.
- Cheap noise summary: mean `88.566310`, sample stdev `0.220956`, min `88.367509`, max `88.804279`, range `0.436770`. Treat future cheap deltas below about `0.44` as noise unless confirmed by repeated runs or full benchmark.
- No `needs_human` occurred in v1.0.2 full or cheap noise runs.


### Stable Review After v1.0.2 C Fix

- Stable review artifact: `/home/sina/.advisor/sessions/20260709T231845-review`; command used stable `/home/sina/.local/bin/advisor @review` with BENCHLOG, scorer, regression tests, manifest, v1.0.2 full report, and 3 cheap reports.
- Review status: all advisors returned `status=ok`; no CLI `needs_human` status.
- Stable review consensus:
  - v1.0.2 `bullet_count` / `is_none_marker` fix is valid and covered by targeted regression tests.
  - Remaining A: none evidenced in reviewed files.
  - Remaining B: none evidenced in reviewed files for this C-fix review.
  - Remaining C: full-profile noise is not measured; current cheap noise range applies only to cheap subset; `false_positive_traps` are present in manifest but not scored; current precision formula treats extra bullets as false positives without validating whether they are actually false.
- Human-decision blocker before further metric redesign: define precision semantics and whether/how to score `false_positive_traps`. No further scorer metric patch applied after this review.


### Benchmark Version 1.0.3 Notes

- User delegated methodology choice: “fais ce qui te semble être le plus pertinent”.
- Decision: preserve existing precision formula as a concision proxy and add explicit `false_positive_traps` scoring because traps already exist in every manifest case but were unused.
- Patch: conservative trap heuristics detect positive recommendations for forbidden dependencies/rewrite/repo-access claims while ignoring negated guidance such as “do not add dependencies” / “without new dependencies”. Penalty is `0.15` per hit, capped at `0.30`, subtracted from quality.
- Tests added/updated in `tests/test_bench_advisor_quality.py` for negated dependency guidance, positive dependency false positive, and penalty cap.
- Gates before rebaseline: `pytest` PASS (`140 passed, 22 subtests`), `ruff` PASS, `smoke --adversarial --no-gate` PASS (`20 checks / 10 features`).
- Requires rebaseline: yes. Do not compare v1.0.2 and v1.0.3 scores without this note.


### Benchmark Version 1.0.3 Rebaseline

- Cheap artifact: `/home/sina/advisor-dev/benchmarks/results/20260710T074935Z-v1.0.3-cheap-minimax`; score `88.644997`; axes quality `33.644997/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.023650`; latency total `197.890s`.
- Full artifact: `/home/sina/advisor-dev/benchmarks/results/20260710T075258Z-v1.0.3-full-minimax`; score `88.859475`; axes quality `33.859475/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.055155`; latency total `604.495s`.
- Observed trap hits: all quality cases had `false_positive_hits=[]`; v1.0.3 therefore adds the measurement channel without penalizing this minimax sample.
- Interpretation: v1.0.3 is a benchmark semantic change and not directly comparable to v1.0.2. The lower full score vs v1.0.2 (`89.667993`) appears dominated by normal model output variance/actionability differences rather than trap penalties.


### Stable Review After v1.0.3 Trap Scoring

- Stable review artifact: `/home/sina/.advisor/sessions/20260710T100335-review`; command used stable `/home/sina/.local/bin/advisor @review` with BENCHLOG, scorer, tests, manifest, and v1.0.3 cheap/full reports.
- Review status: all advisors returned `status=ok`; no CLI `needs_human` status.
- Stable review consensus:
  - Blockers: none.
  - v1.0.3 patch is mechanically valid and preserves existing precision formula.
  - Remaining A: none evidenced.
  - Remaining B: none evidenced.
  - Remaining C: trap tests are asymmetric (dependency only), `not add a dependency` negation is not covered, trap dispatch is brittle to manifest wording, and full-profile noise remains unmeasured.
- Next selected follow-up: minimal C patch for trap regex/test coverage before any broader data-driven trap refactor or full-noise campaign.


### Benchmark Version 1.0.4 Notes

- Follow-up from stable v1.0.3 review artifact `/home/sina/.advisor/sessions/20260710T100335-review`.
- Patch: calibrate trap negation handling for `not add a dependency`, avoid repo-access false positive on “reviewed the attached brief”, and add tests for dependency, broad rewrite, repo-access claim, and full `score_quality` penalty cap path.
- Scope: C benchmark only; no advisor CLI or skills/context changes.
- Gates before rebaseline: `pytest` PASS (`144 passed, 22 subtests`), `ruff` PASS, `smoke --adversarial --no-gate` PASS (`20 checks / 10 features`).
- Requires rebaseline: yes. Do not compare v1.0.3 and v1.0.4 scores without this note.


### Benchmark Version 1.0.4 Rebaseline

- Cheap artifact: `/home/sina/advisor-dev/benchmarks/results/20260710T082058Z-v1.0.4-cheap-minimax`; score `89.127136`; axes quality `34.127136/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.024433`; latency total `291.789s`.
- Full artifact: `/home/sina/advisor-dev/benchmarks/results/20260710T082557Z-v1.0.4-full-minimax`; score `88.408654`; axes quality `33.408654/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.057371`; latency total `820.466s`.
- Observed trap hits: all quality cases had `false_positive_hits=[]`; v1.0.4 changes calibration/test coverage but did not penalize this minimax sample.
- Interpretation: v1.0.4 is a benchmark semantic/test calibration change and not directly comparable to v1.0.3. Full latency was high (`820.466s`), dominated by real-case model time.


### Stable Review After v1.0.4 Trap Calibration

- Stable review artifact: `/home/sina/.advisor/sessions/20260710T104008-review`; command used stable `/home/sina/.local/bin/advisor @review` with BENCHLOG, scorer, tests, manifest, and v1.0.4 cheap/full reports.
- Review status: all advisors returned `status=ok`; no CLI `needs_human` status.
- Stable review consensus:
  - Blockers: none.
  - Remaining A: none evidenced.
  - Remaining B: none evidenced.
  - Remaining C: trap detector still has no positive live hits, manifest wording can silently bypass substring dispatch, repo-access wording coverage can improve, full-profile noise remains unmeasured, and v1.0.4 full latency was high.
- Next selected follow-up: minimal C guard so every manifest `false_positive_traps` entry maps to an explicit scorer route; this is test/scorer hygiene and does not require a new benchmark version unless scoring semantics change.


### Trap Dispatch Guard Notes

- Follow-up from stable v1.0.4 review artifact `/home/sina/.advisor/sessions/20260710T104008-review`.
- Patch: refactor trap dispatch into `false_positive_trap_route()` and add `test_manifest_false_positive_traps_have_known_routes` so future manifest trap wording cannot silently bypass scorer routing.
- Scope: C benchmark/scorer hygiene only. No benchmark version bump and no rebaseline because scoring semantics are unchanged for existing routed traps.
- Gates: `pytest` PASS (`145 passed, 22 subtests`), `ruff` PASS, `smoke --adversarial --no-gate` PASS (`20 checks / 10 features`).


### SOTA Normal Follow-up — Benchmark / Advisor Harness Improvement

- Command: stable `/home/sina/.local/bin/advisor @sota-normal --strict-topic --since 2024-01-01 "LLM-as-judge evaluation for automated code review and external advisor harnesses: measuring defect recall, false positives, actionability of fix plans, judge variance, cost/token-aware model routing, golden sets with injected defects, and benchmark robustness" --json`.
- Artifact: `/home/sina/.advisor/sessions/20260710T125529-sota`; profile `normal`; no `--high`; strict topic enabled.
- Status: syntheses `kimi` and `sonnet` ok; reviewer `glm_max` ok; no `needs_human` status observed. Kimi and GLM used configured fallback from `opencode-go` to `ollama_cloud` after slow paid-code route.
- Verification: `/home/sina/.advisor/sessions/20260710T125529-sota/verification.json` status `ok`; invalid evidence IDs `[]`; missing citations `[]`; uncited evidence `0`.
- Source profile: evidence count `5`; quality counts `medium=4`, `weak=1`; source health has no source errors, but SOTA degraded with `no applied evidence available; using full evidence set`; Brave/Tavily filtered off-topic items under strict topic.
- Cost: total `0.184773` (`sonnet=0.184773`, `kimi=0`, `glm_max=0`); latency was high because Kimi/GLM opencode-go attempts fell back.
- Key findings for benchmark direction:
  - SWR-Bench/SWRench-style design supports balanced clean/defect PRs and point-level TP/FP/FN scoring, but the evidence set does not quantify adversarial false-positive traps or synthetic injection robustness.
  - Actionability of minimal fix plans is an evidence gap; SWR-style `resolve_info` suggests a measurable target, but no source here proves it.
  - Cost-aware model selection is supported as a one-shot aggregate tradeoff; token-aware/adaptive routing is not supported by the evidence.
  - Judge variance is named as an open issue, not measured; any harness benchmark should include cheap repeat/noise checks before trusting deltas.
  - The empirical floor from SWR-style code review is low, so benchmark gates should emphasize absolute recall/precision and false positives, not roadmap optimism.
- Next selected follow-up: benchmark v1.0.5 C patch adding static scorer-case fixtures for trap/actionability calibration so the benchmark verifies its own scoring channels without spending provider tokens or relying on live model randomness.


### Benchmark Version 1.0.5 Notes

- Follow-up from SOTA normal artifact `/home/sina/.advisor/sessions/20260710T125529-sota` and stable v1.0.4 review artifact `/home/sina/.advisor/sessions/20260710T104008-review`.
- Patch: add provider-free static `scorer_cases` to benchmark manifest and runner. These calibrate false-positive trap positive hits, negated trap non-hits, and minimal-fix actionability missing verification/test requirements.
- Scope: C benchmark measurement only; no advisor CLI/skills/context behavior changed.
- Rationale: live minimax runs had `false_positive_hits=[]`, so the scorer channel existed but had no positive benchmark self-test; SOTA also confirmed adversarial FP traps/actionability are evidence gaps worth measuring locally.
- Gates before scoring: initial full gate had `pytest` PASS (`146 passed, 22 subtests`) and `ruff` PASS; first smoke command path was invalid (`scripts/smoke_adv_tools.py` missing), corrected to `python3 adv-tools/scripts/smoke_adv_tools.py --adversarial --no-gate --advisor-py advisor/advisor.py`, which PASSed (`20 checks / 10 features`).
- Static scorer calibration: all 3 new scorer cases PASS; observed trap-positive penalty `0.30`, negated trap penalty `0.0`, missing-test actionability `0.466667`.
- Requires rebaseline: yes. Do not compare v1.0.4 and v1.0.5 without this note.


### Benchmark Version 1.0.5 Cheap Run

- Cheap artifact: `/home/sina/advisor-dev/benchmarks/results/20260710T113022Z-v1.0.5-cheap-minimax`; score `88.207498`; axes quality `33.207498/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.024420`; latency total `222.001s`.
- Advisor artifact paths: quality cases under `/home/sina/advisor-dev/benchmarks/results/20260710T113022Z-v1.0.5-cheap-minimax/advisor-artifacts/`; internal benchmark artifact `/home/sina/advisor-dev/benchmarks/results/20260710T113022Z-v1.0.5-cheap-minimax/advisor-artifacts/20260710T133404-benchmark`.
- Status: no `needs_human`; all SOTA, infra, and scorer calibration cases PASS.
- Observed live trap hits: all live quality cases still `false_positive_hits=[]`; positive-hit coverage now comes from provider-free scorer cases, not from minimax output randomness.
- Interpretation: score movement versus v1.0.4 cheap (`89.127136`) is not directly comparable because benchmark version changed and minimax output variance is present; scorer additions are green and did not consume provider tokens.


### Benchmark Version 1.0.5 Rebaseline

- Full artifact: `/home/sina/advisor-dev/benchmarks/results/20260710T113438Z-v1.0.5-full-minimax`; score `88.074592`; axes quality `33.074592/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.052590`; latency total `458.843s`.
- Advisor artifact paths: quality cases under `/home/sina/advisor-dev/benchmarks/results/20260710T113438Z-v1.0.5-full-minimax/advisor-artifacts/`; internal benchmark artifact `/home/sina/advisor-dev/benchmarks/results/20260710T113438Z-v1.0.5-full-minimax/advisor-artifacts/20260710T134217-benchmark`.
- Status: no `needs_human`; all SOTA, infra, and scorer calibration cases PASS.
- Observed live trap hits: all live quality cases still `false_positive_hits=[]`; static scorer cases verify positive/negated trap behavior and missing-test actionability at zero model cost.
- Interpretation: v1.0.5 is a benchmark measurement change and not directly comparable to v1.0.4. Compared with v1.0.4 full (`88.408654`), the small drop is consistent with minimax output variance; scorer cases are pass-through unless the benchmark scorer regresses.
- Commit: `335c865` (`bench: add scorer calibration cases`).


### Stable Review After v1.0.5 Scorer Calibration

- Stable review artifact: `/home/sina/.advisor/sessions/20260710T134245-review`; command used stable `/home/sina/.local/bin/advisor @review` with BENCHLOG, runner, manifest, tests, and v1.0.5 cheap/full reports.
- Review status: all advisors returned `status=ok`; no CLI `needs_human` status. Kimi used configured fallback from `opencode-go/kimi-k2.7-code` to `ollama_cloud/kimi-k2.7-code` after a slow provider route.
- Cost: sonnet `0.405279`, minimax `0.02725596`, kimi `0`; total observed `0.43253496`.
- Stable review consensus:
  - Remaining A: none evidenced in reviewed files.
  - Remaining B: none evidenced in reviewed files; v1.0.5 did not touch skills/context contract.
  - Remaining C: static scorer cases are mechanically valid and useful in-pipeline, but scorer self-checks are mixed into the infra axis; real-case actionability is degenerate (`0.3` constant) because generic requirements (`section headings`, `actionable steps`, `verification`) are lexical and rarely matched; cost/latency axis remains binary; trap route coverage lacks repo-access negation/paraphrase tests; full-profile noise remains unmeasured.
- Next selected follow-up: C-only v1.0.6 benchmark patch focused on the highest measurement defect: make real-case actionability discriminate structure/content instead of the current lexical floor. Keep scorer/infra split as a report diagnostic if it stays low-risk; defer cost-axis redesign because that is a broader methodology decision.


### Benchmark Version 1.0.6 Notes

- Follow-up from stable review artifact `/home/sina/.advisor/sessions/20260710T134245-review`.
- Patch: replace real-case lexical `minimal_fix_requirements` (`section headings`, `actionable steps`, `verification`) with structural requirements `structured_fix_steps` and `concrete_fix_target`; add scorer support for those requirements and expose `fix_requirement_hits` / `fix_requirement_count` in results.
- Patch: add `axis_diagnostics` to distinguish infra CLI score, scorer self-check score, and combined axis3 score while preserving total scoring weights for now.
- Scope: C benchmark measurement only; no advisor CLI or skills/context behavior changed.
- Gates before scoring: `pytest` PASS (`147 passed, 22 subtests`), `ruff` PASS, `smoke --adversarial --no-gate` PASS (`20 checks / 10 features`).
- Requires rebaseline: yes. Do not compare v1.0.5 and v1.0.6 quality scores without noting the real-case actionability semantic change.


### Benchmark Version 1.0.6 Rebaseline

- Cheap artifact: `/home/sina/advisor-dev/benchmarks/results/20260710T120018Z-v1.0.6-cheap-minimax`; score `94.785004`; axes quality `39.785004/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.025299`; latency total `190.882s`.
- Full artifact: `/home/sina/advisor-dev/benchmarks/results/20260710T120335Z-v1.0.6-full-minimax`; score `93.891208`; axes quality `38.891208/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.042296`; latency total `447.376s`.
- Advisor artifact paths: cheap quality cases under `/home/sina/advisor-dev/benchmarks/results/20260710T120018Z-v1.0.6-cheap-minimax/advisor-artifacts/`; full quality cases under `/home/sina/advisor-dev/benchmarks/results/20260710T120335Z-v1.0.6-full-minimax/advisor-artifacts/`; full internal benchmark artifact `/home/sina/advisor-dev/benchmarks/results/20260710T120335Z-v1.0.6-full-minimax/advisor-artifacts/20260710T141103-benchmark`.
- Status: no `needs_human`; all SOTA, infra, and scorer calibration cases PASS.
- Measurement effect: real cases now score as structured/concrete/actionable when the Minimal fix plan contains multiple steps plus concrete file/function/flag/test targets. In v1.0.6 full all 5 real cases had `actionability=1.0`; in v1.0.5 full all 5 real cases had `actionability=0.3` due to lexical requirements. This is a benchmark calibration improvement, not an advisor-dev output quality jump.
- Axis diagnostics: full `axis3_infra_cli_score=1.0`, `axis3_scorer_selfcheck_score=1.0`, `axis3_infra_combined_score=1.0`.
- Observed live trap hits: all live quality cases still `false_positive_hits=[]`; static scorer cases remain the positive/negated trap coverage.


### Stable Review After v1.0.6 Real-Case Actionability Calibration

- Stable review artifact: `/home/sina/.advisor/sessions/20260710T141133-review`; command used stable `/home/sina/.local/bin/advisor @review` with BENCHLOG, runner, manifest, tests, and v1.0.6 cheap/full reports.
- Review status: all advisors returned `status=ok`; no CLI `needs_human` status. Kimi used configured fallback from `opencode-go/kimi-k2.7-code` to `ollama_cloud/kimi-k2.7-code` after a slow provider route.
- Cost: sonnet `0.364695`, minimax `0.0169422`, kimi `0`; total observed `0.3816372`.
- Stable review consensus:
  - Remaining A: none evidenced.
  - Remaining B: none evidenced.
  - Remaining C: v1.0.6 fixed the old lexical floor but over-corrected: all 5 real cases reached `actionability=1.0` and `score=1.0`, indicating ceiling/saturation. `CONCRETE_FIX_TARGET_RE` is too permissive; `structured_fix_steps` only checks two bullets; no weak/medium negative-control scorer case prevents this inflation. Axis3 diagnostics are useful, but axis1 lacks real-vs-injected/actionability/trap diagnostics.
- Next selected follow-up: immediate C-only v1.0.7 calibration patch: add weak/medium real-actionability scorer controls, tighten `concrete_fix_target`, add axis1 diagnostics, and mark v1.0.6 as a miscalibrated intermediate baseline.


### Benchmark Version 1.0.7 Notes

- Follow-up from stable review artifact `/home/sina/.advisor/sessions/20260710T141133-review`.
- Patch: tighten `concrete_fix_target` so generic backticks or a single target do not satisfy the requirement; require at least two distinct concrete targets (file/flag/test/function-shaped target).
- Patch: add provider-free scorer control `scorer-real-actionability-weak-004`, which has two weak steps and a generic backtick but should score only structural actionability (`0.35`) and not full actionability.
- Patch: extend `axis_diagnostics` with axis1 real/injected quality means, actionability means, real-actionability full-count, and total false-positive-hit count.
- Scope: C benchmark measurement only; no advisor CLI or skills/context behavior changed.
- Gates before scoring: `pytest` PASS (`148 passed, 22 subtests`), `ruff` PASS, `smoke --adversarial --no-gate` PASS (`20 checks / 10 features`).
- Requires rebaseline: yes. v1.0.6 is treated as a miscalibrated intermediate baseline for real-case actionability saturation.


### Benchmark Version 1.0.7 Rebaseline

- Cheap artifact: `/home/sina/advisor-dev/benchmarks/results/20260710T122922Z-v1.0.7-cheap-minimax`; score `94.735000`; axes quality `39.735000/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.023310`; latency total `187.938s`.
- Full artifact: `/home/sina/advisor-dev/benchmarks/results/20260710T123236Z-v1.0.7-full-minimax`; score `92.593952`; axes quality `37.593952/45`, SOTA `20/20`, infra `25/25`, cost/latency `10/10`; cost total `0.050917`; latency total `463.242s`.
- Advisor artifact paths: cheap quality cases under `/home/sina/advisor-dev/benchmarks/results/20260710T122922Z-v1.0.7-cheap-minimax/advisor-artifacts/`; full quality cases under `/home/sina/advisor-dev/benchmarks/results/20260710T123236Z-v1.0.7-full-minimax/advisor-artifacts/`; full internal benchmark artifact `/home/sina/advisor-dev/benchmarks/results/20260710T123236Z-v1.0.7-full-minimax/advisor-artifacts/20260710T144020-benchmark`.
- Status: no `needs_human`; all SOTA, infra, and scorer calibration cases PASS.
- Measurement effect: v1.0.7 no longer saturates all real cases. Full diagnostics: `axis1_real_quality_score=0.9055`, `axis1_injected_quality_score=0.791622`, `axis1_real_actionability_mean=0.79`, `axis1_injected_actionability_mean=0.795833`, `axis1_real_actionability_full_count=2`, `axis1_false_positive_hit_count=0`.
- Scorer control: `scorer-real-actionability-weak-004` PASS with observed `actionability=0.35` and `score=0.7075`, proving weak structured/generic plans no longer receive full actionability.
- Remaining risks: live false-positive trap hits remain zero; full-profile noise still unmeasured beyond single full runs per version; axis4 cost/latency remains binary.
