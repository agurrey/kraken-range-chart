#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Necesitas Python 3.10 o superior."
  exit 1
fi

python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
mkdir -p data

echo "Instalacion completada. Ejecuta ./start.sh y abre http://localhost:8790"
if ! command -v paplay >/dev/null 2>&1; then
  echo "Aviso: para los sonidos instala pulseaudio-utils (paplay)."
fi
