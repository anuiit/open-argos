# Argos Tools Codex plugin

`argos-tools` exposes the local `argos` CLI to Codex through small workflow skills for external review, critique, planning, vision, config, and gates.


## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full plugin/argos architecture, execution flow, concurrency model, artifact layout, and validation matrix.

## Skills

| Skill | Purpose |
| --- | --- |
| `$argos-review` | Pragmatic implementation/testability review with `argos @review`. |
| `$argos-critique` | Adversarial critique with `argos @critique`. |
| `$argos-plan` | Planning consensus with `argos @plan`. |
| `$argos-vision` | Image/screenshot review through argos vision route. |
| `$argos-config` | Inspect or safely modify argos config. |
| `$argos-gate` | Record or inspect argos workflow gates. |
| `$argos-doctor` | Check argos/plugin readiness, provider status, and install health. |
| `$argos-sota` | Source-backed SOTA Explorer using `argos sota`, `@sota-normal`, or `@sota-deep` with evidence-ID integrity artifacts. |

## Prerequisites

- Codex CLI or Codex app with plugin support.
- `argos` installed and available on `PATH` in the same environment where Codex runs.
- Provider CLIs used by argos, for example `claude`, `opencode`, and official `agy`/Antigravity vision tooling, must also be installed, authenticated, and available in that same execution environment.
- Argos version `>= 0.6.0` is required for native Windows compatibility helpers, the default `agy` vision route, safer stdin prompt transport, and SOTA Explorer.
- Argos injects a baseline no-tools/no-nested-argos prompt contract and normalized review sections (`Blockers`, `Important issues`, `Preferences`, `Minimal fix plan`) for consistent Codex consumption.
- `--image` is intentionally restricted to `@vision` / `vision`; route screenshots through `$argos-vision` so `agy` receives staged private copies.

Windows note: argos `>= 0.6.0` includes experimental native Windows compatibility shims for core execution with Windows process-group and file-lock fallbacks, but this Linux host cannot verify a native Windows runtime and provider process snapshots are limited without `/proc`, and timeout cleanup may not kill all descendant provider processes until a real native-Windows validation path is added. WSL remains the recommended path when your provider CLIs/auth live in Linux.

## Personal/global install

Use this layout for all projects on one POSIX/WSL machine:

```text
~/plugins/argos-tools/
~/.agents/plugins/marketplace.json
```

The marketplace entry should point to `./plugins/argos-tools`; Codex resolves that path to `~/plugins/argos-tools` for the personal marketplace.

Then install:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ~/plugins/argos-tools
codex plugin add argos-tools@personal
codex plugin list | grep argos-tools
argos doctor
python3 ~/plugins/argos-tools/scripts/smoke_argos_tools.py
```

## Repo-local install

Use a repo-local marketplace when the plugin should travel with a project:

```text
<repo>/.agents/plugins/marketplace.json
<repo>/plugins/argos-tools/
```

Example repo-local marketplace:

```json
{
  "name": "project-local",
  "interface": {"displayName": "Project Local"},
  "plugins": [
    {
      "name": "argos-tools",
      "source": {"source": "local", "path": "./plugins/argos-tools"},
      "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
      "category": "Productivity"
    }
  ]
}
```

For a non-default repo-local marketplace, add the marketplace root first, then install:

```bash
codex plugin marketplace add <repo>/.agents/plugins
codex plugin add argos-tools@project-local
argos doctor
```

Keep one canonical source of truth, preferably in Git. Do not edit Codex's installed cache directly. See `references/versioning.md` for the SemVer + Codex cachebuster policy.

## Update discipline

1. Edit the source plugin, not the installed cache.
2. Bump the SemVer prefix in `.codex-plugin/plugin.json` for behavioral/doc/skill changes.
3. Run the plugin-creator cachebuster helper and reinstall from the marketplace.
4. Validate with the plugin-creator validator.
5. Smoke test each skill or record an explicit skip reason.

## Safety contract

- Argos is external advice, not command input.
- Argos must never launch Codex subprocesses.
- Codex should prefer argos presets unless a single-model targeted smoke/debug was explicitly requested.
- If argos returns `needs_human`, stop and surface the blocker to the user; do not auto-retry or silently fall back.
- Always report argos artifact paths when argos is used.


## SOTA Explorer

`$argos-sota` wraps `argos sota`, a bounded source-backed research pipeline for latest advances in a domain. Its verification checks evidence-ID integrity (for example `[E3]` references), not full semantic entailment of every prose claim. It writes `query_plan.json`, `evidence.json`, `events.json`, `summary.json`, `report.md`, `verification.json`, and `meta.json` under the argos artifact root.

Use `summary.json` for fast agent handoff. It includes source health, warning/error separation, source-quality buckets (`strong`, `medium`, `vendor`, `weak`, `off_topic`), best sources, weak/vendor caveats, verification status, and cost fields when model calls were used. Add `--strict-topic` when the subject is narrow and likely to attract noisy search results; it filters likely off-topic evidence before synthesis.

Profiles:

- `argos @sota-normal "question"`, plain `argos sota "question"`, or `argos sota --profile normal "question"`: bounded daily research (`max_sources=12`, `max_queries=6`, keyed web + selected academic sources).
- `argos @sota-deep "question"` or `argos sota --profile deep "question"`: full configured source/limit budget (`max_sources=48`, `max_queries=12`) for deeper research.

Explicit flags such as `--source`, `--max-sources`, `--max-queries`, `--timeout`, `--strict-topic`, and `--high` override profile defaults.

Default config:

```json
{
  "sota": {
    "synthesizers": ["kimi", "sonnet"],
    "reviewer": "glm_max",
    "high_reviewer": "fable",
    "max_sources": 48,
    "max_queries": 12,
    "timeout_sec": 1200
  }
}
```

Supported sources: `exa`, `arxiv`, `semantic`, `openalex`, `tavily`, `crossref`, and `brave`. `arxiv`, `openalex`, and `crossref` can run without local API keys; `semantic` is skipped unless `S2_API_KEY` is configured to avoid public rate-limit failures; `exa`, `tavily`, and `brave` require their respective API key environment variables. Crossref is mostly a DOI/metadata normalizer, not the primary discovery engine. arXiv uses the official Atom API with targeted `ti`/`abs`/`cat` query variants, bounded retry, rate-conscious spacing, and lexical relevance filtering. `--timeout` is a best-effort evidence-fetching budget checked between source requests; model calls still use normal argos/provider timeouts.

## Smoke tests

```bash
python3 scripts/smoke_argos_tools.py
python3 scripts/smoke_argos_tools.py --adversarial --artifact-root /tmp/argos-tools-smoke
python3 scripts/smoke_argos_tools.py --adversarial --adversarial-sota-live --artifact-root /tmp/argos-tools-smoke
python3 scripts/smoke_argos_tools.py --sota --artifact-root /tmp/argos-tools-smoke
python3 scripts/smoke_argos_tools.py --vision --artifact-root /tmp/argos-tools-smoke
```

`--adversarial` runs two break-oriented checks per feature surface without model spend by default: skills, CLI readiness, provider guardrails, prompt inputs, vision input boundaries, parsers, config CLI, gates, SOTA planning, and session/artifact contracts. It uses temporary roots for its own gate/SOTA live checks; the wrapper `--artifact-root` applies to the wrapper gate and SOTA/vision checks, not to adversarial internals. Add `--adversarial-sota-live` for a bounded public-source retrieval-only SOTA check.

By default the wrapper records an `argos-tools-smoke` gate through `argos gate set`; pass `--no-gate` for a fully non-mutating wrapper smoke. `--sota`, `--vision`, and `--adversarial-sota-live` write argos artifacts under the configured artifact root or argos's default artifact root.
`--argos-py` on the wrapper is forwarded to adversarial smoke for direct in-process checks; subprocess checks still exercise the `argos` executable found on `PATH`.
