# Pre-1.0 release status

Snapshot: 2026-08-05
Candidate: `0.9.1-rc1` (`0.9.1rc1` in Python metadata)
Branch: `main`

## Current verdict

The repository now produces a coherent local release candidate. Runtime,
package, documentation, context-egress, and deterministic MCP gates pass on the
current native Windows host. It is **not yet a public tag**: first remote CI,
clean WSL/Windows host registration, and a bounded live provider smoke remain
release gates.

Latest evidence:

- `416 passed, 6 skipped, 58 subtests passed` with the base environment;
- MCP SDK lane: `48 passed, 2 skipped` with `mcp==2.0.0`;
- Ruff, byte-compilation, PowerShell installer parsing, and `git diff --check`
  pass;
- wheel and sdist build as `open_argos-0.9.1rc1`;
- archive verification rejects tests, benchmarks, plugin sources, internal
  histories, and local agent state from the Python distribution;
- a fresh venv installs the wheel with `--no-deps`, reports
  `argos 0.9.1-rc1`, and imports the MCP launcher without the SDK installed;
- a fresh isolated MCP runtime installs, verifies `mcp==2.0.0`, and reports
  ready while using a runtime-local writable uv cache.

## Git state and integration

The branch remains a linear release series ahead of `main`/`origin/main`, with
no commit divergence at the audited snapshot:

| Commit | Scope | RC disposition |
| --- | --- | --- |
| `fa7ad85` | Fail-closed providers, context, sessions | Code/test ready; bounded live provider smoke remains. |
| `ffe904a` | MCP bridge and runtime | Code/test ready; clean Codex + Claude Code registration remains. |
| `fd4b755` | Focused plugin surface | Migration routes and changelog now documented; current plugin candidate is `0.5.3-rc.1`. |
| `9fe3060` | Benchmark v2 harness/corpus | Keep as quality infrastructure; distribution verifier excludes it from wheel/sdist. |
| `bb40b51` | Long OpenCode event abort | Ready with focused regression coverage. |
| `46b1a21` | Installable pre-1.0 candidate | Locally verified; remote and clean-host gates remain. |

The technical release preparation is committed. The MIT metadata completes the
local licensing gate. Merge through a reviewed pull request and do not tag the
feature branch.

## What the RC now includes

### Reliability

- absolute provider deadlines include concurrency waits;
- external subprocesses and uv bootstrap are bounded;
- timeout/unknown-outcome paths avoid unsafe automatic retry;
- Windows process trees and cross-process locks are cleaned up;
- unwritable config/artifact/lock roots fail before provider calls or partial
  sessions are created;
- corrupt `session.json`, `background.json`, and metadata JSON return stable
  CLI errors instead of decoder tracebacks;
- long/fragmented OpenCode output retains early abort behavior;
- the generated Windows shim preserves caller-provided `ARGOS_*` roots.

### Installation and MCP

- setuptools wheel/sdist with a single core version source;
- `argos`, `python -m argos`, and `argos-mcp` entrypoints;
- dependency-free core CLI plus isolated pinned MCP runtime;
- one canonical MCP guide for Codex and Claude Code on Windows and Linux/WSL;
- update, rollback, unregister, and uninstall instructions;
- CI matrix plus tag-driven GitHub release workflow, checksums, and
  clean-install smoke.

### Public surface

- English canonical README and French quick-start;
- changelog, security reporting, contributing, compatibility, branching, and
  showcase/A-B protocol documents;
- deprecated plugin skills mapped to current routes;
- stale unrelated `ETAT_DES_LIEUX-20260721.md` removed;
- obsolete post-rename migration/promotion/mirror scripts removed;
- MIT license declared in source and Python package metadata;
- personal installation paths removed from primary user instructions.

### Minimal context egress

Three scopes are deliberately separate:

1. The Git repository retains frozen benchmark inputs for reproducibility.
2. The Python package excludes benchmarks, results, tests, internal notes,
   migration helpers, and developer state.
3. Provider context uses the smallest task-relevant set; directory expansion
   excludes `benchmarks/`, `.omc/`, secrets, binaries, VCS state, dependencies,
   caches, and Argos state. An individual non-secret file remains explicit
   opt-in through `--file`.

Every run retains an `inputs_report` with included/skipped paths and limits.

## Remaining gates for the public RC

### Blocking

- [ ] The pull request runs the new GitHub Actions matrix successfully.
- [ ] A clean native Windows install completes `pipx install .` or
  `uv tool install .`, `argos doctor`, `argos-mcp --prepare`, and one host
  `argos_health` call.
- [ ] A clean WSL/Linux install completes the same flow.
- [ ] At least one configured provider completes a bounded live smoke; any
  unavailable provider is recorded explicitly rather than silently skipped.
- [ ] `main` branch protection requires CI before merge.

### Non-blocking for GitHub-only `0.9.1-rc1`

- PyPI publication is not enabled. The `open-argos` endpoint returned 404
  during preparation, but availability must be rechecked immediately before a
  future registry publish.
- Provider-owned state directories (for example `~/.kimi-code`) cannot be
  relocated by `ARGOS_*`; the clean-host smoke must validate them and document
  provider-specific overrides.
- The comparative showcase protocol is ready, but no "better than Codex"
  metric is claimed until the frozen A/B runs are executed.

## Branch model

Use protected, releasable `main` plus short-lived `feat/*`, `fix/*`, and
`codex/*` branches. A temporary `release/<version>` branch is acceptable only
for a real stabilization window. Do not add a permanent `dev` branch yet: the
current team size and promotion scripts do not justify a second integration
truth.

## Language and compatibility

English is canonical for CLI/help/errors, schema fields, MCP names, skill
invocations, and normative docs. French guides translate explanations and
commands without translating protocol identifiers.

Before 1.0, changes to documented CLI/config/MCP/artifact/plugin contracts must
carry a changelog entry and migration path. At 1.0 those surfaces become stable
and removals require a deprecation period or a major release, except for urgent
security fixes.

## 1.0 exit criteria

- supported Windows, WSL/Linux, Codex, and Claude Code matrix passes on clean
  machines;
- install, update, rollback, and uninstall are automated and tested;
- trusted registry publication/provenance is in place;
- compatibility, deprecation, support, and security promises are public;
- two or three external beta users install and complete a real workflow without
  maintainer intervention;
- no unresolved hang, duplicate unknown-outcome retry, orphan process, lock
  leak, or corrupted-state traceback remains;
- the Codex-only versus Codex+Argos showcase is reproducible and includes
  failures, time, cost, raw sanitized artifacts, and limitations.
