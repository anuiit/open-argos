---
name: adv-plan
description: Run local advisor planning consensus for implementation plans when external planning critique is requested. Use `advisor @plan` and capture artifact paths.
---

Before running advisor, follow `../../references/advisor-context-contract.md`.

Use `advisor @plan` to get external planning input.

Steps:
1. Provide the brief, constraints, acceptance criteria, and known risks.
2. Run `advisor @plan "<brief>" --file <optional-plan-or-context>`; use `advisor config show` if you need the current preset membership.
3. Do not narrow to one `--advisor` unless it is an explicit targeted smoke/debug run with `--single-ok`.
4. Integrate only concrete, relevant planning improvements.
5. Report command and artifact path.
