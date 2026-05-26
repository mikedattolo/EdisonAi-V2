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
/srv/edison-data/logs
/srv/edison-data/models
/srv/edison-data/ollama
/srv/edison-data/tmp
/srv/edison-data/workflows
```

## GPU Cooling

The local GPU fan controller uses the NVIDIA Xorg path so `nvidia-settings` can
hold manual fan targets. Keep these services active:

```bash
systemctl --user status edison-gpu-xorg.service --no-pager
systemctl --user status edison-gpu-fans.timer --no-pager
```

Verify all GPU fans after driver or hardware changes:

```bash
nvidia-smi --query-gpu=index,name,temperature.gpu,fan.speed,power.draw,utilization.gpu --format=csv
```

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
local-general-chat    -> qwen2.5-coder:32b
local-coding          -> qwen2.5-coder:32b
local-reasoning       -> qwen2.5-coder:32b
local-vision          -> qwen2.5vl:7b
local-embeddings      -> bge-m3
```

The 32B lane is the practical heavy model for the 24 GB RTX 3090 plus two 16 GB
GPUs. Larger 70B-class models should be treated as optional experiments rather
than the default workstation lane.

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
```

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
