#!/usr/bin/env bash
set -euo pipefail

REPO_ID="${REPO_ID:-HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive}"
MODEL_ID="${MODEL_ID:-qwen3.6-35b-a3b-hauhaucs-coding}"
MODEL_ROOT="${MODEL_ROOT:-/srv/edison-data/models/huggingface/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive}"
ALLOW_PATTERN="${ALLOW_PATTERN:-*Q4_K_M*.gguf}"
MODEL_PATH="${MODEL_PATH:-$MODEL_ROOT/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf}"
EDISON_HOME="${EDISON_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MODEL_REGISTRY_PATH="${MODEL_REGISTRY_PATH:-$EDISON_HOME/config/model-registry.local.json}"
PORT="${PORT:-8014}"
LLAMA_CPP_TAG="${LLAMA_CPP_TAG:-b9536}"
LLAMA_TOOLS_ROOT="${LLAMA_TOOLS_ROOT:-/srv/edison-data/tools}"
LLAMA_ROOT="${LLAMA_ROOT:-$LLAMA_TOOLS_ROOT/llama.cpp-vulkan-$LLAMA_CPP_TAG}"
LLAMA_ARCHIVE="${LLAMA_ARCHIVE:-$LLAMA_TOOLS_ROOT/llama-$LLAMA_CPP_TAG-bin-ubuntu-vulkan-x64.tar.gz}"
LLAMA_URL="${LLAMA_URL:-https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA_CPP_TAG/llama-$LLAMA_CPP_TAG-bin-ubuntu-vulkan-x64.tar.gz}"
SERVICE_NAME="${SERVICE_NAME:-edison-qwen-coding.service}"
RESTART_EDISON_API="${RESTART_EDISON_API:-1}"

mkdir -p "$MODEL_ROOT" "$LLAMA_TOOLS_ROOT"

if [[ ! -e "$MODEL_PATH" ]]; then
  python3 - <<PY
from pathlib import Path
import subprocess
import sys

repo_id = "$REPO_ID"
model_root = Path("$MODEL_ROOT")
allow_pattern = "$ALLOW_PATTERN"

try:
    from huggingface_hub import snapshot_download
except Exception:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "-U", "huggingface_hub"])
    from huggingface_hub import snapshot_download

snapshot_download(
    repo_id=repo_id,
    local_dir=model_root,
    allow_patterns=[allow_pattern, "*.json", "*.md", "README*"],
    local_dir_use_symlinks=False,
)
ggufs = sorted(model_root.rglob("*.gguf"), key=lambda path: path.stat().st_size, reverse=True)
if not ggufs:
    raise SystemExit(f"No GGUF file matching {allow_pattern!r} was downloaded into {model_root}")
target = Path("$MODEL_PATH")
if target != ggufs[0] and not target.exists():
    target.symlink_to(ggufs[0])
print(target)
PY
fi

if [[ ! -f "$LLAMA_ARCHIVE" ]]; then
  curl -L --fail "$LLAMA_URL" -o "$LLAMA_ARCHIVE"
fi

rm -rf "$LLAMA_ROOT"
mkdir -p "$LLAMA_ROOT"
tar -xzf "$LLAMA_ARCHIVE" -C "$LLAMA_ROOT"

LLAMA_SERVER="$(find "$LLAMA_ROOT" -type f -name llama-server | head -n 1)"
if [[ -z "$LLAMA_SERVER" ]]; then
  echo "llama-server was not found in $LLAMA_ROOT after extracting $LLAMA_ARCHIVE." >&2
  exit 1
fi
chmod +x "$LLAMA_SERVER"
LLAMA_DIR="$(dirname "$LLAMA_SERVER")"

LD_LIBRARY_PATH="$LLAMA_DIR:${LD_LIBRARY_PATH:-}" "$LLAMA_SERVER" --list-devices | grep -q "Vulkan" || {
  echo "No Vulkan GPU backend was detected by llama-server." >&2
  exit 1
}

mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/$SERVICE_NAME" <<EOF
[Unit]
Description=Edison Qwen Coding GPU Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$MODEL_ROOT
Environment=LD_LIBRARY_PATH=$LLAMA_DIR
ExecStart=$LLAMA_SERVER -m $MODEL_PATH --host 127.0.0.1 --port $PORT -c 8192 -np 1 -ngl 999 -sm layer -dev Vulkan2,Vulkan0,Vulkan1 -ts 17,16,11 --reasoning off --reasoning-budget 0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=edison.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"

if [[ ! -f "$MODEL_REGISTRY_PATH" && -f "$EDISON_HOME/config/model-registry.example.json" ]]; then
  cp "$EDISON_HOME/config/model-registry.example.json" "$MODEL_REGISTRY_PATH"
fi

python3 - <<PY
import json
from pathlib import Path

registry_path = Path("$MODEL_REGISTRY_PATH")
profile = {
    "id": "$MODEL_ID",
    "display_name": "Qwen3.6 35B A3B HauhauCS Coding",
    "provider": "local-openai-compatible",
    "status": "ready",
    "capabilities": ["chat", "coding", "tool-calling", "long-context", "JSON-structured-output"],
    "license": "Apache-2.0",
    "tags": ["coding", "repo", "creator-planning", "huggingface", "qwen", "gguf", "llama.cpp", "vulkan", "gpu"],
    "safety_notes": "Use for Code Space edits, creator planning, captions, metadata, and workflow assistance. Keep media generation policies enforced at tool boundaries.",
    "context_window": 8192,
    "max_output_tokens": 4096,
    "endpoint_url": "http://127.0.0.1:$PORT/v1",
    "preferred_gpu": "RTX 3090 + RTX 5060 Ti + RTX 4060 Ti",
    "notes": "Installed as a GPU llama.cpp Vulkan server using $MODEL_PATH."
}
payload = {"models": []}
if registry_path.exists():
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
models = payload.setdefault("models", [])
for index, item in enumerate(models):
    if item.get("id") == profile["id"]:
        models[index] = {**item, **profile}
        break
else:
    models.append(profile)
registry_path.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
print(f"Updated {registry_path}")
PY

if [[ "$RESTART_EDISON_API" == "1" ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl --user restart edison-api.service || true
fi

cat <<EOF
GPU Qwen coding model is ready.

Service:
  $SERVICE_NAME

Endpoint:
  http://127.0.0.1:$PORT/v1

Model:
  $MODEL_PATH
EOF
