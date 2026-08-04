# Open Argos

Open Argos ajoute aux agents de code des workflows multi-fournisseurs bornés
et auditables. Codex ou Claude Code garde le contrôle ; Argos sollicite des CLI
externes indépendants pour relire, critiquer, planifier, rechercher ou tenir un
conseil persistant, puis conserve les preuves localement.

Version candidate actuelle : **0.9.1-rc1**.

[Installation MCP](docs/MCP_INSTALL.md) ·
[Compatibilité](docs/COMPATIBILITY.md) ·
[Démonstrations](docs/SHOWCASE.md) ·
[Plan pré-1.0](docs/PRE_1_0_RELEASE_PLAN.md)

## Installation

Prérequis : Python 3.10+, `uv`, et au moins un CLI fournisseur installé et
authentifié dans le même environnement qu’Argos.

```bash
git clone https://github.com/anuiit/open-argos.git
cd open-argos
pipx install .
# ou : uv tool install .

argos --version
argos init-config
argos doctor --json
argos-mcp --prepare --json
```

Enregistrez ensuite le même serveur MCP dans les deux clients si nécessaire :

```bash
codex mcp add argos -- argos-mcp
claude mcp add argos --scope local -- argos-mcp
```

Windows natif et WSL doivent avoir deux installations distinctes. En revanche,
Codex et Claude Code partagent bien le même binaire, la même configuration et
les mêmes artefacts lorsqu’ils tournent dans le même environnement OS.

## Exemple concret

```bash
argos run review \
  "Trouve les blocages de correction et de sécurité, avec fichiers et tests." \
  --dir . --include "**/*.py" \
  --argos fable --argos kimi3 --synthesize --json
```

La différence avec une réponse mono-modèle n’est pas « plus de texte » : Argos
conserve des avis indépendants, les désaccords, les statuts d’échec et les
artefacts vérifiables. Le protocole A/B reproductible est décrit dans
[docs/SHOWCASE.md](docs/SHOWCASE.md).

## Données envoyées

Seuls les fichiers explicitement sélectionnés peuvent être transmis. Les
secrets, binaires, métadonnées Git, états locaux d’agents, caches et le dossier
`benchmarks/` sont exclus par défaut lors d’un `--dir`. Un fichier de benchmark
non secret peut encore être ajouté volontairement avec `--file`.

Les racines par défaut sont `~/.config/argos`, `~/.argos/sessions` et
`~/.argos/locks`. Dans un sandbox, définissez `ARGOS_CONFIG_DIR`,
`ARGOS_ARTIFACT_ROOT` et `ARGOS_LOCK_ROOT` vers des dossiers accessibles avant
le lancement.

Le README anglais reste la référence pour les commandes, les noms de champs et
les contrats machine. Les guides français sont des traductions d’usage.

## Licence

Open Argos est distribué sous [licence MIT](LICENSE).
