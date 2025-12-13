#!/usr/bin/env bash
# MultiRig runner for macOS/Linux/Raspberry Pi
# - Creates a local virtualenv if needed and installs deps
# - Starts the FastAPI app with uvicorn

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Configurable via env
PYTHON_BIN="${PYTHON:-python3}"
VENV_DIR="${VENV:-.venv}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"

ensure_venv() {
  if [[ ! -d "$VENV_DIR" ]]; then
    echo "[MultiRig] Creating virtualenv at $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
    if [[ -f "pyproject.toml" ]]; then
      echo "[MultiRig] Installing project (editable)"
      "$VENV_DIR/bin/pip" install -e .
    else
      echo "[MultiRig] Installing requirements"
      "$VENV_DIR/bin/pip" install fastapi "uvicorn[standard]" pydantic pyyaml jinja2
    fi
  fi
}

ensure_venv

if [[ "${REINSTALL_DEPS:-0}" == "1" ]]; then
  echo "[MultiRig] Reinstalling dependencies"
  "$VENV_DIR/bin/pip" install -e .
fi

# Optionally open browser (best-effort) after a short delay
if [[ "$OPEN_BROWSER" == "1" ]]; then
  (
    sleep 1
    URL="http://localhost:${PORT}"
    if command -v open >/dev/null 2>&1; then open "$URL" >/dev/null 2>&1 || true; fi
    if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true; fi
  ) &
fi

echo "[MultiRig] Starting server on ${HOST}:${PORT}"
exec "$VENV_DIR/bin/python" -m uvicorn multirig.app:create_app --factory --host "$HOST" --port "$PORT"
