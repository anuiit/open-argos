---
name: mos-gate
description: Record or inspect strict mosaic workflow gates with normalized states pass, fail, blocked, or needs_human.
---

Use strict mosaic gates. For mosaic-backed reviews, follow `../../references/mosaic-context-contract.md`.

Commands:
- List gates: `mosaic gates` or `mosaic gates --json`
- Record a gate: `mosaic gate set <gate-id> <pass|fail|blocked|needs_human> --evidence "<evidence>"`

Rules:
1. Do not use N/A, skipped, deferred, or silent pass states.
2. Use `needs_human` when execution requires credentials, a browser target, destructive approval, or an unavailable external state.
3. Include reproducible evidence in every gate update.
