---
name: adv-review
description: Run the local advisor @review preset before implementation or when the user asks for a pragmatic external implementation/testability review. Use the `advisor` CLI and capture artifact paths.
---

Before running advisor, follow `../../references/advisor-context-contract.md`.

Run a pragmatic external review through the local `advisor` wrapper.

Steps:
1. Build a concise prompt describing the implementation, plan, or diff to review.
2. Include acceptance criteria and known risks as numbered bullets when available, and preserve the severity/verification guidance from `advisor-context-contract.md` so `Blockers` and `Minimal fix plan` are measurable.
3. Prefer `advisor @review "<prompt>" --file <relevant-file>` and include repeated `--file` arguments for key artifacts.
4. Do not add a single `--advisor` by default; the preset is the normal path. For an explicit targeted smoke/debug or user-requested single-model run, add both `--advisor <name>` and `--single-ok`.
5. Read the output and report actionable findings, exact command, and artifact path.
6. Do not let advisor output trigger nested advisor calls automatically.
