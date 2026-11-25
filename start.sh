#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x .venv/bin/python ]]; then
    PYTHON=".venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

if [[ -f data/app.pid ]] && kill -0 "$(cat data/app.pid)" 2>/dev/null; then
  echo "BTC chart ya esta activo en http://localhost:8790"
else
  nohup "$PYTHON" app.py > data/app.log 2>&1 &
  echo $! > data/app.pid
  ready=0
  for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:8790/ >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 0.5
  done
  if [[ "$ready" != "1" ]]; then
    echo "No se pudo iniciar BTC chart. Ultimas lineas del log:"
    tail -n 20 data/app.log
    exit 1
  fi
  echo "BTC chart iniciado en http://localhost:8790"
fi

if [[ "${NO_OPEN:-0}" != "1" ]] && command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://localhost:8790 >/dev/null 2>&1 &
fi
