#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f data/app.pid ]] && kill -0 "$(cat data/app.pid)" 2>/dev/null; then
  kill "$(cat data/app.pid)"
  rm -f data/app.pid
  echo "BTC chart detenido"
else
  rm -f data/app.pid
  echo "BTC chart no estaba activo"
fi
