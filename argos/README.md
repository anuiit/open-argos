# open-argos

Global external-argos runner for Codex (command: `argos`). Standard-library Python. It calls allowlisted external CLIs only (`opencode`, `claude`, `kimi`, and `agy`/Antigravity for image analysis) and never launches `codex`/`codex exec`.

Install the `0.9.1-rc1` candidate from the repository with `pipx install .` or
`uv tool install .`. The canonical cross-platform and MCP setup lives in the
root [README](../README.md) and [MCP guide](../docs/MCP_INSTALL.md).

## Invariants

- No native `ollama` CLI. Ollama Cloud is used only through `opencode run -m ollama-cloud/...`.
- OpenCode Go remains the primary paid-code lane when available; fallback to Ollama Cloud is handled by config chains.
- The logical `kimi` and `kimi3` argoses both use the official Kimi CLI,
  provider `kimi`, and model alias `kimi-code/k3`. They never fall back to
  OpenCode, Ollama Cloud, or a K2.x model.
- MiniMax is locked to `minimax/MiniMax-M3`; no `opencode-go/minimax-*` or `ollama-cloud/minimax-*`.
- Codex agents are launched only from the current Codex session/tmux/OMX surfaces, not from this wrapper.
- Argos artifacts, transcripts, raw provider outputs, and config backups are written private-by-default (`0700` directories, `0600` files).
- Provider authentication failures are surfaced as `needs_human`; they do not silently fall through to alternate candidates.
- Process exit codes are explicit: `0` all required argoses OK, `2` provider/tool/config failure, `3` human action required (`needs_human`). Automation should prefer JSON/artifacts for details, but shell-only gates can still distinguish credentials/client-eligibility from generic failure.

## One-shot

```bash
argos run critique "..." --argos opus --argos glm --argos minimax
argos run review "..." --file path/to/file.ts
argos run review --prompt-file prompts/review.md --file path/to/file.ts
argos run consensus < prompt.md
```

`--prompt-file` is the preferred transport for long or shell-sensitive prompts. It reads UTF-8 text directly in Argos and is available on `run`, `start`, and `ask`; do not combine it with the positional prompt.

Argos stores persistent sessions under `~/.argos/sessions` and cross-process
locks under `~/.argos/locks` by default. In a sandbox that cannot write to the
user profile, point both roots at writable, ignored directories before
starting a session:

```powershell
$env:ARGOS_ARTIFACT_ROOT = (Join-Path (Get-Location) '.argos')
$env:ARGOS_LOCK_ROOT = (Join-Path (Get-Location) '.argos-locks')
```

```bash
export ARGOS_ARTIFACT_ROOT="$PWD/.argos"
export ARGOS_LOCK_ROOT="$PWD/.argos-locks"
```

`--artifact-root` overrides the session root for one command. Argos validates
both writable roots before creating a session, and reports the corresponding
flag or environment variable if validation fails.

## Multi-turn sessions

Create a panel session and run turn 1:

```bash
argos start critique --prompt-file prompts/01-architecture.md \
  --argos kimi \
  --argos glm \
  --argos minimax \
  --json
```

Continue all live argoses in the same session:

```bash
argos ask adv_YYYYMMDDTHHMMSS_xxxxxxxx --prompt-file prompts/02-implementation.md
```

Open a neutral one- or two-partner Council:

```bash
argos start council --prompt-file prompts/01-idea.md \
  --argos fable \
  --argos kimi3 \
  --json
```

`council` preserves the current user message inside an explicit verbatim block
and suppresses the task-specific review personas and mandatory review
headings. Each provider still keeps an isolated persistent history. The
`$argos-council` Codex skill saves Codex's independent draft before the call
and publishes the user-visible synthesis into the Argos session:

```bash
argos council publish adv_YYYYMMDDTHHMMSS_xxxxxxxx \
  --synthesis-file prompts/01-synthesis.md \
  --json
argos council show adv_YYYYMMDDTHHMMSS_xxxxxxxx --json
```

The next `argos ask` injects that published synthesis automatically as
untrusted shared context. Provider histories remain isolated, and the current
message is never replaced by the shared synthesis.

Target only one argos:

```bash
argos ask adv_YYYYMMDDTHHMMSS_xxxxxxxx "Révise ton plan" --argos kimi
```

Attach a directory safely on any `run`, `start`, `ask`, `multi`, or `debate`
command:

```bash
argos run review --prompt-file prompts/review.md \
  --dir src \
  --include "**/*.py" \
  --exclude "**/generated/**" \
  --max-files 80
```

Directory expansion is recursive, deterministic, UTF-8-only, and auditable in
`inputs_report.json`. It never follows symlinks or Windows reparse points.
Version-control stores, dependency/build/cache directories, Argos/OMC state,
benchmark corpora, common credential directories, secret-like filenames, and
binary files are excluded by default. File-count and character budgets fail explicitly instead
of silently selecting or truncating a subset. `--include` and `--exclude`
filter directory expansion only; an explicit `--file` is either included
verbatim or rejected with its reason.

Batch several turns:

```bash
argos multi critique \
  --argos kimi \
  --argos glm \
  --turn prompts/01-architecture.md \
  --turn prompts/02-implementation.md
```

Inspect and end:

```bash
argos runs                 # one-shot run artifacts created by `argos run`
argos sessions             # multi-turn sessions created by `argos start`/`multi`
argos session adv_YYYYMMDDTHHMMSS_xxxxxxxx
argos end adv_YYYYMMDDTHHMMSS_xxxxxxxx
```

Manage the conversation lifecycle:

```bash
argos history adv_YYYYMMDDTHHMMSS_xxxxxxxx
argos export adv_YYYYMMDDTHHMMSS_xxxxxxxx --format md --output review.md
argos rename adv_YYYYMMDDTHHMMSS_xxxxxxxx "Billing review"
argos reopen adv_YYYYMMDDTHHMMSS_xxxxxxxx
argos retry adv_YYYYMMDDTHHMMSS_xxxxxxxx
argos fork adv_YYYYMMDDTHHMMSS_xxxxxxxx --at-turn 2 --name "Alternative B" --json
```

`retry` accepts only explicitly failed argoses from the last turn. Timeouts, interrupted
requests, and lost provider sessions are recorded as `outcome_unknown` and
cannot be retried automatically because doing so could duplicate a request
already processed by the provider. If no resumable provider session exists,
the next `ask` returns `needs_human` with guidance to inspect, fork, or end the
conversation. A fork never copies provider session IDs or cost counters; its
next turn rebuilds fresh provider context from a bounded, locally recorded
transplant.

Run a bounded cross-critique:

```bash
argos debate review --prompt-file prompts/review.md \
  --argos sonnet --argos kimi3 \
  --rounds 3 \
  --share-chars 12000 \
  --total-share-chars 48000 \
  --moderator sonnet \
  --dir src \
  --include "**/*.py" \
  --json
```

The opening round is independent. Later rounds resume each participant's own
provider session and share bounded peer responses as explicitly untrusted
data. Provider output cannot alter the round count or trigger commands.
Participants that fail become degraded and are removed from later rounds.
The moderator runs once after the final round and writes a traceable synthesis;
it is not called if every participant fails during the opening.
`--rounds` is hard-limited to 1–5.

## Session behavior

- Turn 1 may fallback `opencode-go/* -> ollama-cloud/*` for OpenCode chains;
  Kimi has one direct K3 candidate and no fallback.
- The winning candidate is then locked per argos: kind/provider/model/effort/session id.
- Later turns resume with `opencode --session <id>`, `claude --resume <id>`, or
  Kimi ACP `session/resume` over JSON-RPC stdio.
- Later turns do not fallback by default; transient errors retry once, then the argos is marked dead or `outcome_unknown` according to whether duplicate execution is possible.
- Authentication/client-eligibility failures mark that argos `needs_human` instead of `dead`; the session remains auditable and the CLI exits `3`.
- Other argoses continue if one argos dies.
- Transcripts are append-only JSONL audit logs; provider session ids are the fast-path for actual context.

## Artifacts

```text
~/.argos/sessions/<id>/
  session.json
  session.lock
  effective_config.json
  argoses/<logical>/transcript.jsonl
  turns/001/{input.md,raw,normalized,final.md,meta.json}
  turns/001/inputs_report.json
  turns/002/{...}
  synthesis/{final.md,meta.json}  # debate sessions
```

## Contrats, affectations et presets rapides

Le prompt provider est compilé à partir de couches distinctes :

- un socle de sécurité commun;
- un contrat propre au workflow (`plan`, `review`, `critique`, `council`,
  `research`, etc.);
- une affectation composable issue des registres `roles`, `lenses` et
  `assignments`;
- la demande et les contextes non fiables bornés.

La sélection du provider/modèle reste indépendante de l'affectation. Le
registre historique `personas` demeure un fallback de compatibilité, mais les
nouvelles configurations doivent préférer les trois registres composables.
Chaque nouvel appel provider trace un `prompt_manifest` déterministe dans les
résultats et artefacts : workflow, phase, provenance et hash de l'affectation,
hash du contrat, budget et tailles. Lors d'un tour repris, la provenance est
conservée sans réinjecter le préfixe d'affectation dans l'historique provider.

Le mode `council` est l'exception volontaire : il utilise un contrat
conversationnel neutre et supprime les affectations spécialisées afin de
préserver les voix parallèles.

Les modes configurés évitent d'écrire une longue liste d'argoses. La forme canonique, sûre dans tous les shells, est `argos run <mode>` ; les raccourcis historiques `@...` restent compatibles lorsqu'ils sont correctement échappés :

```bash
argos run critique "..."
argos run review "..." --file src/foo.ts
argos start plan "tour 1: architecture" --json
argos ask adv_YYYYMMDDTHHMMSS_xxxxxxxx "tour 2: implémentation"
argos multi critique --turn prompts/01.md --turn prompts/02.md
```

Presets par défaut :

- `@council` → `council` avec `fable`, `kimi3`
- `@critique` → `critique` avec `opus`, `glm`, `minimax`
- `@review` → `review` avec `sonnet`, `kimi`, `minimax`
- `@plan` → `plan` avec `fable_medium`, `kimi`, `glm_max`
- `@ui` → `ui` avec `glm`, `sonnet`, `minimax`
- `@debug` → `debug` avec `deepseek`, `sonnet`, `minimax`
- `@consensus` → `consensus` avec `opus`, `kimi`, `glm`, `minimax`

Un `--argos` explicite remplace la liste du preset tout en gardant le mode et la persona de l'argos demandé :

```bash
argos run critique "smoke" --argos minimax --single-ok
```

Invariant important : les triggers `@critique`, `@review`, etc. sont interprétés uniquement depuis les arguments CLI de l'utilisateur. Une réponse d'argos contenant `@critique` ne déclenche jamais d'autre argos.

## Validation notes

Version `0.9.0-rc1` adds the neutral persistent `council` mode used by
`$argos-council`: one or two external partners, verbatim current-message
transport, and no task-specific persona or mandatory review headings.

Prompt orchestration v2 adds mode-specific workflow contracts, composable
roles/lenses/assignments, collision-safe untrusted provider-output transport,
and deterministic prompt manifests. Review-like runs write `findings.json`
and bounded review loops stop on no delta or identical findings. Research
writes `coverage.json` before model work and skips synthesis/review when
coverage is insufficient unless `--force-model-on-insufficient` is explicitly
recorded.

Version `0.8.0` adds safe recursive `--dir` context, auditable input reports,
conversation lifecycle commands, bounded fork reconstruction, explicit
`outcome_unknown` handling, the `kimi3` logical route, and moderated
multi-Argos debates. Existing validation still checks argos/preset
cross-references and candidate shapes at config load, rejects unsafe argos
path names, avoids double file attachment, writes private artifacts, and
injects personas only when creating fresh provider context.

## Model config management

```bash
argos config show                  # effective models, modes, presets, synthesis
argos config show --json
argos config set-model sonnet --kind claude --model claude-sonnet-5 --provider claude --effort medium
argos config set-model kimi --kind kimi --model kimi-code/k3 --provider kimi --command kimi
argos config set-model agy_image --kind agy --model default --provider agy --command agy
argos config set-mode vision --argos agy_image
```

`set-model` and `set-mode` validate the full config and write unique timestamped backups before atomically replacing `~/.config/argos/config.json`.
Sonnet now targets Anthropic's `claude-sonnet-5` model id. Kimi uses ACP v1 over stdio with an artifact-private `tools: []` agent profile; prompts never enter argv, provider sessions resume by structured ID, and any tool/reverse-RPC event is rejected. Vision defaults to the `agy_image` argos (`@vision` / `vision`) and accepts repeated `--image` paths for PNG, JPEG, WEBP, HEIC, and HEIF files. `agy`/Antigravity is the only supported vision provider. `--image` is rejected outside `@vision` / `vision` because text providers cannot access image files. `argos doctor` treats `opencode` + `claude` + `kimi` as core text readiness and reports optional agy vision CLI visibility separately; live provider auth or client eligibility can still require human action, and visual correctness should be smoke-tested with a known image before treating `@vision` as a strict visual QA gate. Vision inputs and the full AGY prompt are staged into private artifact subdirectories; AGY receives only their directories plus a short prompt-file reference, avoiding stdin incompatibilities, command-line length limits, and prompt disclosure in process listings. Prompts include a baseline no-tools/no-nested-argoses contract, mark embedded files as untrusted data, and enforce normalized sections (`Blockers`, `Important issues`, `Preferences`, `Minimal fix plan`).

## Strict gates

```bash
argos gate set implementation pass --evidence "tests passed"
argos gate set browser-target needs_human --evidence "no URL or app target provided"
argos gates --json
```

Gate states are intentionally limited to `pass`, `fail`, `blocked`, and `needs_human`; there is no silent `N/A`, `skipped`, or `deferred` state.

## Codex plugin facade

The bundled `argos-tools/` Codex plugin facade exposes the focused public surface
`$argos`, `$argos-plan`, `$argos-research`, `$argos-critique`,
`$argos-review`, and `$argos-council`. Operational config, diagnostics, gates,
vision, and generic conversation commands remain available through the
`$argos` router and the CLI without occupying separate visible skills. The
facade remains a Codex-side instruction layer: Argos itself never launches
Codex.


## MCP bridge

Argos now exposes a local MCP bridge in `argos/mcp_server.py` with its
contract adapter in `argos/mcp_adapter.py`.

The bridge is stdio-first and keeps the surface intentionally narrow:

- read-only inspection tools for sessions, councils, and benchmark artifacts;
- workflow tools for run/start/ask/council publish/research;
- idempotent `request_id` handling for repeated requests;
- workspace-contained file and directory expansion only.

The main resource templates are:

- `argos://sessions/{session_id}/summary`
- `argos://sessions/{session_id}/turns/{turn}`
- `argos://sessions/{session_id}/artifacts`
- `argos://councils/{council_id}/summary`
- `argos://councils/{council_id}/turns/{turn}`
- `argos://runs/{request_id}/manifest`
- `argos://runs/{request_id}/coverage`
- `argos://runs/{request_id}/findings`

The installed `argos-mcp` launcher keeps the regular CLI dependency-free. It
prepares a pinned, isolated MCP runtime and then starts the bundled server with
clean stdio:

```bash
argos-mcp --prepare --json
codex mcp add argos --env "ARGOS_WORKSPACE=<project>" -- argos-mcp
claude mcp add argos --scope local -e "ARGOS_WORKSPACE=<project>" -- argos-mcp
```

Use the absolute `argos-mcp` path when the client does not inherit the tool
installer's `PATH`. Full Windows, WSL, timeout, verification, update, rollback,
and uninstall instructions are centralized in
[`docs/MCP_INSTALL.md`](../docs/MCP_INSTALL.md).

The SDK and real-stdio smoke suite is:

```powershell
uv run --with mcp==2.0.0 --with pytest python -m pytest `
  argos/tests/test_mcp_contract.py `
  argos/tests/test_mcp_adapter.py `
  argos/tests/test_mcp_runtime.py `
  argos/tests/test_mcp_launcher.py `
  argos/tests/test_mcp_server.py `
  argos/tests/test_mcp_stdio.py -q
```


## Native Windows support

Provider timeouts are absolute per-candidate wall-clock budgets: waiting for
in-process and cross-process concurrency consumes the same budget later used
by the provider subprocess. A persistent request whose remote outcome is
unknown (for example an outer timeout) is never retried automatically with the
same provider session ID. Explicitly safe transient retries, when applicable,
remain inside the original deadline.

Raw provider output is immutable per attempt and uses names such as
`raw/<argos>.<provider>.attempt-001.stdout` and the matching `.stderr` file.
Consumers must follow each normalized result's `raw_path` rather than assume a
fixed raw filename. OpenCode stdout is consumed incrementally; structured
quota, authentication, and rate-limit error events terminate the stuck CLI
early and retain the real provider error.

Persistent turns distinguish `completed`, `partial`, `failed`,
`needs_human`, and `outcome_unknown`. A turn with at least one usable voice is
`partial` when another targeted voice did not answer. The attempted `turn`
counter remains monotonic, while `last_good_turn` advances only for
`completed` and `partial` turns.

Native Windows support is a first-class target. On Windows, provider processes are launched with `CREATE_NEW_PROCESS_GROUP`, and on timeout the entire process tree is terminated via `taskkill /F /T /PID <pid>`, with a plain kill of the direct process as fallback if `taskkill` is unavailable or fails. The `bin\argos-dev.cmd` and `bin\argos-dev.ps1` wrappers are provided for Windows shells (cmd and PowerShell). A native Windows clone can live in any writable directory; WSL remains a separate supported installation when provider CLIs/auth live in Linux.
On Windows, Argos preserves the user's normal OpenCode profile instead of
inventing a second XDG home, uses a longer OpenCode startup allowance, and
disables Claude Code's background auto-updater for provider subprocesses so
completed calls do not retain their isolated working directories.
Kimi prompts use ACP stdio rather than `-p <prompt>`, avoiding the Windows
command-line limit and process-list disclosure. The Kimi provider is serialized
at one call across processes, while provider session IDs remain per argos.
Cross-process slots use one canonical lock namespace, and `argos providers`
uses the native `tasklist` snapshot to report OpenCode, Claude, Kimi, and AGY
processes instead of reporting an always-limited `/proc` view. If `tasklist`
itself fails, the snapshot is reported explicitly as `limited`.

## Versioned internal benchmark

`argos benchmark` runs a deterministic benchmark suite for argos's core automation contract. The suite is versioned in every artifact (`suite_id=argos-internal-quality`, `suite_version=2.0.0`) so future changes can be compared apples-to-apples.

```bash
argos benchmark --json
argos benchmark --iterations 5
argos benchmark --prompt-variant no-persona --json
argos benchmark --prompt-variant persona --argos sonnet --compare <baseline-dir>
argos benchmark --prompt-variant compact-persona --argos sonnet
argos benchmark --compare ~/.argos/sessions/20260709T151440-benchmark
argos benchmark --compare-latest
```

Artifacts are written under `~/.argos/sessions/<timestamp>-benchmark/`:

- `benchmark.json`: machine-readable score, suite version, per-case pass/fail, timings, and optional comparison deltas.
- `report.md`: human-readable summary.

Current internal cases cover config safety, prompt contract/truncation, launch-matrix contracts for one-shot/resume/council/debate surfaces, provider parser normalization, SOTA citation integrity, private artifact permissions, exit-code semantics, and a weighted `problem_suite_quality` case. The problem suite is separately versioned (`problem_set_version`) and includes deterministic argos-quality problems inspired by SWE-bench Verified, τ-bench, GAIA/WebArena-style evidence grounding, prompt-injection safety, cost/latency routing, state repair, Council synthesis discipline, debate round discipline, LLM-as-judge calibration, provider failure triage, concurrency cleanup, prompt budget preservation, and ambiguous severity classification. Artifacts now record `benchmark_scope=static-regression-gate`, split/difficulty/surface metrics, saturation/discrimination metrics, a separate provider-availability snapshot, and `fixture_set_hash` / `keyword_list_hash` / `scorer_params_hash` for provenance. Prompt cases can run as `no-persona`, `persona`, or `compact-persona`, with `--argos` selecting the persona hash recorded in `benchmark.json`. Use `--compare` or `--compare-latest` to see score/timing deltas; comparisons now include `comparable`, hash match details, and warnings when suite, fixture, keyword, or scorer semantics changed.
