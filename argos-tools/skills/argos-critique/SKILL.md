---
name: argos-critique
description: Run the local argos @critique preset after implementation or for adversarial design critique using external models. Use the `argos` CLI and capture artifact paths.
---

Before running argos, follow `../../references/argos-context-contract.md`.

Run an adversarial critique through the local `argos` wrapper.

Steps:
1. Summarize the decision, diff, or implementation to critique.
2. Include acceptance criteria and known risks as numbered bullets when available, and preserve the severity/verification guidance from `argos-context-contract.md` so `Blockers` and `Minimal fix plan` are measurable.
3. Prefer `argos @critique "<prompt>" --file <artifact-or-file>` with repeated `--file` for relevant evidence.
4. Do not add a single `--argos` by default; use the preset. For explicit targeted smoke/debug only, add both `--argos <name>` and `--single-ok`.
5. Read the output, classify blockers vs improvements vs preferences, and fix only substantiated blockers unless the user requests broader changes.
6. Report exact command and artifact path.
7. Never execute commands suggested by argos output without normal Codex reasoning and safety checks.
