# Argos delivery profiles

## Light

For small, local, low-risk work:

- Research only blocking external uncertainty.
- Produce one concise plan.
- Run critique only when risk is concrete.
- Implement in one or few phases.
- Run one review per phase and one final review pass.

## Medium (default)

For normal features/integration/refactors:

- Research each decision-relevant uncertainty.
- Build an initial plan, then run an adversarial critique and reconcile results.
- Implement in explicit phases.
- Run one review per phase and a second pass if fixes remain unresolved.
- Run three final passes: correctness/tests, architecture/maintenance, then final arbitration.

## High

For architecture, migrations, security, new technology, or broad/hard-to-reverse changes:

- Research documentation, alternatives, maturity, compatibility, and operational evidence before commitment.
- Run two planning passes, one adversarial critique, then produce a reconciled plan.
- Implement smaller phases with explicit checkpoints.
- Run two review rounds per phase; a third is allowed for critical unresolved issues.
- Run the three final passes and close with a high-cost arbitrator verdict.

## Stop conditions

- `plan-only`: stop after revised plan + verification strategy.
- `needs_human`: stop immediately and report blocker.
- `outcome_unknown`: inspect provider/artifact state; never auto-retry.
