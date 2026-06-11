#!/usr/bin/env bash
# End-to-end smoke test for Creator Lab (#21 + #22).
set -uo pipefail
API=http://127.0.0.1:8000/api/v1/creator-lab

echo "=== 1. create dataset ==="
DS=$(curl -s -X POST "$API/datasets" -H 'Content-Type: application/json' \
  -d '{"name":"Aria Test","lora_type":"sdxl","trigger_token":"aria_test","notes":"smoke test persona"}')
echo "$DS" | python3 -c "import sys,json;d=json.load(sys.stdin);print('dataset',d['id'],'| trigger',d['trigger_token'],'| status',d['status'])"
DSID=$(echo "$DS" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

echo "=== 2. make a test image (no deps) ==="
python3 - <<'PY'
import zlib, struct
def png(w, h, rgb):
    row = b'\x00' + (bytes(rgb) * w)
    raw = row * h
    def chunk(typ, data):
        body = typ + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw, 9)
    return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')
open('/tmp/creator_test.png', 'wb').write(png(384, 384, (70, 130, 180)))
print('wrote /tmp/creator_test.png')
PY

echo "=== 3. upload image ==="
curl -s -X POST "$API/datasets/$DSID/images" -F 'files=@/tmp/creator_test.png' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('images now:',d['image_count'],'| status',d['status'])"

echo "=== 4. workflow graph (side panel data) ==="
curl -s "$API/workflows/sdxl_txt2img_lora/graph" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('label:',d['label']);print('nodes:',[n['type'] for n in d['nodes']])"

echo "=== 5. VLM critique (qwen2.5-VL) - may take ~20s to load model ==="
IMG=$(curl -s "$API/datasets/$DSID" | python3 -c "import sys,json;print(json.load(sys.stdin)['images'][0]['id'])")
curl -s -X POST "$API/vlm-critique" -H 'Content-Type: application/json' \
  -d "{\"prompt\":\"a solid steel-blue square\",\"dataset_id\":\"$DSID\",\"image_id\":\"$IMG\"}" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('VLM:',d['status'],'| score',d.get('score'),'| matches',d.get('matches'),'| verdict',d.get('verdict'),'| model',d.get('model_id'));print('notes:',(d.get('notes') or '')[:160])"

echo "=== 6. cleanup test dataset ==="
curl -s -X DELETE "$API/datasets/$DSID" | python3 -c "import sys,json;print(json.load(sys.stdin))"

echo "=== install log tail ==="
tail -4 /srv/edison-data/training/install.log 2>/dev/null
