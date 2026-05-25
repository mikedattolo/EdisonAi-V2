#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDISON_HOME="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ ! -x "$EDISON_HOME/.venv/bin/uvicorn" ]]; then
  echo "Missing $EDISON_HOME/.venv/bin/uvicorn" >&2
  echo "Install the API first:" >&2
  echo "  cd $EDISON_HOME" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  source .venv/bin/activate" >&2
  echo "  python -m pip install --upgrade pip" >&2
  echo "  python -m pip install -e \".[dev]\"" >&2
  exit 1
fi

if [[ ! -d "$EDISON_HOME/apps/web/node_modules" ]]; then
  echo "Missing $EDISON_HOME/apps/web/node_modules" >&2
  echo "Install the web dependencies first:" >&2
  echo "  cd $EDISON_HOME/apps/web && npm install" >&2
  exit 1
fi

if [[ ! -f "$EDISON_HOME/config/edison.local.toml" ]]; then
  cp "$EDISON_HOME/config/edison.example.toml" "$EDISON_HOME/config/edison.local.toml"
fi

if [[ ! -f "$EDISON_HOME/config/model-registry.local.json" ]]; then
  cp "$EDISON_HOME/config/model-registry.example.json" "$EDISON_HOME/config/model-registry.local.json"
fi

export EDISON_CONFIG_PATH="$EDISON_HOME/config/edison.local.toml"
export EDISON_MODEL_REGISTRY_PATH="$EDISON_HOME/config/model-registry.local.json"

cleanup() {
  if [[ -n "${api_pid:-}" ]]; then
    kill "$api_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cd "$EDISON_HOME"
"$EDISON_HOME/.venv/bin/uvicorn" edison_core.main:create_app \
  --factory \
  --reload \
  --app-dir "$EDISON_HOME/apps/api" \
  --host 0.0.0.0 \
  --port 8000 &
api_pid=$!

cd "$EDISON_HOME/apps/web"
echo "Edison API: http://127.0.0.1:8000"
echo "Edison Web: http://127.0.0.1:5173"
echo "In Codespaces or a remote dev container, open the forwarded port 5173 URL from VS Code's Ports view."
npm run dev -- --host 0.0.0.0 --port 5173