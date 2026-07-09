---
name: adv-sota
description: Run advisor SOTA Explorer for source-backed deep web/academic research over a domain or question. Use `advisor sota` / `advisor @sota-explorer` with bounded sources, evidence artifacts, two synthesis models, and a final reviewer.
---

Before running advisor, follow `../../references/advisor-context-contract.md`.

Use SOTA Explorer when the user wants a neutral, current, source-backed view of latest advances in a domain.

Default commands:

```bash
advisor @sota-normal "<domain or question>" --json
advisor @sota-deep "<domain or question>" --json
```

Use normal for a daily bounded pass and deep for a wider source/query budget. Plain `advisor sota` defaults to normal.

Useful options:
- `--profile normal` / `--profile deep` or aliases `@sota-normal` / `@sota-deep`.
- `--source arxiv --source semantic --source openalex` to restrict sources.
- `--source exa --source tavily --source brave` for web/industry search; these require API keys.
- `--since YYYY-MM-DD` to prefer recent publications where supported.
- `--strict-topic` to drop likely off-topic evidence before synthesis/reporting.
- `--high` to use the configured high reviewer.
- `--no-model` for retrieval-only smoke tests without spending model tokens.

Rules:
1. Do not auto-trigger SOTA Explorer; run it only when requested or clearly useful for current/latest research.
2. Treat `evidence.json` as the source of truth. Report citations as evidence IDs such as `[E3]`; verification checks evidence-ID integrity, not full semantic entailment.
3. Use `summary.json` for quick agent consumption: it contains source health, warnings/errors, quality buckets, best sources, cost, and verification status.
4. If keyed providers are unavailable, continue with public sources and explicitly report skipped providers.
5. Do not claim native browsing beyond retrieved evidence; unsupported claims must be marked weak or omitted.
6. Report artifact path, profile/depth, evidence count, skipped/error source events, source-quality caveats, and whether `--high` was used.
