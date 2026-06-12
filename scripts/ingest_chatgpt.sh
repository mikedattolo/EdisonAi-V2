#!/usr/bin/env bash
# Ingest a (split) ChatGPT export's conversations-*.json files into Edison's
# knowledge base via the local API (bypasses the browser upload-size limit).
set -uo pipefail
DIR="${1:-/tmp/chatgpt}"
cd "$DIR" || { echo "no dir $DIR"; exit 1; }
count=$(ls conversations-*.json 2>/dev/null | wc -l)
echo "ingesting $count conversation files from $DIR"
total=0
for f in conversations-*.json; do
  res=$(curl -s --max-time 300 -X POST http://127.0.0.1:8000/api/v1/knowledge/ingest/chat-export \
    -F "source=chatgpt" -F "files=@${f}")
  n=$(printf '%s' "$res" | python3 -c 'import sys,json
try:
    print(json.load(sys.stdin).get("imported_count", 0))
except Exception:
    print(0)' 2>/dev/null || echo 0)
  total=$((total + n))
  echo "$(date +%H:%M:%S) ${f} -> imported ${n} (running total ${total})"
done
echo "INGEST_DONE total_imported=${total}"
