# mosaic

Global external-mosaic runner for Codex. Standard-library Python. It calls allowlisted external CLIs only (`opencode`, `claude`, and `agy`/Antigravity for image analysis) and never launches `codex`/`codex exec`.

## Invariants

- No native `ollama` CLI. Ollama Cloud is used only through `opencode run -m ollama-cloud/...`.
- OpenCode Go remains the primary paid-code lane when available; fallback to Ollama Cloud is handled by config chains.
- MiniMax is locked to `minimax/MiniMax-M3`; no `opencode-go/minimax-*` or `ollama-cloud/minimax-*`.
- Codex agents are launched only from the current Codex session/tmux/OMX surfaces, not from this wrapper.
- Mosaic artifacts, transcripts, raw provider outputs, and config backups are written private-by-default (`0700` directories, `0600` files).
- Provider authentication failures are surfaced as `needs_human`; they do not silently fall through to alternate candidates.
- Process exit codes are explicit: `0` all required mosaics OK, `2` provider/tool/config failure, `3` human action required (`needs_human`). Automation should prefer JSON/artifacts for details, but shell-only gates can still distinguish credentials/client-eligibility from generic failure.

## One-shot

```bash
mosaic run critique "..." --mosaic opus --mosaic glm --mosaic minimax
mosaic run review "..." --file path/to/file.ts
mosaic run consensus < prompt.md
```

## Multi-turn sessions

Create a panel session and run turn 1:

```bash
mosaic start critique "Réfléchis à l'architecture uniquement" \
  --mosaic kimi \
  --mosaic glm \
  --mosaic minimax \
  --json
```

Continue all live mosaics in the same session:

```bash
mosaic ask adv_YYYYMMDDTHHMMSS_xxxxxxxx "Maintenant implémente"
```

Target only one mosaic:

```bash
mosaic ask adv_YYYYMMDDTHHMMSS_xxxxxxxx "Révise ton plan" --mosaic kimi
```

Batch several turns:

```bash
mosaic multi critique \
  --mosaic kimi \
  --mosaic glm \
  --turn prompts/01-architecture.md \
  --turn prompts/02-implementation.md
```

Inspect and end:

```bash
mosaic runs                 # one-shot run artifacts created by `mosaic run`
mosaic sessions             # multi-turn sessions created by `mosaic start`/`multi`
mosaic session adv_YYYYMMDDTHHMMSS_xxxxxxxx
mosaic end adv_YYYYMMDDTHHMMSS_xxxxxxxx
```

## Session behavior

- Turn 1 may fallback `opencode-go/* -> ollama-cloud/*`.
- The winning candidate is then locked per mosaic: kind/provider/model/effort/session id.
- Later turns resume with `opencode --session <id>` or `claude --resume <id>`.
- Later turns do not fallback by default; transient errors retry once, then the mosaic is marked dead.
- Authentication/client-eligibility failures mark that mosaic `needs_human` instead of `dead`; the session remains auditable and the CLI exits `3`.
- Other mosaics continue if one mosaic dies.
- Transcripts are append-only JSONL audit logs; provider session ids are the fast-path for actual context.

## Artifacts

```text
~/.mosaic/sessions/<id>/
  session.json
  session.lock
  effective_config.json
  mosaics/<logical>/transcript.jsonl
  turns/001/{input.md,raw,normalized,final.md,meta.json}
  turns/002/{...}
```

## Personas et presets rapides

Chaque mosaic reçoit automatiquement une mini-persona structurée (rôle, priorités, format attendu, limites). Ces personas sont injectées dans le prompt envoyé au provider, et tracées dans `meta.json`, `session.json` et les résultats normalisés via un hash/version.

Les presets `@...` évitent d'écrire une longue liste d'mosaics :

```bash
mosaic @critique "..."                         # alias de mosaic run @critique "..."
mosaic run @review "..." --file src/foo.ts
mosaic start @plan "tour 1: architecture" --json
mosaic ask adv_YYYYMMDDTHHMMSS_xxxxxxxx "tour 2: implémentation"
mosaic multi @critique --turn prompts/01.md --turn prompts/02.md
```

Presets par défaut :

- `@critique` → `critique` avec `opus`, `glm`, `minimax`
- `@review` → `review` avec `sonnet`, `kimi`, `minimax`
- `@plan` → `plan` avec `fable_medium`, `kimi`, `glm_max`
- `@ui` → `ui` avec `glm`, `sonnet`, `minimax`
- `@debug` → `debug` avec `deepseek`, `sonnet`, `minimax`
- `@consensus` → `consensus` avec `opus`, `kimi`, `glm`, `minimax`

Un `--mosaic` explicite remplace la liste du preset tout en gardant le mode et la persona de l'mosaic demandé :

```bash
mosaic @critique "smoke" --mosaic minimax
```

Invariant important : les triggers `@critique`, `@review`, etc. sont interprétés uniquement depuis les arguments CLI de l'utilisateur. Une réponse d'mosaic contenant `@critique` ne déclenche jamais d'autre mosaic.

## Validation notes

Version `0.6.0` validates mosaic/preset cross-references and candidate shapes at config load, rejects unsafe mosaic path names, avoids double file attachment (file contents are already embedded in the built prompt), writes private artifacts, and injects personas only on session turn 1.

## Model config management

```bash
mosaic config show                  # effective models, modes, presets, synthesis
mosaic config show --json
mosaic config set-model sonnet --kind claude --model claude-sonnet-5 --provider claude --effort medium
mosaic config set-model agy_image --kind agy --model default --provider agy --command agy
mosaic config set-mode vision --mosaic agy_image
```

`set-model` and `set-mode` validate the full config and write unique timestamped backups before atomically replacing `~/.config/mosaic/config.json`.
Sonnet now targets Anthropic's `claude-sonnet-5` model id. Vision defaults to the `agy_image` mosaic (`@vision` / `vision`) and accepts repeated `--image` paths for PNG, JPEG, WEBP, HEIC, and HEIF files. `agy`/Antigravity is the only supported vision provider. `--image` is rejected outside `@vision` / `vision` because text providers cannot access image files. `mosaic doctor` distinguishes core text readiness (`opencode` + `claude`) from optional agy vision CLI visibility; live agy auth or client eligibility can still require human action, and visual correctness should be smoke-tested with a known image before treating `@vision` as a strict visual QA gate. Vision inputs are staged once into a private artifact subdirectory before provider CLIs receive include directories. Prompts include a baseline no-tools/no-nested-mosaics contract, mark embedded files as untrusted data, and enforce normalized sections (`Blockers`, `Important issues`, `Preferences`, `Minimal fix plan`).

## Strict gates

```bash
mosaic gate set implementation pass --evidence "tests passed"
mosaic gate set browser-target needs_human --evidence "no URL or app target provided"
mosaic gates --json
```

Gate states are intentionally limited to `pass`, `fail`, `blocked`, and `needs_human`; there is no silent `N/A`, `skipped`, or `deferred` state.

## Codex plugin facade

A local Codex plugin facade was scaffolded at `~/.agents/plugins/plugins/mos-tools` with skills named `$mos-review`, `$mos-critique`, `$mos-plan`, `$mos-vision`, `$mos-config`, and `$mos-gate`. It is registered in `~/.agents/plugins/marketplace.json` and remains a Codex-side instruction layer: mosaic itself still never launches Codex.


## Native Windows timeout caveat

Native Windows support remains experimental. The core shims support Windows process creation and file-lock fallbacks, but provider timeout cleanup may only terminate the direct provider process rather than every descendant process until a real Windows Job Object or equivalent `taskkill /T` validation path is added. WSL remains recommended when provider CLIs/auth live in Linux.

## Versioned internal benchmark

`mosaic benchmark` runs a deterministic, provider-free benchmark suite for mosaic's core automation contract. The suite is versioned in every artifact (`suite_id=mosaic-internal-quality`, `suite_version=1.10.0`) so future changes can be compared apples-to-apples.

```bash
mosaic benchmark --json
mosaic benchmark --iterations 5
mosaic benchmark --prompt-variant no-persona --json
mosaic benchmark --prompt-variant persona --mosaic sonnet --compare <baseline-dir>
mosaic benchmark --prompt-variant compact-persona --mosaic sonnet
mosaic benchmark --compare ~/.mosaic/sessions/20260709T151440-benchmark
mosaic benchmark --compare-latest
```

Artifacts are written under `~/.mosaic/sessions/<timestamp>-benchmark/`:

- `benchmark.json`: machine-readable score, suite version, per-case pass/fail, timings, and optional comparison deltas.
- `report.md`: human-readable summary.

Current internal cases cover config safety, prompt contract/truncation, provider parser normalization, SOTA citation integrity, private artifact permissions, exit-code semantics, and a weighted `problem_suite_quality` case. The problem suite is separately versioned (`problem_set_version`) and includes deterministic mosaic-quality problems inspired by SWE-bench Verified, τ-bench, GAIA/WebArena-style evidence grounding, prompt-injection safety, cost/latency routing, state repair, LLM-as-judge calibration, provider failure triage, concurrency cleanup, prompt budget preservation, and ambiguous severity classification. Artifacts now record `benchmark_scope=static-regression-gate`, split/difficulty metrics, saturation/discrimination metrics, and `fixture_set_hash` / `keyword_list_hash` / `scorer_params_hash` for provenance. Prompt cases can run as `no-persona`, `persona`, or `compact-persona`, with `--mosaic` selecting the persona hash recorded in `benchmark.json`. Use `--compare` or `--compare-latest` to see score/timing deltas; comparisons now include `comparable`, hash match details, and warnings when suite, fixture, keyword, or scorer semantics changed.
