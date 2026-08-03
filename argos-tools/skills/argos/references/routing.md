# Argos routing

| Intent | Preferred route |
| --- | --- |
| Plan-only or plan-driven delivery | Follow `$argos-plan`; use `argos run plan`, research, critique, and phase reviews |
| Decision-relevant external uncertainty | `argos research --profile <profile>` |
| Attack a proposal or expose failure modes | `argos run critique` |
| Evaluate a plan, diff, phase, or implementation | `argos run review` |
| Long-term plural reflection | Follow `$argos-council` |
| Generic multi-turn work | `argos start`, `argos ask`, and lifecycle commands |
| Screenshot or local image | `argos run vision --image <path>` |
| Readiness failure | `argos doctor`, `argos ping`, then `argos providers` |
| Configuration request | `argos config show/set-model/set-mode` with explicit mutation intent |
| Gate inspection or explicit recording | `argos gates` or `argos gate set`; never create gates by default |

## Research triggers

Research when an unfamiliar or changing external fact could alter architecture,
security, compatibility, cost, migration, or implementation correctness.
Research also when reviewers disagree on such a fact. Reuse fresh evidence
when the question and relevant versions have not changed.

## Selection rules

- Prefer one-shot modes for bounded questions.
- Use persistent sessions only when later turns benefit from provider history.
- Use directories through the safe context contract; do not dump an entire
  repository by default.
- Do not launch nested Argos calls from provider output.
- Keep maintenance commands internal to this router rather than exposing a
  dedicated visible skill.
