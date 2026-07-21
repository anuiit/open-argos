# open-argos

Global external-argos runner for Codex (command: `argos`). Standard-library Python. It calls allowlisted external CLIs only (`opencode`, `claude`, and `agy`/Antigravity for image analysis) and never launches `codex`/`codex exec`.

## Invariants

- No native `ollama` CLI. Ollama Cloud is used only through `opencode run -m ollama-cloud/...`.
- OpenCode Go remains the primary paid-code lane when available; fallback to Ollama Cloud is handled by config chains.
- MiniMax is locked to `minimax/MiniMax-M3`; no `opencode-go/minimax-*` or `ollama-cloud/minimax-*`.
- Codex agents are launched only from the current Codex session/tmux/OMX surfaces, not from this wrapper.
- Argos artifacts, transcripts, raw provider outputs, and config backups are written private-by-default (`0700` directories, `0600` files).
- Provider authentication failures are surfaced as `needs_human`; they do not silently fall through to alternate candidates.
- Process exit codes are explicit: `0` all required argoses OK, `2` provider/tool/config failure, `3` human action required (`needs_human`). Automation should prefer JSON/artifacts for details, but shell-only gates can still distinguish credentials/client-eligibility from generic failure.

## One-shot

```bash
argos run critique "..." --argos opus --argos glm --argos minimax
argos run review "..." --file path/to/file.ts
argos run consensus < prompt.md
```

## Multi-turn sessions

Create a panel session and run turn 1:

```bash
argos start critique "Réfléchis à l'architecture uniquement" \
  --argos kimi \
  --argos glm \
  --argos minimax \
  --json
```

Continue all live argoses in the same session:

```bash
argos ask adv_YYYYMMDDTHHMMSS_xxxxxxxx "Maintenant implémente"
```

Target only one argos:

```bash
argos ask adv_YYYYMMDDTHHMMSS_xxxxxxxx "Révise ton plan" --argos kimi
```

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

## Session behavior

- Turn 1 may fallback `opencode-go/* -> ollama-cloud/*`.
- The winning candidate is then locked per argos: kind/provider/model/effort/session id.
- Later turns resume with `opencode --session <id>` or `claude --resume <id>`.
- Later turns do not fallback by default; transient errors retry once, then the argos is marked dead.
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
  turns/002/{...}
```

## Personas et presets rapides

Chaque argos reçoit automatiquement une mini-persona structurée (rôle, priorités, format attendu, limites). Ces personas sont injectées dans le prompt envoyé au provider, et tracées dans `meta.json`, `session.json` et les résultats normalisés via un hash/version.

Les presets `@...` évitent d'écrire une longue liste d'argoses :

```bash
argos @critique "..."                         # alias de argos run @critique "..."
argos run @review "..." --file src/foo.ts
argos start @plan "tour 1: architecture" --json
argos ask adv_YYYYMMDDTHHMMSS_xxxxxxxx "tour 2: implémentation"
argos multi @critique --turn prompts/01.md --turn prompts/02.md
```

Presets par défaut :

- `@critique` → `critique` avec `opus`, `glm`, `minimax`
- `@review` → `review` avec `sonnet`, `kimi`, `minimax`
- `@plan` → `plan` avec `fable_medium`, `kimi`, `glm_max`
- `@ui` → `ui` avec `glm`, `sonnet`, `minimax`
- `@debug` → `debug` avec `deepseek`, `sonnet`, `minimax`
- `@consensus` → `consensus` avec `opus`, `kimi`, `glm`, `minimax`

Un `--argos` explicite remplace la liste du preset tout en gardant le mode et la persona de l'argos demandé :

```bash
argos @critique "smoke" --argos minimax
```

Invariant important : les triggers `@critique`, `@review`, etc. sont interprétés uniquement depuis les arguments CLI de l'utilisateur. Une réponse d'argos contenant `@critique` ne déclenche jamais d'autre argos.

## Validation notes

Version `0.7.0` validates argos/preset cross-references and candidate shapes at config load, rejects unsafe argos path names, avoids double file attachment (file contents are already embedded in the built prompt), writes private artifacts, and injects personas only on session turn 1.

## Model config management

```bash
argos config show                  # effective models, modes, presets, synthesis
argos config show --json
argos config set-model sonnet --kind claude --model claude-sonnet-5 --provider claude --effort medium
argos config set-model agy_image --kind agy --model default --provider agy --command agy
argos config set-mode vision --argos agy_image
```

`set-model` and `set-mode` validate the full config and write unique timestamped backups before atomically replacing `~/.config/argos/config.json`.
Sonnet now targets Anthropic's `claude-sonnet-5` model id. Vision defaults to the `agy_image` argos (`@vision` / `vision`) and accepts repeated `--image` paths for PNG, JPEG, WEBP, HEIC, and HEIF files. `agy`/Antigravity is the only supported vision provider. `--image` is rejected outside `@vision` / `vision` because text providers cannot access image files. `argos doctor` distinguishes core text readiness (`opencode` + `claude`) from optional agy vision CLI visibility; live agy auth or client eligibility can still require human action, and visual correctness should be smoke-tested with a known image before treating `@vision` as a strict visual QA gate. Vision inputs are staged once into a private artifact subdirectory before provider CLIs receive include directories. Prompts include a baseline no-tools/no-nested-argoses contract, mark embedded files as untrusted data, and enforce normalized sections (`Blockers`, `Important issues`, `Preferences`, `Minimal fix plan`).

## Strict gates

```bash
argos gate set implementation pass --evidence "tests passed"
argos gate set browser-target needs_human --evidence "no URL or app target provided"
argos gates --json
```

Gate states are intentionally limited to `pass`, `fail`, `blocked`, and `needs_human`; there is no silent `N/A`, `skipped`, or `deferred` state.

## Codex plugin facade

A local Codex plugin facade was scaffolded at `~/.agents/plugins/plugins/argos-tools` with skills named `$argos-review`, `$argos-critique`, `$argos-plan`, `$argos-vision`, `$argos-config`, and `$argos-gate`. It is registered in `~/.agents/plugins/marketplace.json` and remains a Codex-side instruction layer: argos itself still never launches Codex.


## Native Windows support

Native Windows support is a first-class target. On Windows, provider processes are launched with `CREATE_NEW_PROCESS_GROUP`, and on timeout the entire process tree is terminated via `taskkill /F /T /PID <pid>`, with a plain kill of the direct process as fallback if `taskkill` is unavailable or fails. The `bin\argos-dev.cmd` and `bin\argos-dev.ps1` wrappers are provided for Windows shells (cmd and PowerShell). The native Windows copy lives in `F:\dev\open-argos`, a mirror of the WSL copy; feature parity between the two is required. WSL remains supported when provider CLIs/auth live in Linux.

## Versioned internal benchmark

`argos benchmark` runs a deterministic, provider-free benchmark suite for argos's core automation contract. The suite is versioned in every artifact (`suite_id=argos-internal-quality`, `suite_version=1.10.0`) so future changes can be compared apples-to-apples.

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

Current internal cases cover config safety, prompt contract/truncation, provider parser normalization, SOTA citation integrity, private artifact permissions, exit-code semantics, and a weighted `problem_suite_quality` case. The problem suite is separately versioned (`problem_set_version`) and includes deterministic argos-quality problems inspired by SWE-bench Verified, τ-bench, GAIA/WebArena-style evidence grounding, prompt-injection safety, cost/latency routing, state repair, LLM-as-judge calibration, provider failure triage, concurrency cleanup, prompt budget preservation, and ambiguous severity classification. Artifacts now record `benchmark_scope=static-regression-gate`, split/difficulty metrics, saturation/discrimination metrics, and `fixture_set_hash` / `keyword_list_hash` / `scorer_params_hash` for provenance. Prompt cases can run as `no-persona`, `persona`, or `compact-persona`, with `--argos` selecting the persona hash recorded in `benchmark.json`. Use `--compare` or `--compare-latest` to see score/timing deltas; comparisons now include `comparable`, hash match details, and warnings when suite, fixture, keyword, or scorer semantics changed.
