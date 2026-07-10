---
name: mos-plan
description: Run local mosaic planning consensus for implementation plans when external planning critique is requested. Use `mosaic @plan` and capture artifact paths.
---

Before running mosaic, follow `../../references/mosaic-context-contract.md`.

Use `mosaic @plan` to get external planning input.

Steps:
1. Provide the brief, constraints, acceptance criteria, and known risks. Preserve acceptance criteria and known risks as numbered bullets when available.
2. Preserve the severity/verification guidance from `mosaic-context-contract.md` so `Blockers` and `Minimal fix plan` are measurable.
3. Run `mosaic @plan "<brief>" --file <optional-plan-or-context>`; use `mosaic config show` if you need the current preset membership.
4. Do not narrow to one `--mosaic` unless it is an explicit targeted smoke/debug run with `--single-ok`.
5. Integrate only concrete, relevant planning improvements.
6. Report command and artifact path.
