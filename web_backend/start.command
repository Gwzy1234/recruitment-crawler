#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")/.."
backend_python="$PWD/web_backend/.venv/bin/python"
if [[ ! -x "$backend_python" ]]; then
  python3 -m venv "$PWD/web_backend/.venv"
fi
if ! "$backend_python" -c 'import fastapi, uvicorn, requests, bs4' 2>/dev/null; then
  "$backend_python" -m pip install -r "$PWD/web_backend/requirements.txt"
fi
exec "$backend_python" -m uvicorn web_backend.app:app --host 127.0.0.1 --port "${PORT:-8767}" --workers 1
