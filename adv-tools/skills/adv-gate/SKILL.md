---
name: adv-gate
description: Record or inspect strict advisor workflow gates with normalized states pass, fail, blocked, or needs_human.
---

Use strict advisor gates. For advisor-backed reviews, follow `../../references/advisor-context-contract.md`.

Commands:
- List gates: `advisor gates` or `advisor gates --json`
- Record a gate: `advisor gate set <gate-id> <pass|fail|blocked|needs_human> --evidence "<evidence>"`

Rules:
1. Do not use N/A, skipped, deferred, or silent pass states.
2. Use `needs_human` when execution requires credentials, a browser target, destructive approval, or an unavailable external state.
3. Include reproducible evidence in every gate update.
