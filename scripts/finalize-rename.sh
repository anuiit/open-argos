#!/usr/bin/env bash
# finalize-rename.sh — dernière étape du rename mosaic -> open-argos :
#   1) promotion de l'install stable : ~/.config/mosaic -> ~/.config/argos (core 0.7.0 validé,
#      rebaseline v1.1.0 = 93.73/100), symlink ~/.local/bin/argos, backup de l'ancien stable
#   2) commit + push vers origin (github.com/anuiit/open-argos)
#   3) resync du miroir Windows F:\dev\open-argos
#   4) rename du dossier repo : ~/mosaic-dev -> ~/open-argos (en dernier)
# Usage (WSL, racine du repo) : bash scripts/finalize-rename.sh [--no-promote] [--no-push]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DO_PROMOTE=1
DO_PUSH=1
for arg in "$@"; do
  case "$arg" in
    --no-promote) DO_PROMOTE=0 ;;
    --no-push) DO_PUSH=0 ;;
    *) echo "option inconnue: $arg" >&2; exit 2 ;;
  esac
done

# 1) Promotion stable (remplace l'install legacy mosaic 0.6.2 par argos 0.7.0)
if [ "$DO_PROMOTE" = "1" ]; then
  echo "== promotion stable: ~/.config/argos (core 0.7.0, rebaseline v1.1.0: 93.731649/100) =="
  read -r -p "Confirmer la promotion du stable (remplace ~/.config/mosaic, backup créé) ? [y/N] " ok
  if [ "${ok:-n}" = "y" ] || [ "${ok:-n}" = "Y" ]; then
    ts="$(date +%Y%m%dT%H%M%S)"
    backup="$HOME/backup-mosaic-stable-$ts.tgz"
    tar czf "$backup" -C "$HOME" \
      $( [ -d "$HOME/.config/mosaic" ] && echo ".config/mosaic" ) \
      $( [ -e "$HOME/.local/bin/mosaic" ] && echo ".local/bin/mosaic" ) 2>/dev/null || true
    echo "backup: $backup"

    mkdir -p "$HOME/.config/argos/tests" "$HOME/.local/bin"
    install -m 0755 argos/argos.py "$HOME/.config/argos/argos.py"
    cp argos/tests/test_argos.py "$HOME/.config/argos/tests/test_argos.py"
    if [ -f "$HOME/.config/mosaic/config.json" ]; then
      # migre la config en renommant la seule clé structurelle affectée par le rename
      sed 's/"mosaics":/"argoses":/g' "$HOME/.config/mosaic/config.json" > "$HOME/.config/argos/config.json"
    fi
    if [ -f "$HOME/.config/mosaic/.env" ]; then
      cp "$HOME/.config/mosaic/.env" "$HOME/.config/argos/.env" && chmod 600 "$HOME/.config/argos/.env"
    fi
    ln -sf "$HOME/.config/argos/argos.py" "$HOME/.local/bin/argos"

    echo "-- smoke du stable promu :"
    if "$HOME/.local/bin/argos" doctor --json >/dev/null; then
      echo "argos doctor: OK — suppression de l'ancien stable mosaic"
      rm -rf "$HOME/.config/mosaic"
      rm -f "$HOME/.local/bin/mosaic"
    else
      echo "ATTENTION: argos doctor a échoué — ancien stable mosaic CONSERVÉ. Vérifie ~/.config/argos/config.json." >&2
    fi
  else
    echo "promotion sautée."
  fi
fi

# 2) Commit + push
echo "== commit + push =="
# restaure les bits exécutables perdus par les éditions côté Windows
chmod +x argos/argos.py bin/argos-dev bin/argos-dev.ps1 scripts/*.sh scripts/bench_argos_quality.py argos-tools/scripts/*.py 2>/dev/null || true
git add -A
if git diff --cached --quiet; then
  echo "rien à committer."
else
  git commit -m "rename: mosaic -> open-argos (argos CLI 0.7.0), native Windows parity, rebaseline v1.1.0 (93.73/100)"
fi
if [ "$DO_PUSH" = "1" ]; then
  git push origin main
  echo "pushed -> $(git remote get-url origin)"
fi

# 3) Miroir Windows
bash scripts/migrate-to-argos.sh --no-purge-stable

# 4) Rename du dossier repo (EN DERNIER — change tous les chemins)
if [ "$(basename "$ROOT")" = "mosaic-dev" ] && [ ! -e "$HOME/open-argos" ]; then
  echo "== rename du dossier repo: $ROOT -> $HOME/open-argos =="
  cd "$HOME"
  mv "$ROOT" "$HOME/open-argos"
  echo ""
  echo "FAIT. Le repo vit maintenant dans ~/open-argos."
  echo "IMPORTANT : reconnecte le dossier dans Cowork/Claude :"
  echo "  \\\\wsl.localhost\\ubuntu-24.04\\home\\sina\\open-argos"
  echo "Les prochains syncs : cd ~/open-argos && bash scripts/migrate-to-argos.sh"
else
  echo "dossier repo déjà renommé (ou ~/open-argos existe) — rien à faire."
fi

echo "== terminé =="
