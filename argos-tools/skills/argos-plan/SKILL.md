---
name: argos-plan
description: Plan and, when the task requests a change, execute work through an Argos-guided delivery loop. Use for plan-only analysis or phased implementation with recurring research, adversarial plan critique, implementation, 1–3 review/fix rounds per phase, and final multi-pass review. Supports `light`, `medium`, and `high` workflow profiles; default to `medium`.
---

# Argos Plan-Driven Delivery

Read `../../references/argos-context-contract.md` and
`../../references/delivery-profiles.md` before execution.

Default to `medium`. Honor an explicit `light`, `medium`, `high`, or
`plan-only` request. The profile controls workflow intensity, not the provider
model's reasoning-effort setting.

## Delivery loop

1. Inspect the repository, constraints, acceptance criteria, current tests,
   and rollback surface.
2. Maintain an uncertainty list. Run `$argos-research` whenever an unfamiliar
   or changing external fact could materially affect the decision.
3. Produce the initial plan with `argos run plan`. In `high`, obtain a second
   planning perspective with a complementary prompt before reconciling either
   proposal.
4. Add an explicit `uncertainty register` with owner, impact, and verification
   plan.
5. Run an adversarial `argos run critique` against the reconciled plan when required by
   the selected profile. Revise the plan before implementation.
6. If the user asked only for a plan, stop with the revised plan and
   verification strategy.
7. Otherwise implement the plan in bounded phases. Codex performs edits and
   commands; Argos only advises.
8. After each phase, run `argos run review`, fix substantiated findings, and
   repeat within the profile's round budget.
9. Re-run `$argos-research` at phase boundaries when new uncertainty appears.
10. Before closing a phase, run `argos run critique` if the profile asks for
   adversarial verification on unresolved tradeoffs.
11. Run the profile's final complementary reviews for correctness, accuracy,
    architecture, and release/arbitration; apply required fixes, then obtain
    a final heavy arbitrator verdict for the delivery.
12. Conclude only with acceptance criteria verified, tests read, and exact
    Argos artifact paths reported.

Do not repeat identical review prompts. Later rounds must verify fixes,
investigate unresolved risks, or cover a complementary concern.

Escalate only the affected delivery phase from `medium` to `high`, or switch
only the affected research question to the `deep` profile. Announce and record
the reason; do not silently make the whole workflow more expensive.

## Delivery profile contract

- `light`: one plan draft, one critique when risk is concrete, one implementation
  review per phase, and one final review pass.
- `medium`: initial plan + one adversarial critique + one to two review rounds per phase
  + three final review rounds (correctness, architecture, release/arbitration).
- `high`: two planning passes, adversarial plan critique, two review rounds per phase
  + optional third round on important items + three final rounds, with
  arbitrator-heavy final review.
- `plan-only`: stop immediately after revised plan + test plan when implementation is
  explicitly out of scope.

## Command form (use shell-safe aliases only)

- Plan: `argos run plan "<prompt>" --json [--argos <name> ...]`
- Critique: `argos run critique "<prompt>" --file plan.md --json`
- Review: `argos run review "<prompt>" --file plan.md --json`
- Research: `argos research "<question>" --profile <docs|landscape|implementation|current|evidence|deep> --json`

## Artifact and traceability checklist

For every run, report:

- exact command,
- profile used,
- artifact directory,
- blockers addressed,
- remaining risks and follow-up decisions.
