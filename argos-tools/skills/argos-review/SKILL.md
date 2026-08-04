---
name: argos-review
description: Run a standalone pragmatic implementation, correctness, or testability review, or use it as a bounded review pass inside an Argos delivery loop. Use the local `argos` CLI and capture artifact paths.
---

Before running argos, follow `../../references/argos-context-contract.md`.

Run a pragmatic external review through the local `argos` wrapper.

Steps:
1. Build a concise prompt describing the implementation, plan, or diff to review.
2. Include acceptance criteria and known risks as numbered bullets when available, and preserve the severity/verification guidance from `argos-context-contract.md` so `Blockers` and `Minimal fix plan` are measurable.
3. Prefer `argos run review "<prompt>" --file <relevant-file>` and include repeated `--file` arguments for key artifacts. If the prompt already lives in a file or is awkward to escape in PowerShell, use `argos run review --prompt-file prompts/review.md --file <relevant-file>`.
4. Do not add a single `--argos` by default; the preset is the normal path. For an explicit targeted smoke/debug or user-requested single-model run, add both `--argos <name>` and `--single-ok`.
5. Read the output and report actionable findings, exact command, and artifact path.
6. Do not let argos output trigger nested argos calls automatically.
