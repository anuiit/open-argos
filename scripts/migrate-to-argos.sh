#!/usr/bin/env bash
# migrate-to-argos.sh — finalise le rename mosaic -> open-argos :
#   1) renames physiques (git mv) alignés sur les contenus déjà transformés
#   2) purge des résidus (caches, locks orphelins, run kimi échoué, advisor-artifacts, .bak stables)
#   3) gates (JSON, compile, pytest, ruff)
#   4) miroir Windows natif -> F:\dev\open-argos (parité WSL <-> Windows)
# Usage (depuis WSL, à la racine du repo) :
#   bash scripts/migrate-to-argos.sh [--no-mirror] [--no-purge-stable]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MIRROR_DEST="/mnt/f/dev/open-argos"
DO_MIRROR=1
DO_PURGE_STABLE=1
for arg in "$@"; do
  case "$arg" in
    --no-mirror) DO_MIRROR=0 ;;
    --no-purge-stable) DO_PURGE_STABLE=0 ;;
    *) echo "option inconnue: $arg" >&2; exit 2 ;;
  esac
done

echo "== open-argos migration =="

git_mv_if() {
  if [ -e "$1" ] && [ ! -e "$2" ]; then
    if git mv "$1" "$2" 2>/dev/null; then
      echo "renamed (git): $1 -> $2"
    else
      echo "AVERTISSEMENT: git mv a échoué pour $1 (non tracké ?) — fallback mv hors index git" >&2
      mv "$1" "$2"
      echo "renamed (mv): $1 -> $2"
    fi
  fi
}

# 1) Renames physiques
git_mv_if mosaic argos
git_mv_if argos/mosaic.py argos/argos.py
git_mv_if argos/tests/test_mosaic.py argos/tests/test_argos.py
git_mv_if bin/mosaic-dev bin/argos-dev
git_mv_if scripts/bench_mosaic_quality.py scripts/bench_argos_quality.py
git_mv_if tests/test_bench_mosaic_quality.py tests/test_bench_argos_quality.py
git_mv_if mos-tools argos-tools
if [ -d argos-tools ]; then
  for s in review critique plan vision sota config gate doctor; do
    git_mv_if "argos-tools/skills/mos-$s" "argos-tools/skills/argos-$s"
  done
  git_mv_if argos-tools/scripts/smoke_mos_tools.py argos-tools/scripts/smoke_argos_tools.py
  git_mv_if argos-tools/scripts/adversarial_smoke_mos_tools.py argos-tools/scripts/adversarial_smoke_argos_tools.py
  git_mv_if argos-tools/tests/test_smoke_mos_tools.py argos-tools/tests/test_smoke_argos_tools.py
  git_mv_if argos-tools/references/mosaic-context-contract.md argos-tools/references/argos-context-contract.md
fi
git_mv_if .config/mosaic-dev .config/argos-dev
if [ -d .mosaic ] && [ ! -d .argos ]; then mv .mosaic .argos; echo "renamed: .mosaic -> .argos"; fi
chmod +x bin/argos-dev bin/argos-dev.ps1 scripts/migrate-to-argos.sh 2>/dev/null || true

# 2) Purge
echo "== purge =="
find . -type d -name __pycache__ -not -path "./.git/*" -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf .pytest_cache .ruff_cache
rm -f .argos/locks/*.lock 2>/dev/null || true
rm -rf "benchmarks/results/20260709T193229Z-v1.0.0-cheap-kimi" 2>/dev/null || true
find benchmarks/results -mindepth 1 -maxdepth 2 -type d -name advisor-artifacts -prune -exec rm -rf {} + 2>/dev/null || true
if [ "$DO_PURGE_STABLE" = "1" ] && [ -d "$HOME/.config/mosaic" ]; then
  echo "-- purge des *.bak* de l'install stable (~/.config/mosaic)"
  find "$HOME/.config/mosaic" -maxdepth 2 -name '*.bak*' -print -delete 2>/dev/null || true
fi

# 3) Gates
echo "== gates =="
python3 -m json.tool benchmarks/golden/v1/manifest.json >/dev/null && echo "manifest.json: JSON OK"
python3 -m json.tool benchmarks/frozen/judge-v1.json >/dev/null && echo "judge-v1.json: JSON OK"
python3 -m json.tool argos-tools/.codex-plugin/plugin.json >/dev/null && echo "plugin.json: JSON OK"
python3 -m compileall -q argos/argos.py scripts/bench_argos_quality.py && echo "compile: OK"
if python3 -m pytest -q argos/tests tests argos-tools/tests; then
  echo "pytest: OK"
else
  echo "PYTEST FAILED — corrige avant de synchroniser le miroir (relance ensuite ce script)." >&2
  exit 3
fi
if command -v ruff >/dev/null 2>&1; then
  ruff check argos scripts tests argos-tools || echo "ruff: warnings (non bloquant)"
fi

# 4) Miroir Windows natif (parité WSL <-> Windows)
if [ "$DO_MIRROR" = "1" ]; then
  echo "== miroir Windows: $MIRROR_DEST =="
  if [ -d "$MIRROR_DEST/.git" ]; then
    # Clone git détecté côté F: — on ne rsync JAMAIS par-dessus un clone
    # (ça salit l'arbre de travail et bloque les git pull suivants).
    echo "-- clone git détecté : sync via git (nécessite commit+push préalables)"
    if git -C "$MIRROR_DEST" pull --ff-only 2>/dev/null; then
      echo "git pull OK côté F:."
    else
      echo "git pull impossible depuis WSL (ownership drvfs ou arbre sale) — fais côté Windows :"
      echo "  git -C F:\\dev\\open-argos pull --ff-only"
      echo "  (arbre sale suite à un ancien rsync ? git -C F:\\dev\\open-argos reset --hard origin/main)"
    fi
  elif [ -d /mnt/f/dev ]; then
    mkdir -p "$MIRROR_DEST"
    # .git est EXCLU : rsync ne peut pas remplacer les objets git en lecture seule
    # sur NTFS/drvfs (Permission denied). Le repo git côté Windows doit être un
    # vrai clone : git clone https://github.com/anuiit/open-argos.git (une fois),
    # mis à jour via git pull ; ce rsync n'aligne que l'arbre de travail.
    rsync -a --delete \
      --exclude '.git/' \
      --exclude '.native-windows-validated.json' \
      --exclude '.argos/' \
      --exclude '.omc/' \
      --exclude '.pytest_cache/' \
      --exclude '.ruff_cache/' \
      --exclude '__pycache__/' \
      --exclude 'benchmarks/results/' \
      ./ "$MIRROR_DEST"/
    echo "Miroir synchronisé (arbre de travail, .git exclu)."
    echo "Côté Windows : F:\\dev\\open-argos\\bin\\argos-dev.cmd (ou .ps1) — nécessite Python 3 dans le PATH."
  else
    echo "ATTENTION: /mnt/f/dev introuvable — monte F: ou relance avec --no-mirror." >&2
  fi
fi

echo "== terminé =="
echo "Rappels :"
echo " - Rebaseline benchmark REQUIS (golden v1.1.0, hashes invalidés par le rename) :"
echo "     python3 scripts/bench_argos_quality.py --profile full"
echo " - Resynchroniser le miroir après chaque changement : bash scripts/migrate-to-argos.sh (idempotent)"
echo " - L'install stable ~/.config/mosaic garde l'ancien nom ; promotion vers argos = validation humaine."
