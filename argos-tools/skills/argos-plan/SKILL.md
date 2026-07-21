---
name: argos-plan
description: Run local argos planning consensus for implementation plans when external planning critique is requested. Use `argos @plan` and capture artifact paths.
---

Before running argos, follow `../../references/argos-context-contract.md`.

Use `argos @plan` to get external planning input.

Steps:
1. Provide the brief, constraints, acceptance criteria, and known risks. Preserve acceptance criteria and known risks as numbered bullets when available.
2. Preserve the severity/verification guidance from `argos-context-contract.md` so `Blockers` and `Minimal fix plan` are measurable.
3. Run `argos @plan "<brief>" --file <optional-plan-or-context>`; use `argos config show` if you need the current preset membership.
4. Do not narrow to one `--argos` unless it is an explicit targeted smoke/debug run with `--single-ok`.
5. Integrate only concrete, relevant planning improvements.
6. Report command and artifact path.
