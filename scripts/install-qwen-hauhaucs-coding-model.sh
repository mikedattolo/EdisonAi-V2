#!/usr/bin/env bash
set -euo pipefail

REPO_ID="${REPO_ID:-HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive}"
MODEL_ROOT="${MODEL_ROOT:-/srv/edison-data/models/huggingface/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive}"
ALLOW_PATTERN="${ALLOW_PATTERN:-*Q4_K_M*.gguf}"
PORT="${PORT:-8014}"

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
