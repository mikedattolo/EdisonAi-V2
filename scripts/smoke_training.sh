#!/usr/bin/env bash
# Short end-to-end LoRA training smoke test (#23): 20 steps on one GPU.
set -uo pipefail
API=http://127.0.0.1:8000/api/v1/creator-lab

echo "=== clear any prior Train Smoke dataset ==="
curl -s "$API/datasets" | python3 -c "import sys,json;[print(d['id']) for d in json.load(sys.stdin) if d['name']=='Train Smoke']" \
  | while read -r id; do [ -n "$id" ] && curl -s -X DELETE "$API/datasets/$id" >/dev/null && echo "deleted $id"; done

echo "=== create dataset ==="
DS=$(curl -s -X POST "$API/datasets" -H 'Content-Type: application/json' \
  -d '{"name":"Train Smoke","lora_type":"sdxl","trigger_token":"smoke_persona"}')
DSID=$(echo "$DS" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "dataset: $DSID"

echo "=== upload 4 training images ==="
for i in 1 2 3 4; do cp /tmp/creator_test.png /tmp/creator_test_$i.png; done
curl -s -X POST "$API/datasets/$DSID/images" \
  -F 'files=@/tmp/creator_test_1.png' -F 'files=@/tmp/creator_test_2.png' \
  -F 'files=@/tmp/creator_test_3.png' -F 'files=@/tmp/creator_test_4.png' \
  | python3 -c "import sys,json;print('images:',json.load(sys.stdin)['image_count'])"

echo "=== start training (100 steps, GPU 2, dim 8) ==="
JOB=$(curl -s -X POST "$API/training/start" -H 'Content-Type: application/json' \
  -d "{\"dataset_id\":\"$DSID\",\"steps\":100,\"network_dim\":8,\"resolution\":1024,\"gpu_ids\":[2]}")
echo "$JOB" | python3 -c "import sys,json;d=json.load(sys.stdin);print('job:',d.get('id'),'| status',d.get('status'),'| detail',d.get('detail') or d.get('detail'))"
JOBID=$(echo "$JOB" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
if [ -z "$JOBID" ]; then echo "START FAILED:"; echo "$JOB"; exit 1; fi

echo "=== poll up to ~6 min ==="
for n in $(seq 1 36); do
  sleep 10
  J=$(curl -s "$API/training/jobs/$JOBID")
  ST=$(echo "$J" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['current_step'],d['total_steps'],round(d['progress']*100))" 2>/dev/null)
  echo "[$((n*10))s] $ST"
  STATUS=$(echo "$ST" | awk '{print $1}')
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "cancelled" ]; then
    echo "=== final log tail ==="
    echo "$J" | python3 -c "import sys,json;[print(l) for l in json.load(sys.stdin)['log_tail'][-18:]]"
    break
  fi
done

echo "=== output lora? ==="
ls -lh /srv/edison-data/creator_lab/outputs/$JOBID/output/ 2>/dev/null
ls -lh /srv/edison-data/comfyui/ComfyUI/models/loras/ 2>/dev/null | tail -3

echo "=== cleanup dataset (keep job for inspection) ==="
curl -s -X DELETE "$API/datasets/$DSID" >/dev/null && echo "dataset deleted"
