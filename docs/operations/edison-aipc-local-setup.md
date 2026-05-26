# Edison AIPC Local Setup

This note captures the local workstation layout used for Mike's Edison V2 AI PC.
It is intentionally operational rather than generic deployment guidance.

## Storage Layout

The 4 TB NVMe boot disk uses LVM for `/`. The root logical volume should consume
the full `ubuntu-vg-1` volume group so the operating system and repository have
roughly 3.5 TB free after install.

The extra drives are pooled for large Edison assets:

- `/dev/nvme0n1p1` - 1 TB NVMe
- `/dev/nvme2n1p1` - 1 TB NVMe
- `/dev/sda1` - 2 TB SATA SSD

Those three devices form `edison-data-vg/edison-data`, formatted as ext4 and
mounted at `/srv/edison-data`.

This data pool maximizes usable capacity. It is not redundant; if one member
disk fails, the pool can be lost. Keep anything irreplaceable backed up outside
this machine.

Expected directories:

```text
/srv/edison-data/artifacts
/srv/edison-data/cache
/srv/edison-data/comfyui
/srv/edison-data/datasets
/srv/edison-data/huggingface
/srv/edison-data/invokeai
/srv/edison-data/logs
/srv/edison-data/modly
/srv/edison-data/models
/srv/edison-data/ollama
/srv/edison-data/tmp
/srv/edison-data/workflows
```

## GPU Cooling

The local GPU fan controller uses the NVIDIA Xorg path so `nvidia-settings` can
hold manual fan targets. Keep these system services active:

```bash
systemctl status edison-gpu-xorg.service --no-pager
systemctl status edison-gpu-fans.timer --no-pager
```

Verify all GPU fans after driver or hardware changes:

```bash
nvidia-smi --query-gpu=index,name,temperature.gpu,fan.speed,power.draw,utilization.gpu --format=csv
DISPLAY=:99 nvidia-settings -q fans
for i in 0 1 2 3 4; do DISPLAY=:99 nvidia-settings -q "[fan:$i]/GPUCurrentFanSpeedRPM"; done
```

## ComfyUI Media Backend

ComfyUI is installed outside the repository at:

```text
/srv/edison-data/comfyui/ComfyUI
```

It runs in its own Python virtual environment and listens on Edison's configured
media adapter URL:

```text
http://127.0.0.1:8188
```

Keep the user service enabled:

```bash
systemctl --user status edison-comfyui.service --no-pager
```

Generated images are written to `/srv/edison-data/artifacts/comfyui`, and ComfyUI
temporary files are written to `/srv/edison-data/tmp/comfyui`.

The first local checkpoint installed for smoke testing and basic image
generation is:

```text
/srv/edison-data/comfyui/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors
```

WAN 2.2 video support is installed through ComfyUI's native workflow templates.
The WAN model set is stored under ComfyUI's model directories:

```text
/srv/edison-data/comfyui/ComfyUI/models/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors
/srv/edison-data/comfyui/ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors
/srv/edison-data/comfyui/ComfyUI/models/vae/wan2.2_vae.safetensors
```

Because WAN is hosted by ComfyUI on this workstation, Edison should use the same
base URL for `wan22_base_url`:

```toml
wan22_base_url = "http://127.0.0.1:8188"
```

## InvokeAI Media Backend

InvokeAI is installed at:

```text
/srv/edison-data/invokeai
```

It listens locally on:

```text
http://127.0.0.1:9090
```

Keep the user service enabled:

```bash
systemctl --user status edison-invokeai.service --no-pager
```

The SDXL checkpoint is registered in-place from ComfyUI so both tools share the
same model file:

```text
/srv/edison-data/comfyui/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors
```

## Modly 3D Backend

Modly is installed at:

```text
/srv/edison-data/modly/modly
```

It listens locally on:

```text
http://127.0.0.1:7070
```

Keep the user service enabled:

```bash
systemctl --user status edison-modly.service --no-pager
```

The Hunyuan3D Mini Fast extension is installed at:

```text
/srv/edison-data/modly/extensions/modly-hunyuan3d-mini-fast-extension
```

Its downloaded model weights live under:

```text
/srv/edison-data/modly/models/hunyuan3d-mini-fast
```

Modly generation is image-to-3D. It expects an image input and returns a mesh
artifact through `/generate/from-image`.

The first Modly generation may look stuck while the background-removal model is
downloaded and cached. After that one-time setup, progress should move through
background removal and shape generation.

## Image Quality Defaults

Edison chat image jobs use the ComfyUI SDXL path by default with 1024x1024
output, 30 steps, `dpmpp_2m`, `karras`, CFG `6.5`, prompt enhancement, and a
stronger negative prompt. Lower these values in job metadata when speed matters
more than quality.

## Ollama Runtime

Ollama is the local OpenAI-compatible runtime for Edison chat and model lanes.
The systemd drop-in should keep model blobs on the data pool:

```ini
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_MODELS=/srv/edison-data/ollama/models"
Environment="OLLAMA_KEEP_ALIVE=15m"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=2"
Environment="OLLAMA_FLASH_ATTENTION=1"
```

Edison model registry profiles can point at `http://127.0.0.1:11434/v1`.
The runtime model aliases used on this workstation are:

```text
local-fast-chat       -> qwen2.5:7b
local-general-chat    -> qwen3:30b
local-coding          -> qwen2.5-coder:32b
local-reasoning       -> qwen3:30b
local-vision          -> qwen2.5vl:7b
local-embeddings      -> bge-m3
```

Qwen3 30B is the default general/reasoning lane for stronger everyday answers.
Qwen 2.5 Coder 32B remains the coding lane. Larger 70B-class models should be
treated as optional experiments rather than the default workstation lane.

## Edison Local Config

`config/edison.local.toml` is intentionally local-only. On this machine it should
keep generated artifacts and workflow assets on the data pool:

```toml
[storage]
database_path = "data/edison.sqlite3"
artifact_root = "/srv/edison-data/artifacts"
log_root = "/srv/edison-data/logs"

[models]
registry_path = "config/model-registry.local.json"

[media]
workflow_root = "/srv/edison-data/workflows"
comfyui_base_url = "http://127.0.0.1:8188"
invokeai_base_url = "http://127.0.0.1:9090"
wan22_base_url = "http://127.0.0.1:8188"
modly_base_url = "http://127.0.0.1:7070"
```

## Chat Delivery

Chat uses server-sent events at `/api/v1/chat/stream` so assistant responses
render progressively instead of waiting for the full response body. Completed
media jobs can be delivered back into a conversation with
`/api/v1/media/jobs/{job_id}/deliver`; the web UI renders attached artifacts as
preview cards inside the assistant message.

The model gateway prepends an Edison system prompt for more polished answers and
filters private `<think>` traces before responses reach the chat UI.

## Starter Knowledge

The starter knowledge/RAG corpus lives under:

```text
/srv/edison-data/datasets/edison-starter-knowledge
```

The manifest records sources ingested into the Edison SQLite knowledge tables.
The current starter corpus combines local Edison repo documentation, selected
Wikipedia extracts, and open documentation pages for FastAPI, Transformers,
PyTorch, and Ollama.

## Validation Commands

```bash
df -hT / /srv/edison-data
ollama list
curl -fsS http://127.0.0.1:8000/api/v1/status | python3 -m json.tool
curl -fsS http://127.0.0.1:8000/api/v1/models | python3 -m json.tool
systemctl status ollama --no-pager
systemctl --user status edison-api.service edison-web.service --no-pager
```
