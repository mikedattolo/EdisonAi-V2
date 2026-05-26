# Edison V2 Deployment Guide

This guide covers a practical local deployment for Edison V2: one primary AI workstation running the FastAPI core, React workbench, local storage, model backends, and optional private network access.

## What Edison V2 Is

Edison V2 is a local-first AI workstation. It combines chat, model routing, memory, coding workspace tools, media generation pipelines, artifacts, and system controls behind one operator workbench. The current repository is the foundation layer: it is runnable now, keeps unsafe actions behind approval gates, and exposes clear service boundaries for adding real local model servers, media backends, and remote nodes.

## Production Shape

- FastAPI core API serves `/health`, `/api/v1/status`, chat, workspace, media, knowledge, and system-control endpoints.
- React/Vite workbench is built as static files and can be served by Caddy, Nginx, or another local reverse proxy.
- SQLite stores conversations, session state, media jobs, artifacts metadata, and knowledge indexes.
- Model servers stay local and are registered through `config/model-registry.example.json` or a copied production registry file.
- Remote access should use Tailscale or another private VPN first; avoid public port forwarding by default.

## Host Prerequisites

- Python 3.11 or newer.
- Node.js 20 or newer.
- npm.
- git.
- NVIDIA driver and `nvidia-smi` for GPU telemetry.
- Optional: `nvidia-settings` plus a configured Coolbits/Xorg environment for hardware fan writes.
- Optional media backends: ComfyUI, InvokeAI, WAN 2.2, or Modly.

On Ubuntu 24.04, install the base tools with:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version
npm --version
python3 --version
```

## First-Time Install

Clone the repo onto the machine that will run Edison:

```bash
git clone https://github.com/mikedattolo/EdisonAi-V2.git
cd EdisonAi-V2
```

Install the FastAPI backend and test dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Install and build the React workbench:

```bash
cd apps/web
npm install
npm run build
cd ../..
```

At this point the repository has everything needed to run the local API and web workbench. Model servers and media backends are separate processes; configure them after the base app starts.

## Dev Container Or Codespace Start

Systemd is usually unavailable inside Codespaces, dev containers, and some hosted terminals. In those environments, start Edison with the foreground launcher:

```bash
bash scripts/start-edison-dev.sh
```

The launcher starts the API on port `8000` and the web workbench on port `5173`, both bound to `0.0.0.0` so VS Code can forward them. Open the forwarded port `5173` URL from the VS Code Ports view. If you type `127.0.0.1:5173` into your local browser while Edison is running remotely, it will point at your laptop, not the remote container.

## Install User Services

Edison ships systemd user-service templates and an installer that renders them with your checkout path. Use these on a real Linux workstation with systemd. Run this after the backend virtualenv exists and the web dependencies are installed:

```bash
bash scripts/install-systemd-user-services.sh
```

The installer creates or refreshes these files under `~/.config/systemd/user`:

- `edison-api.service`: runs `uvicorn` from `.venv` for the FastAPI core API.
- `edison-web.service`: runs `npm run preview` for the built React workbench.
- `edison.target`: starts both services as one Edison unit.

It also creates `config/edison.local.toml` and `config/model-registry.local.json` from the examples if they do not already exist.

Activate Edison:

```bash
systemctl --user enable --now edison.target
```

Open the workbench at `http://127.0.0.1:5173` on the workstation, or `http://<workstation-lan-ip>:5173` from another trusted LAN device. The API remains available locally at `http://127.0.0.1:8000`.

If the workstation is remote, open the forwarded `5173` URL or route it through your private reverse proxy/Tailscale URL.

If the installer says systemd user services are unavailable, use:

```bash
bash scripts/start-edison-dev.sh
```

Check service health and logs:

```bash
systemctl --user status edison-api.service
systemctl --user status edison-web.service
journalctl --user -u edison-api.service -u edison-web.service -f
```

Restart or stop Edison:

```bash
systemctl --user restart edison.target
systemctl --user stop edison.target
```

Optional boot persistence for a workstation account:

```bash
loginctl enable-linger "$USER"
```

Use `loginctl disable-linger "$USER"` later if you no longer want user services to run outside active login sessions.

## Updating An Existing Checkout

From an existing Edison checkout:

```bash
cd EdisonAi-V2
git status --short
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

In a dev container, replace the last two lines with:

```bash
bash scripts/start-edison-dev.sh
```

If `git status --short` shows local changes, commit or stash them before pulling.

## Configure

Copy the example config and model registry before editing local deployment values:

```bash
cp config/edison.example.toml config/edison.local.toml
cp config/model-registry.example.json config/model-registry.local.json
```

Set environment variables for the API process:

```bash
export EDISON_CONFIG_PATH="$PWD/config/edison.local.toml"
export EDISON_MODEL_REGISTRY_PATH="$PWD/config/model-registry.local.json"
```

In `config/model-registry.local.json`, set real model profiles to `ready` and point `endpoint_url` at OpenAI-compatible local model servers such as vLLM, llama.cpp server, LM Studio, Ollama-compatible gateways, or another private backend.

## Run The API

Development mode:

```bash
source .venv/bin/activate
export EDISON_CONFIG_PATH="$PWD/config/edison.local.toml"
export EDISON_MODEL_REGISTRY_PATH="$PWD/config/model-registry.local.json"
uvicorn edison_core.main:create_app --factory --reload --app-dir apps/api --host 127.0.0.1 --port 8000
```

Deployment mode:

```bash
source .venv/bin/activate
export EDISON_CONFIG_PATH="$PWD/config/edison.local.toml"
export EDISON_MODEL_REGISTRY_PATH="$PWD/config/model-registry.local.json"
uvicorn edison_core.main:create_app --factory --app-dir apps/api --host 127.0.0.1 --port 8000
```

Health checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/status
```

## Serve The Web Workbench

During development:

```bash
cd apps/web
npm run dev
```

Then open `http://localhost:5173` in a browser.

For remote environments, use the forwarded port `5173` URL from VS Code instead.

When running through `edison-web.service`, the service uses `npm run preview` bound to `0.0.0.0:5173` and proxies `/api` and `/health` to the local API service.

For deployment, serve `apps/web/dist` from a reverse proxy and proxy `/api` to `http://127.0.0.1:8000`. Keep the API bound to localhost unless you are intentionally exposing it on a private interface.

Example Caddy shape:

```caddyfile
edison-v2.localhost {
  root * /absolute/path/to/EdisonAi-V2/apps/web/dist
  file_server

  handle /api/* {
    reverse_proxy 127.0.0.1:8000
  }

  handle /health {
    reverse_proxy 127.0.0.1:8000
  }
}
```

## GPU Fan Control

The System page includes an MSI Afterburner-style multi-GPU fan panel. By default it runs in monitor mode: it reads `nvidia-smi` telemetry, accepts policies through the API, and reports that hardware writes are disabled.

To allow hardware fan writes, the host must support `nvidia-settings` fan control. On a headless NVIDIA workstation, install the optional root-level fan services after the NVIDIA driver stack is installed:

```bash
sudo bash scripts/install-gpu-fan-services.sh
```

The installer creates a headless Xorg control display on `:99`, generates `/etc/X11/xorg.conf` with Coolbits enabled, installs `edison-gpu-xorg.service`, `edison-gpu-fans.service`, and `edison-gpu-fans.timer`, and writes default fan targets to `/etc/default/edison-gpu-fans`. The reference three-GPU Edison workstation exposes five NVIDIA fan targets and uses `35 35 35 50 50` so the RTX 3090 fans reliably spin from cold idle.

After validating that manual fan writes work outside Edison, opt in:

```toml
[hardware]
gpu_fan_control_enabled = true
gpu_fan_control_backend = "nvidia-settings"
```

or use environment variables:

```bash
export EDISON_GPU_FAN_CONTROL_ENABLED=true
export EDISON_GPU_FAN_CONTROL_BACKEND=nvidia-settings
```

Fan writes are intentionally disabled by default because bad fan policies can damage hardware. Start with conservative manual speeds, watch temperatures, and leave remote access private.

## Validation

Run the backend and frontend checks before deploying changes:

```bash
python -m pytest
cd apps/web
npm run build
```

## Private Remote Access

Use Tailscale for remote access instead of public port forwarding. See `docs/operations/tailscale-access.md` for the recommended tailnet shape.
