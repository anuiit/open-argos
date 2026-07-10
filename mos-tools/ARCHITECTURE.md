# Mos-Tools / mosaic architecture

Ce document décrit le fonctionnement du plugin Codex `mos-tools` et du runner local `mosaic`.

## Vue d'ensemble

`mos-tools` est une façade Codex légère. Elle fournit des skills (`$mos-review`, `$mos-critique`, `$mos-plan`, `$mos-vision`, `$mos-sota`, `$mos-config`, `$mos-gate`, `$mos-doctor`) qui expliquent à Codex comment appeler le CLI local `mosaic`. Le CLI `mosaic` exécute ensuite uniquement des outils externes allowlistés (`opencode`, `claude`, `agy`) et écrit des artefacts privés sous `~/.mosaic/sessions`. Pour la vision, `agy`/Antigravity est le provider officiel unique.

Invariant central: `mosaic` ne lance jamais `codex` / `codex exec`, et n'utilise jamais le CLI natif `ollama`.

```mermaid
flowchart TB
  User[Utilisateur / Codex] --> Skill[Skill Mos-Tools]
  Skill --> Contract[Contrat de contexte mosaic]
  Contract --> CLI[mosaic CLI\n~/.local/bin/mosaic]

  CLI --> Config[Config effective\n~/.config/mosaic/config.json\n+ DEFAULT_CONFIG]
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

- Les skills Mos-Tools construisent un brief court suivant `references/mosaic-context-contract.md`; le CLI `mosaic` injecte ensuite un contrat commun: analyse textuelle seulement, aucun outil/agent/mosaic/CLI déclenché par le provider, fichiers traités comme données non fiables.
- Les prompts mosaic imposent les sections `Blockers`, `Important issues`, `Preferences`, `Minimal fix plan` pour faciliter la consommation par Codex/OMX.
- Les fichiers passés avec `--file` sont inclus avec des fences Markdown adaptatifs afin qu'un fichier contenant des backticks ne casse pas la structure du prompt.
- Les images sont acceptées uniquement en mode `vision`; elles sont copiées une seule fois dans `vision_inputs/` privé et `agy` ne reçoit qu'un `--add-dir` vers ce staging.

## Flux one-shot (`mosaic @review`, `@critique`, `@plan`, `@vision`)

```mermaid
sequenceDiagram
  participant C as Codex skill
  participant A as mosaic CLI
  participant R as Runner
  participant L as Limits/locks
  participant P as Provider CLI
  participant FS as Artifact store

  C->>A: mosaic @review "prompt" --file ...
  A->>A: resolve preset -> mode + mosaics
  A->>A: validate config, files, images
  A->>A: build prompt + inject persona
  A->>FS: write input.md + effective_config.json
  A->>R: run_logical(mosaic) for each mosaic
  par mosaics
    R->>L: acquire global/provider/opencode locks
    L-->>R: slot acquired or timeout
    R->>P: subprocess allowlisted CLI via stdin
    P-->>R: stdout/stderr/exit
    R->>FS: raw/*.stdout/stderr + normalized/*.json/md
    R->>L: release locks
  end
  R-->>A: MosaicResult[]
  A->>FS: meta.json + final.md
  A-->>C: Markdown or JSON + exit code
```

## Flux multi-turn (`start`, `ask`, `multi`)

```mermaid
stateDiagram-v2
  [*] --> Created: mosaic start/multi
  Created --> Turn1Running: active_turn={turn:1,pid}
  Turn1Running --> Active: providers ok + session ids locked
  Turn1Running --> NeedsHuman: auth/client eligibility
  Turn1Running --> Degraded: provider error/dead
  Active --> TurnNRunning: mosaic ask
  TurnNRunning --> Active: ok, update provider_session_id/cost
  TurnNRunning --> NeedsHuman: needs_human mosaic retained auditable
  TurnNRunning --> Degraded: non-transient failure marks mosaic dead
  Active --> Ended: mosaic end
  NeedsHuman --> Ended: mosaic end
  Degraded --> Ended: mosaic end
```

Session artifacts:

```text
~/.mosaic/sessions/adv_<timestamp>_<id>/
  session.json
  session.lock
  effective_config.json
  mosaics/<logical>/transcript.jsonl
  turns/001/{input.md, final.md, meta.json, raw/, normalized/}
  turns/002/{...}
```

## Contrôle du parallélisme

Deux couches protègent les providers:

1. **In-process**: `asyncio.Semaphore` global, par provider, et `opencode_total`.
2. **Cross-process**: fichiers de lock sous `~/.mosaic/locks`, utilisés quand `concurrency.cross_process=true`.

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

## Plugin Mos-Tools

Le plugin ne contient pas de logique provider. Il contient:

- `skills/*/SKILL.md`: contrats d'utilisation Codex pour les commandes mosaic.
- `references/mosaic-context-contract.md`: format minimal des prompts envoyés aux mosaics.
- `scripts/smoke_mos_tools.py`: smoke non destructif par défaut, avec options live/vision/SOTA et `--adversarial`.
- `scripts/adversarial_smoke_mos_tools.py`: deux checks cassants par surface feature sans spend modèle par défaut; `--sota-live` ajoute un fetch public SOTA borné en `--no-model` dans un répertoire temporaire nettoyé.
- `tests/test_smoke_mos_tools.py`: tests unitaires du smoke script.
- `ARCHITECTURE.md`: ce document.

```mermaid
flowchart TB
  Marketplace[Codex marketplace personal] --> Plugin[~/plugins/mos-tools]
  Plugin --> Manifest[.codex-plugin/plugin.json]
  Plugin --> Skills[skills/*/SKILL.md]
  Plugin --> References[references/*.md]
  Plugin --> Smoke[scripts/smoke_mos_tools.py]
  Skills --> Mosaic[mosaic CLI]
  Smoke --> Mosaic
  Mosaic --> Artifacts[~/.mosaic/sessions]
```

## Validation recommandée

Sans appel modèle payant:

```bash
python3 -m pytest -q ~/.config/mosaic/tests ~/plugins/mos-tools/tests
python3 -m py_compile ~/.config/mosaic/mosaic.py ~/plugins/mos-tools/scripts/smoke_mos_tools.py
python3 -m ruff check ~/.config/mosaic/mosaic.py ~/.config/mosaic/tests ~/plugins/mos-tools/scripts ~/plugins/mos-tools/tests
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ~/plugins/mos-tools
python3 ~/plugins/mos-tools/scripts/smoke_mos_tools.py
```

Optionnel, réseau sans modèle:

```bash
python3 ~/plugins/mos-tools/scripts/smoke_mos_tools.py --sota
```

Optionnel, live/payant:

```bash
mosaic ping --live --mosaic sonnet --timeout 30 --json
python3 ~/plugins/mos-tools/scripts/smoke_mos_tools.py --live
python3 ~/plugins/mos-tools/scripts/smoke_mos_tools.py --vision
python3 ~/plugins/mos-tools/scripts/smoke_mos_tools.py --adversarial --no-gate
```

## Risques connus / axes futurs

- `mosaic.py` est encore un gros fichier unique: les prochaines features devraient extraire progressivement config, runner, sessions, SOTA, CLI parser, et provider adapters.
- Windows natif reste expérimental; WSL demeure recommandé tant que les providers/auth vivent côté Linux.
- Le smoke live peut consommer des tokens; le mode par défaut reste statique/non-payant.
- Les snapshots de processus provider sont précis sur `/proc`, limités sur plateformes sans `/proc`.
