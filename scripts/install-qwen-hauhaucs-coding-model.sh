#!/usr/bin/env bash
set -euo pipefail

REPO_ID="${REPO_ID:-HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive}"
MODEL_ROOT="${MODEL_ROOT:-/srv/edison-data/models/huggingface/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive}"
ALLOW_PATTERN="${ALLOW_PATTERN:-*Q4_K_M*.gguf}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.6-35b-a3b-hauhaucs-coding}"
HF_OLLAMA_REF="${HF_OLLAMA_REF:-hf.co/${REPO_ID}:Q4_K_M}"
EDISON_HOME="${EDISON_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MODEL_REGISTRY_PATH="${MODEL_REGISTRY_PATH:-$EDISON_HOME/config/model-registry.local.json}"
PORT="${PORT:-8014}"
RESTART_EDISON_API="${RESTART_EDISON_API:-1}"

if command -v ollama >/dev/null 2>&1; then
  echo "Using Ollama for ${HF_OLLAMA_REF}"
  ollama pull "$HF_OLLAMA_REF"

  MODFILE="$(mktemp)"
  cat > "$MODFILE" <<EOF
FROM $HF_OLLAMA_REF
PARAMETER num_ctx 32768
PARAMETER temperature 0.6
PARAMETER top_p 0.95
PARAMETER top_k 20
PARAMETER repeat_penalty 1.0
SYSTEM You are Edison Code Space Copilot. Help with repository edits, product planning, creator workflow planning, and concise implementation guidance.
EOF
  ollama create "$OLLAMA_MODEL" -f "$MODFILE"
  rm -f "$MODFILE"

  if [[ ! -f "$MODEL_REGISTRY_PATH" && -f "$EDISON_HOME/config/model-registry.example.json" ]]; then
    cp "$EDISON_HOME/config/model-registry.example.json" "$MODEL_REGISTRY_PATH"
  fi

  python3 - <<PY
import json
from pathlib import Path

registry_path = Path("$MODEL_REGISTRY_PATH")
profile = {
    "id": "$OLLAMA_MODEL",
    "display_name": "Qwen3.6 35B A3B HauhauCS Coding",
    "provider": "local-openai-compatible",
    "status": "ready",
    "capabilities": ["chat", "coding", "tool-calling", "long-context", "JSON-structured-output"],
    "license": "Apache-2.0",
    "tags": ["coding", "repo", "creator-planning", "huggingface", "qwen", "gguf", "ollama"],
    "safety_notes": "Use for Code Space edits, creator planning, captions, metadata, and workflow assistance. Keep media generation policies enforced at tool boundaries.",
    "context_window": 32768,
    "max_output_tokens": 8192,
    "endpoint_url": "http://127.0.0.1:11434/v1",
    "preferred_gpu": "RTX 3090",
    "notes": "Installed through Ollama from $HF_OLLAMA_REF."
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
Ollama model alias is ready:
  $OLLAMA_MODEL

Edison model registry endpoint:
  http://127.0.0.1:11434/v1

Edison API restart attempted so the ready profile can be reloaded.
EOF
  exit 0
fi

mkdir -p "$MODEL_ROOT"

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
print(ggufs[0])
PY

GGUF_PATH="$(find "$MODEL_ROOT" -type f -name '*.gguf' -printf '%s %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)"

cat <<EOF
Downloaded model candidate:
  $GGUF_PATH

Run with llama.cpp OpenAI-compatible server:
  llama-server -m "$GGUF_PATH" --host 127.0.0.1 --port $PORT -c 32768 -ngl 999

Edison model registry endpoint:
  http://127.0.0.1:$PORT/v1

After the server is running, mark qwen3.6-35b-a3b-hauhaucs-coding ready in your local model registry.
EOF
