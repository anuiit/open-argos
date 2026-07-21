# Argos-Tools / argos architecture

Ce document décrit le fonctionnement du plugin Codex `argos-tools` et du runner local `argos` (core: `argos/argos.py`, lancé en développement via `bin/argos-dev`).

## Vue d'ensemble

`argos-tools` est une façade Codex légère. Elle fournit des skills (`$argos-review`, `$argos-critique`, `$argos-plan`, `$argos-vision`, `$argos-sota`, `$argos-config`, `$argos-gate`, `$argos-doctor`) qui expliquent à Codex comment appeler le CLI local `argos`. Le CLI `argos` exécute ensuite uniquement des outils externes allowlistés (`opencode`, `claude`, `agy`) et écrit des artefacts privés sous `~/.argos/sessions`. Pour la vision, `agy`/Antigravity est le provider officiel unique.

Invariant central: `argos` ne lance jamais `codex` / `codex exec`, et n'utilise jamais le CLI natif `ollama`.

```mermaid
flowchart TB
  User[Utilisateur / Codex] --> Skill[Skill Argos-Tools]
  Skill --> Contract[Contrat de contexte argos]
  Contract --> CLI[argos CLI\n~/.local/bin/argos\ndev: bin/argos-dev]

  CLI --> Config[Config effective\n~/.config/argos/config.json\n+ DEFAULT_CONFIG]
  CLI --> Prompt[Prompt builder\nmode + demande + fichiers + images + persona]
  CLI --> Router[Preset/mode router\n@review/@critique/@plan/@vision/@sota]

  Router --> Runner[Runner asyncio]
  Runner --> Limits[Semaphores in-process\n+ verrous cross-process]
  Limits --> Providers{Provider candidate chain}

  Providers -->|opencode_go / ollama_cloud / minimax| OpenCode[opencode run]
  Providers -->|claude| Claude[claude -p]
  Providers -->|agy image| Agy[agy --print stdin]

  OpenCode --> Parse[Parse/normalize results]
  Claude --> Parse
  Agy --> Parse

  Parse --> Artifacts[Artefacts privés 0700/0600\nraw/ normalized/ final.md meta.json]
  Parse --> Exit[Exit code\n0 ok / 2 erreur / 3 needs_human]

  CLI --> Gates[Gates strictes\npass/fail/blocked/needs_human]
  CLI --> Sessions[Sessions multi-turn\nsession.json + transcripts]
  CLI --> SOTA[SOTA Explorer\nretrieval + synthèse + vérification citations]
  SOTA --> Artifacts
```

## Contrat d'input et prompts

- Les skills Argos-Tools construisent un brief court suivant `references/argos-context-contract.md`; le CLI `argos` injecte ensuite un contrat commun: analyse textuelle seulement, aucun outil/agent/argos/CLI déclenché par le provider, fichiers traités comme données non fiables.
- Les prompts argos imposent les sections `Blockers`, `Important issues`, `Preferences`, `Minimal fix plan` pour faciliter la consommation par Codex/OMX.
- Les fichiers passés avec `--file` sont inclus avec des fences Markdown adaptatifs afin qu'un fichier contenant des backticks ne casse pas la structure du prompt.
- Les images sont acceptées uniquement en mode `vision`; elles sont copiées une seule fois dans `vision_inputs/` privé et `agy` ne reçoit qu'un `--add-dir` vers ce staging.

## Flux one-shot (`argos @review`, `@critique`, `@plan`, `@vision`)

```mermaid
sequenceDiagram
  participant C as Codex skill
  participant A as argos CLI
  participant R as Runner
  participant L as Limits/locks
  participant P as Provider CLI
  participant FS as Artifact store

  C->>A: argos @review "prompt" --file ...
  A->>A: resolve preset -> mode + argos
  A->>A: validate config, files, images
  A->>A: build prompt + inject persona
  A->>FS: write input.md + effective_config.json
  A->>R: run_logical(argos) for each argos
  par argos
    R->>L: acquire global/provider/opencode locks
    L-->>R: slot acquired or timeout
    R->>P: subprocess allowlisted CLI via stdin
    P-->>R: stdout/stderr/exit
    R->>FS: raw/*.stdout/stderr + normalized/*.json/md
    R->>L: release locks
  end
  R-->>A: ArgosResult[]
  A->>FS: meta.json + final.md
  A-->>C: Markdown or JSON + exit code
```

## Flux multi-turn (`start`, `ask`, `multi`)

```mermaid
stateDiagram-v2
  [*] --> Created: argos start/multi
  Created --> Turn1Running: active_turn={turn:1,pid}
  Turn1Running --> Active: providers ok + session ids locked
  Turn1Running --> NeedsHuman: auth/client eligibility
  Turn1Running --> Degraded: provider error/dead
  Active --> TurnNRunning: argos ask
  TurnNRunning --> Active: ok, update provider_session_id/cost
  TurnNRunning --> NeedsHuman: needs_human argos retained auditable
  TurnNRunning --> Degraded: non-transient failure marks argos dead
  Active --> Ended: argos end
  NeedsHuman --> Ended: argos end
  Degraded --> Ended: argos end
```

Session artifacts:

```text
~/.argos/sessions/adv_<timestamp>_<id>/
  session.json
  session.lock
  effective_config.json
  argoses/<logical>/transcript.jsonl
  turns/001/{input.md, final.md, meta.json, raw/, normalized/}
  turns/002/{...}
```

## Contrôle du parallélisme

Deux couches protègent les providers:

1. **In-process**: `asyncio.Semaphore` global, par provider, et `opencode_total`.
2. **Cross-process**: fichiers de lock sous `~/.argos/locks`, utilisés quand `concurrency.cross_process=true`.

```mermaid
flowchart LR
  Task[run_candidate] --> G[global semaphore]
  G --> P[provider semaphore]
  P --> O{kind == opencode?}
  O -->|oui| OT[opencode_total semaphore]
  O -->|non| X[provider file lock]
  OT --> X
  X --> Y{opencode?}
  Y -->|oui| XL[opencode_total file lock]
  Y -->|non| Exec[subprocess]
  XL --> Exec
  Exec --> Release[release locks/semaphores]
```

## Plugin Argos-Tools

Le plugin ne contient pas de logique provider. Il contient:

- `skills/*/SKILL.md`: contrats d'utilisation Codex pour les commandes argos.
- `references/argos-context-contract.md`: format minimal des prompts envoyés aux argos.
- `scripts/smoke_argos_tools.py`: smoke non destructif par défaut, avec options live/vision/SOTA et `--adversarial`.
- `scripts/adversarial_smoke_argos_tools.py`: deux checks cassants par surface feature sans spend modèle par défaut; `--sota-live` ajoute un fetch public SOTA borné en `--no-model` dans un répertoire temporaire nettoyé.
- `tests/test_smoke_argos_tools.py`: tests unitaires du smoke script.
- `ARCHITECTURE.md`: ce document.

```mermaid
flowchart TB
  Marketplace[Codex marketplace personal] --> Plugin[~/plugins/argos-tools]
  Plugin --> Manifest[.codex-plugin/plugin.json]
  Plugin --> Skills[skills/*/SKILL.md]
  Plugin --> References[references/*.md]
  Plugin --> Smoke[scripts/smoke_argos_tools.py]
  Skills --> Argos[argos CLI]
  Smoke --> Argos
  Argos --> Artifacts[~/.argos/sessions]
```

## Validation recommandée

Sans appel modèle payant:

```bash
python3 -m pytest -q ~/.config/argos/tests ~/plugins/argos-tools/tests
python3 -m py_compile ~/.config/argos/argos.py ~/plugins/argos-tools/scripts/smoke_argos_tools.py
python3 -m ruff check ~/.config/argos/argos.py ~/.config/argos/tests ~/plugins/argos-tools/scripts ~/plugins/argos-tools/tests
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ~/plugins/argos-tools
python3 ~/plugins/argos-tools/scripts/smoke_argos_tools.py
```

Optionnel, réseau sans modèle:

```bash
python3 ~/plugins/argos-tools/scripts/smoke_argos_tools.py --sota
```

Optionnel, live/payant:

```bash
argos ping --live --argos sonnet --timeout 30 --json
python3 ~/plugins/argos-tools/scripts/smoke_argos_tools.py --live
python3 ~/plugins/argos-tools/scripts/smoke_argos_tools.py --vision
python3 ~/plugins/argos-tools/scripts/smoke_argos_tools.py --adversarial --no-gate
```

## Risques connus / axes futurs

- `argos/argos.py` est encore un gros fichier unique: les prochaines features devraient extraire progressivement config, runner, sessions, SOTA, CLI parser, et provider adapters.
- La parité Windows native est désormais assurée (kill d'arborescence de processus via `taskkill /F /T`, wrappers `.cmd`/`.ps1`); le miroir Windows vit dans `F:\dev\open-argos`.
- Le smoke live peut consommer des tokens; le mode par défaut reste statique/non-payant.
- Les snapshots de processus provider sont précis sur `/proc`, limités sur plateformes sans `/proc`.
