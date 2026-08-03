---
name: argos
description: Route freely among Argos workflows (review, critique, plan, council, research) to match the current user need without forcing a fixed mode.
---

Use this skill when the user did not explicitly ask for review/critique/plan/council/research, and wants a best-fit Argos workflow.

Before running argos, follow `../../references/argos-context-contract.md`.

Rules:

1. Infer the required workflow from the request and call the appropriate one-shot:
   - `argos run review` for implementation/testability checks.
   - `argos run critique` for adversarial risk review.
   - `argos run plan` for sequencing and trade-off planning.
   - `argos start council` for sustained deliberation.
   - `argos research` for evidence-backed external research.
2. Preserve acceptance criteria, constraints, and known risks as numbered bullets when available.
3. Preserve context in one concise prompt unless a prompt file is required for reliability.
4. Report the exact command, the selected workflow, and artifact path to the user.
