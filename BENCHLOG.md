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
