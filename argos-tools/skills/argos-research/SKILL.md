---
name: argos-research
description: Run decision-oriented, source-backed research before committing to technical direction. Use `argos research` with a focused profile when the user asks what is current, which alternatives exist, how something is implemented, or what external evidence supports a choice.
---

Before running argos, follow `../../references/argos-context-contract.md`.

Use this workflow when choices are uncertain, standards evolve quickly, or competing
approaches seem plausible.

Profiles:

- `--profile docs`: documentation-first scan of official docs, changelogs, and upgrade notes.
- `--profile landscape`: broad competitive/market/alternative scan.
- `--profile implementation`: implementation-pattern and integration-focused retrieval.
- `--profile current`: quick current-state check with tighter query budget.
- `--profile evidence`: evidence-priority mode favoring source quality over breadth.
- `--profile deep`: broadest search budget for high-uncertainty decisions.

Command shape:

- `argos research "<question>" --profile <docs|landscape|implementation|current|evidence|deep> --json`
- Historical `argos sota` and `@sota-*` spellings remain compatibility aliases;
  use `argos research` in new instructions and artifacts.

Operational rules:

1. Trigger research whenever a decision-relevant external fact is uncertain,
   unfamiliar, or likely to have changed. Do not wait for the start of a new
   plan: interrupt planning, implementation, or review at the decision point.
2. Preserve acceptance criteria and decision criteria from the user context.
3. Keep queries bounded and scoped; report source caveats explicitly when some providers are missing.
   Argos retrieval is limited to Exa, Tavily, and Brave. Codex native web search
   remains a separate host capability when available and is never launched by Argos.
4. Treat evidence IDs (`[E3]`-style references) as primary provenance and report skipped/error sources.
5. Read `coverage.json` before trusting a model synthesis. If coverage is
   `insufficient`, keep the model skipped unless the user explicitly approves
   `--force-model-on-insufficient`; disclose and preserve that override.
   Treat low mean topical relevance or too few high-relevance results as
   insufficient even when the raw result count is non-zero.
6. Return command + artifact path, and summarize: profile used, top evidence
   signals, alternatives considered, skipped sources, recommendation, and
   confidence caveats.
7. Re-run only when the decision changes, new uncertainty appears, or previous
   evidence is stale or insufficient. Do not repeat an unchanged query.
