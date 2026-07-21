#!/usr/bin/env bash
# rebaseline.sh — rebaseline officiel post-rename (golden v1.1.0, hashes invalidés).
# Usage (WSL, racine du repo) : bash scripts/rebaseline.sh [cheap|full]   (défaut: full)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PROFILE="${1:-full}"

echo "== gates pré-rebaseline =="
python3 -m pytest -q argos/tests tests argos-tools/tests
./bin/argos-dev benchmark --json >/dev/null && echo "internal benchmark: OK"

echo "== bench $PROFILE (golden v1.1.0) =="
python3 scripts/bench_argos_quality.py --profile "$PROFILE"

latest="$(ls -1dt benchmarks/results/*/ 2>/dev/null | head -1)"
echo "== résultat: $latest"
if [ -n "$latest" ] && [ -f "$latest/report.md" ]; then
  sed -n '1,40p' "$latest/report.md"
fi

echo ""
echo "Ensuite :"
echo " 1. Ajoute l'entrée de rebaseline dans BENCHLOG.md (baseline officiel v1.1.0, run: $latest)"
echo " 2. Resynchronise le miroir Windows : bash scripts/migrate-to-argos.sh"
