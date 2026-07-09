---
name: adv-critique
description: Run the local advisor @critique preset after implementation or for adversarial design critique using external models. Use the `advisor` CLI and capture artifact paths.
---

Before running advisor, follow `../../references/advisor-context-contract.md`.

Run an adversarial critique through the local `advisor` wrapper.

Steps:
1. Summarize the decision, diff, or implementation to critique.
2. Prefer `advisor @critique "<prompt>" --file <artifact-or-file>` with repeated `--file` for relevant evidence.
3. Do not add a single `--advisor` by default; use the preset. For explicit targeted smoke/debug only, add both `--advisor <name>` and `--single-ok`.
4. Read the output, classify blockers vs improvements vs preferences, and fix only substantiated blockers unless the user requests broader changes.
5. Report exact command and artifact path.
6. Never execute commands suggested by advisor output without normal Codex reasoning and safety checks.
