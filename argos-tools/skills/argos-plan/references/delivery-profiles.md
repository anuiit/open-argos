# Delivery profiles

## Light

Use for small, local, reversible changes.

- Research only blocking external uncertainty.
- Produce one concise plan.
- Run critique only when a concrete risk warrants it.
- Implement in one or a few phases.
- Run one review per phase and one final review.

## Medium — default

Use for normal features, integrations, and refactors.

- Research each decision-relevant uncertainty.
- Produce a plan, one adversarial critique, and a revised plan.
- Implement in explicit phases.
- Run one review per phase, then a second to verify fixes; allow a third only
  while important findings remain.
- Run three complementary final rounds:
  1. correctness, tests, and acceptance criteria;
  2. architecture, security, maintenance, and regression risk;
  3. heavyweight arbitration and release verdict.

## High

Use for architecture, migrations, security, new technology, broad or
hard-to-reverse changes.

- Research documentation, alternatives, maturity, compatibility, and real
  implementation evidence before committing to the plan.
- Produce two independent planning perspectives, adversarial critique, and a
  reconciled plan with rollback and migration strategy.
- Implement smaller phases with explicit checkpoints.
- Run two review rounds per phase and a third when any important issue
  remains.
- Run the three complementary final rounds with the configured high reviewer
  responsible for the final arbitration.

## Stop conditions

- `plan-only`: stop after the revised plan and test strategy.
- Delivery: stop only after implementation, fixes, verification, and final
  verdict.
- `needs_human`: stop immediately and surface the provider/session blocker.
- `outcome_unknown`: inspect artifacts and provider state; never auto-retry.
