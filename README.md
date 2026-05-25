# EdisonAi-V2

EDISON V2 is a local-first, modular AI workstation for running an AI operator stack on your own hardware. It brings chat, memory, model routing, agent workflows, coding tools, media pipelines, artifacts, GPU telemetry, and private deployment controls into one workbench.

This repository is the foundation layer: a runnable monorepo with honest local defaults, approval-gated tools, durable storage, and clean service boundaries for connecting real model and media backends.

## What Edison V2 Is About

- Local-first AI operations: keep chats, workspaces, jobs, artifacts, and system controls close to the machine doing the work.
- Practical model routing: select between fast chat, coding, reasoning, vision, and media profiles as local servers come online.
- Operator-grade workspace tooling: inspect repos, search files, preview diffs, apply approved patches, and run approved commands.
- Media and artifact workflows: track image, video, mesh, audio, and code generation jobs through one artifact system.
- Hardware-aware execution: report GPU telemetry and expose safe multi-GPU fan-control policies for local workstations.
- Private access first: deploy behind localhost, a reverse proxy, or a private tailnet instead of exposing the workstation publicly.

## Current Foundation

- FastAPI core API in `apps/api`.
- React workbench shell in `apps/web`.
- Local configuration examples in `config`.
- SQLite-backed conversation and session-state storage.
- Model registry/router scaffolding with honest `not_configured` defaults.
- Chat gateway endpoint that persists user and assistant turns.
- Workspace tools for repo summary, project scan, file browsing, file preview, search, reviewed patch previews, approved patch apply, and approval-gated command runs.
- Artifact and generation job APIs for media/agent deliverables.
- ComfyUI media status adapter with honest setup-required reporting.
- GPU telemetry and safe-by-default multi-GPU fan control API/UI.
- Clickable workbench sections for Chat, Agent, Code, Media, Memory, System, and Settings.
- Collapsible right-side Core inspector.
- Architecture audit and roadmap in `docs`.

## Quick Start From A Fresh Machine

These commands assume Ubuntu 24.04 or another Debian-based Linux host. Edison also works on other systems with Python 3.11+, Node.js 20+, npm, and git installed.

1. Install system prerequisites:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version
python3 --version
```

2. Pull the repository:

```bash
git clone https://github.com/mikedattolo/EdisonAi-V2.git
cd EdisonAi-V2
```

3. Install the Python API:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

4. Install and build the web workbench:

```bash
cd apps/web
npm install
npm run build
cd ../..
```

5. Create local config files:

```bash
cp config/edison.example.toml config/edison.local.toml
cp config/model-registry.example.json config/model-registry.local.json
export EDISON_CONFIG_PATH="$PWD/config/edison.local.toml"
export EDISON_MODEL_REGISTRY_PATH="$PWD/config/model-registry.local.json"
```

6. Run the API and web app in two terminals:

```bash
# Terminal 1, from the repository root
source .venv/bin/activate
export EDISON_CONFIG_PATH="$PWD/config/edison.local.toml"
export EDISON_MODEL_REGISTRY_PATH="$PWD/config/model-registry.local.json"
uvicorn edison_core.main:create_app --factory --reload --app-dir apps/api
```

```bash
# Terminal 2, from the repository root
cd apps/web
npm run dev
```

Open `http://localhost:5173`. The API runs at `http://127.0.0.1:8000`.

## Run As Services

After the first install and build, install systemd user services from the repository root:

```bash
bash scripts/install-systemd-user-services.sh
systemctl --user enable --now edison.target
```

This activates:

- `edison-api.service`: FastAPI core API on `http://127.0.0.1:8000`.
- `edison-web.service`: built web workbench preview on `http://127.0.0.1:5173`.
- `edison.target`: starts and stops both services together.

Useful service commands:

```bash
systemctl --user status edison-api.service
systemctl --user status edison-web.service
journalctl --user -u edison-api.service -u edison-web.service -f
systemctl --user restart edison.target
systemctl --user stop edison.target
```

To allow the user services to start at boot even before an interactive login session:

```bash
loginctl enable-linger "$USER"
```

## Updating An Existing Install

```bash
cd EdisonAi-V2
git pull origin main
source .venv/bin/activate
python -m pip install -e ".[dev]"
cd apps/web
npm install
npm run build
cd ../..
bash scripts/install-systemd-user-services.sh
systemctl --user restart edison.target
```

Use `git status --short` before pulling if you have local edits you want to keep.

## Backend

```bash
source .venv/bin/activate
export EDISON_CONFIG_PATH="$PWD/config/edison.local.toml"
export EDISON_MODEL_REGISTRY_PATH="$PWD/config/model-registry.local.json"
uvicorn edison_core.main:create_app --factory --reload --app-dir apps/api
```

The API starts on `http://127.0.0.1:8000` by default.

Useful endpoints:

- `GET /health` checks the core API process.
- `GET /api/v1/status` reports storage, model, and GPU status.
- `GET /api/v1/models` lists configured model profiles.
- `GET /api/v1/models/select?mode=chat` previews routing for a mode.
- `POST /api/v1/chat` creates a chat turn, stores both messages, and routes through the model gateway.
- `GET /api/v1/workspace/summary` scans the configured repo root for Code Space.
- `GET /api/v1/workspace/scan` detects stack, entrypoints, scripts, test targets, and config files.
- `GET /api/v1/workspace/files` lists workspace folders and files within the allowed root.
- `GET /api/v1/workspace/files/content` previews a text file.
- `POST /api/v1/workspace/search` searches workspace paths and text content.
- `POST /api/v1/workspace/patches/preview` returns a unified diff, stats, hashes, and risk flags.
- `POST /api/v1/workspace/patches/apply` writes the reviewed patch only when `approved` is true.
- `POST /api/v1/workspace/commands/run` executes a detected command only when `approved` is true and records output in job events.
- `GET /api/v1/media/status` reports ComfyUI readiness and media job counts.
- `POST /api/v1/media/jobs` creates a tracked media job and records setup-required details when ComfyUI is unavailable.
- `GET /api/v1/system/fans` reports per-GPU fan telemetry and active fan policies.
- `PUT /api/v1/system/fans/{gpu_index}` stages or applies a fan policy for one GPU.

Model profiles start as `not_configured`. To connect a real local model server, copy `config/model-registry.example.json`, point `EDISON_MODEL_REGISTRY_PATH` at your copy, set a profile `status` to `ready`, and set `endpoint_url` to an OpenAI-compatible base URL such as `http://127.0.0.1:8002/v1`.

## Frontend

```bash
cd apps/web
npm run dev
```

The workbench starts on `http://localhost:5173`. During Vite development it proxies `/api` to the local FastAPI service, which also works cleanly through Codespaces forwarded URLs.

## Deployment

For a local deployment, build the web app and serve `apps/web/dist` through Caddy, Nginx, or another reverse proxy. Proxy `/api` and `/health` to the FastAPI process on `127.0.0.1:8000`. Keep the API private unless you intentionally place it behind a trusted VPN or tailnet.

```bash
cp config/edison.example.toml config/edison.local.toml
cp config/model-registry.example.json config/model-registry.local.json
export EDISON_CONFIG_PATH="$PWD/config/edison.local.toml"
export EDISON_MODEL_REGISTRY_PATH="$PWD/config/model-registry.local.json"
uvicorn edison_core.main:create_app --factory --app-dir apps/api --host 127.0.0.1 --port 8000
```

Full deployment notes are in `docs/operations/deployment.md`.

## GPU Fan Control

The System view includes an MSI Afterburner-style multi-GPU fan panel with per-GPU telemetry, auto/manual/curve modes, target-speed controls, and policy apply actions. It is safe by default: Edison starts in monitor mode and does not write hardware fan settings unless explicitly enabled.

To opt in after validating `nvidia-settings` works on the host:

```toml
[hardware]
gpu_fan_control_enabled = true
gpu_fan_control_backend = "nvidia-settings"
```

or set `EDISON_GPU_FAN_CONTROL_ENABLED=true` and `EDISON_GPU_FAN_CONTROL_BACKEND=nvidia-settings` for the API process.

## Strategy Docs

- Model and media stack: `docs/architecture/model-media-strategy.md`
- Artifact and job system: `docs/architecture/artifact-job-system.md`
- Coding workspace: `docs/architecture/coding-workspace.md`
- Deployment guide: `docs/operations/deployment.md`
- Hugging Face watchlist: `docs/architecture/huggingface-watchlist.md`
- EDISON-ComfyUI reuse notes: `docs/architecture/edison-comfyui-lessons.md`
- Tailscale remote access plan: `docs/operations/tailscale-access.md`

## Tests

```bash
python -m pytest
```

## Project Notes

- Runtime data is intentionally ignored under `data`, `artifacts`, and `logs`.
- Configure real model servers by copying and editing `config/model-registry.example.json`.
- The master prompt remains in `EDISON_V2_Master_Copilot_Prompt.md` as the product source of truth.