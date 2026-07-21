# État des lieux — mosaic-dev (21 juillet 2026)

Audit réalisé par exploration parallèle (2 sub-agents : code/architecture, benchmarks/exécution) sur `~/mosaic-dev`.

## 1. L'idée

mosaic est un runner de conseillers LLM externes pour sessions Codex : il orchestre en parallèle un panel de modèles hétérogènes (Opus, MiniMax, Kimi, GLM, DeepSeek, Qwen…) pour produire critiques, revues et plans multi-perspectives, sans jamais exécuter d'agent lui-même. Modes `critique/plan/review/ui/debug/vision/star/consensus`, personas hachées par modèle, presets `@...` interprétés uniquement depuis les args CLI (jamais depuis une sortie de modèle), sessions multi-turn persistantes, pipeline SOTA de recherche sourcée avec vérification d'intégrité des citations, et gates strictes (`pass/fail/blocked/needs_human`, pas de N/A silencieux).

L'idée est solide et bien délimitée : le vrai différenciateur n'est pas « appeler plusieurs modèles » mais la discipline autour — artefacts privés auditables, sémantique d'échec stricte, contrôle de concurrence cross-process, et surtout la boucle benchmark-driven qui gouverne chaque changement.

## 2. L'exécution

### Points forts

- **Sécurité de conception remarquable** : allowlist stricte des subprocess (Codex et Ollama natif interdits), fichiers traités comme données non fiables, artefacts en `0700/0600`, invariant « aucun mosaic ne déclenche un autre mosaic ». Aucun secret en clair détecté (clés API via env, `.env` gitignored et absent du disque).
- **Zéro dépendance tierce** : `mosaic.py` est stdlib pure — surface d'attaque et fragilité minimales.
- **Tests** : ~130-149 tests pytest couvrant cas adversariaux, concurrence, fallbacks Windows, contrats de prompt, pipeline SOTA. Portes pytest+ruff+smoke avant chaque scoring.
- **Discipline de benchmark exemplaire** : golden set figé et versionné (v1.0.9), juge gelé, scorers déterministes séparés du LLM-juge (anti self-preference), hash de comparabilité, rebaseline imposé à chaque bump, bruit estimé (stdev 0.221 sur cheap), reverts documentés dans `BENCHLOG.md` quand un gain s'avère être du reward-hacking de forme.
- **Documentation forte** : `mos-tools/ARCHITECTURE.md` (diagrammes mermaid), docs de conception phase1/phase2 avec raisonnement anti-biais explicite.

### Points faibles / dette

- **Monolithe** : `mosaic/mosaic.py` fait 4 443 lignes (~90 fonctions, dont ~1 150 lignes de SOTA). Le refactor en modules (config/runner/sessions/sota/cli/adapters) est déjà identifié dans `ARCHITECTURE.md` mais pas fait. C'est le chantier n°1.
- **Kimi instable** : le run `20260709T193229Z-v1.0.0-cheap-kimi` a timeout à 900 s sur `opencode-go/kimi-k2.7-code`, laissé un run incomplet dans `benchmarks/results/` et un process provider orphelin. Hangs répétés notés dans BENCHLOG.
- **Locks orphelins** : 3 locks résiduels dans `.mosaic/locks/` — `opencode_go.0.lock` (pid 56372, timestamp exact du crash kimi du 9 juillet), `minimax.0.lock` et `opencode_total.0.lock` (10 juillet). Le cleanup de locks après crash n'est pas automatique.
- **Rename advisor → mosaic incomplet** : chemins `advisor-artifacts/`, « Contrat advisor: » et `/home/sina/advisor-dev/` persistent dans les vieux artefacts et certains chemins. Sans impact fonctionnel mais source de confusion.
- **Décalage de doc** : `mosaic.py` en version 0.6.2, README référençant des notes de validation 0.6.0.
- **Windows natif expérimental** : verrous via `msvcrt` OK, mais le cleanup de timeout ne tue que le process direct (pas de Job Object / `taskkill /T`) — WSL reste la plateforme recommandée par le README.

### Ce que disent les benchmarks

27 runs. Les axes 2-4 (SOTA 20, infra 25, coût/latence 10) sont saturés à 55/55 en permanence — seul l'axe qualité (45 pts) discrimine. Baseline officiel courant : **91.093/100** (v1.0.9 full-minimax). Lecture critique honnête, d'ailleurs assumée dans BENCHLOG :

- La plupart des variations de score (~87.5 → 94) viennent de recalibrations du benchmark, pas d'améliorations produit. Le saut +6 pts en v1.0.6 est un artefact de mesure reconnu.
- L'expérience A/B prompt v1.0.7 a été correctement rejetée : le gain apparent venait de la saturation des cas réels, la détection sur cas injectés régressait.
- Vrai échec live : `injected-prompt-injection-007` en v1.0.9 — recall=0, score 0.31 (MiniMax n'a pas détecté l'injection de prompt). C'est le miss le plus significatif et un axe d'amélioration réel.
- Le bruit du profil full n'est pas caractérisé (un seul run full par version).

## 3. Dossiers liés

Identifiés depuis le repo (non accessibles dans cette session, limitée à `mosaic-dev`) :

- `~/.config/mosaic/mosaic.py` — le mosaic **stable** (WSL), cible du symlink `~/.local/bin/mosaic`.
- `~/.config/mosaic-dev/` — config dev (dans le repo).
- `/home/sina/advisor-dev/` — ancien nom du projet, référencé dans les artefacts v1.0.0 ; existe peut-être encore comme dossier legacy.
- Plugin `mos-tools` installé côté Codex (emplacement d'installation à confirmer).

**Version Windows native : aucune trace visible.** Le code a des fallbacks Windows (locks `msvcrt`, tests dédiés) mais le support est explicitement expérimental. Pour une version Windows à jour, il faudrait : (1) un miroir du repo sur NTFS (clone git, pas copie), (2) régler le kill d'arborescence de process sous Windows (Job Objects ou `taskkill /F /T`), (3) vérifier la dispo des CLIs providers (opencode, claude) côté Windows, (4) un run de benchmark full comme gate de parité avant tout usage.

## 4. Verdict et priorités

Projet d'une maturité méthodologique rare pour un outil personnel : sécurité pensée en amont, tests étendus, benchmark versionné avec garde-fous anti-reward-hacking et auto-critique documentée. L'idée est bonne et l'exécution au-dessus du standard.

Priorités suggérées, dans l'ordre :

1. **Refactor du monolithe** en modules (déjà identifié, jamais fait — le coût de maintenance croît avec chaque feature).
2. **Cleanup automatique des locks orphelins** au démarrage (détection pid mort) + purge du run kimi incomplet dans `results/`.
3. **Décision sur kimi** : fix du timeout/hang opencode-go ou retrait de la chaîne de fallback.
4. **Finir le rename advisor → mosaic** (chemins d'artefacts, contrats) + aligner la doc sur 0.6.2.
5. **Durcir la détection de prompt-injection** (le seul vrai échec live du benchmark).
6. **Portage Windows natif** selon le plan ci-dessus, avec benchmark de parité.
