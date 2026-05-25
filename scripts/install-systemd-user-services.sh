#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDISON_HOME="${1:-$(cd "$SCRIPT_DIR/.." && pwd)}"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
TEMPLATE_DIR="$EDISON_HOME/deploy/systemd"

if [[ ! -d "$EDISON_HOME" ]]; then
  echo "Edison path does not exist: $EDISON_HOME" >&2
  exit 1
fi

if [[ ! -x "$EDISON_HOME/.venv/bin/uvicorn" ]]; then
  echo "Missing $EDISON_HOME/.venv/bin/uvicorn" >&2
  echo "Run: python3 -m venv .venv && source .venv/bin/activate && python -m pip install -e \".[dev]\"" >&2
  exit 1
fi

if [[ ! -f "$EDISON_HOME/apps/web/package.json" ]]; then
  echo "Missing web package: $EDISON_HOME/apps/web/package.json" >&2
  exit 1
fi

if [[ ! -d "$EDISON_HOME/apps/web/node_modules" ]]; then
  echo "Missing web dependencies: $EDISON_HOME/apps/web/node_modules" >&2
  echo "Run: cd apps/web && npm install && npm run build" >&2
  exit 1
fi

mkdir -p "$SYSTEMD_USER_DIR" "$EDISON_HOME/data" "$EDISON_HOME/artifacts" "$EDISON_HOME/logs"

if [[ ! -f "$EDISON_HOME/config/edison.local.toml" ]]; then
  cp "$EDISON_HOME/config/edison.example.toml" "$EDISON_HOME/config/edison.local.toml"
fi

if [[ ! -f "$EDISON_HOME/config/model-registry.local.json" ]]; then
  cp "$EDISON_HOME/config/model-registry.example.json" "$EDISON_HOME/config/model-registry.local.json"
fi

escaped_home="$(printf '%s' "$EDISON_HOME" | sed 's/[&/]/\\&/g')"

for template in edison-api.service edison-web.service edison.target; do
  sed "s/@EDISON_HOME@/$escaped_home/g" \
    "$TEMPLATE_DIR/$template.in" > "$SYSTEMD_USER_DIR/$template"
done

systemctl --user daemon-reload

cat <<EOF
Installed Edison user services in $SYSTEMD_USER_DIR

Start Edison now:
  systemctl --user enable --now edison.target

Check status:
  systemctl --user status edison-api.service
  systemctl --user status edison-web.service

Follow logs:
  journalctl --user -u edison-api.service -u edison-web.service -f

Start at boot after login sessions end, if desired:
  loginctl enable-linger "$USER"

Open the workbench:
  http://127.0.0.1:5173
EOF