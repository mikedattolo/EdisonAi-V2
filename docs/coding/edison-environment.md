# Edison Environment & Coding Workflow

This is the machine Edison runs on and how to edit, build, run, and ship code here.

## The machine
- OS: Ubuntu Linux (x86_64), hostname `edison`, user `mike`.
- GPU: NVIDIA (CUDA) for model inference; a Hailo-8 PCIe accelerator is also present.
- App repo: `/home/mike/EdisonAi-V2` (this is workspace root `app`). GitHub remote: `https://github.com/mikedattolo/EdisonAi-V2`.
- Large data lives under `/srv/edison-data` (models, ComfyUI, InvokeAI, artifacts, generated projects). User code projects the agent creates live under the configured projects dir.

## Repo layout
- `apps/api/edison_core/` — FastAPI backend (Python). `api/routes_*.py` = HTTP routes, `services/*.py` = logic, `schemas.py` = pydantic models, `main.py` = app wiring, `config.py` = settings.
- `apps/web/` — React + TypeScript frontend built with Vite. `src/App.tsx` holds the views, `src/styles.css` all styles, `src/api.ts` the API client, `src/types.ts` shared types.
- `tests/` — pytest suite. `config/` — TOML/JSON config. `docs/` — documentation (this file lives in `docs/coding/`). `scripts/` — install/setup shell scripts.

## Services (systemd USER units — run as mike, not root)
Set the runtime dir first in a non-login shell: `export XDG_RUNTIME_DIR=/run/user/$(id -u)`.
- `edison-api.service` — FastAPI/uvicorn on `127.0.0.1:8000` (no auto-reload).
- `edison-web.service` — serves the built web app (`vite preview`) on `0.0.0.0:5173`, proxying `/api` → 8000.
- `edison-comfyui`, `edison-invokeai`, `edison-modly`, `edison-qwen-coding` — model/media backends. `edison.target` groups them.
Common commands:
- `systemctl --user status edison-api.service`
- `systemctl --user restart edison-api.service edison-web.service`
- `journalctl --user -u edison-api.service -n 100 --no-pager` (logs / tracebacks)

## Python backend: edit → run
- Interpreter & deps live in the project venv: `/home/mike/EdisonAi-V2/.venv`.
- Run a one-off with the venv Python: `cd ~/EdisonAi-V2 && PYTHONPATH=apps/api .venv/bin/python -c "import edison_core.main"` (a fast way to confirm the backend still imports after an edit).
- Run the API manually (dev): `cd ~/EdisonAi-V2 && .venv/bin/uvicorn edison_core.main:create_app --factory --reload --app-dir apps/api --host 127.0.0.1 --port 8000`.
- Tests: `cd ~/EdisonAi-V2 && .venv/bin/python -m pytest -q` (config in `pyproject.toml` sets `pythonpath=apps/api`).
- **The running `edison-api` does NOT hot-reload.** A backend edit only takes effect after `systemctl --user restart edison-api.service`. Always import-check before restarting so a syntax error never bricks the API.

## Web frontend: edit → build → serve
- Install deps: `cd ~/EdisonAi-V2/apps/web && npm install`.
- Type-check + build: `cd ~/EdisonAi-V2/apps/web && npm run build` (runs `tsc && vite build`, output to `apps/web/dist`).
- Dev server (hot reload): `npm run dev -- --host 0.0.0.0 --port 5173`.
- `edison-web` serves the BUILT `dist/`, so a frontend edit needs `npm run build` AND `systemctl --user restart edison-web.service` to appear. The Code Space "Apply & restart Edison" button does the build + import-check + restart for you.

## Getting dependencies on this box
- Python (app): `cd ~/EdisonAi-V2 && .venv/bin/pip install <pkg>` then add it to `pyproject.toml` `dependencies`.
- Node (web): `cd ~/EdisonAi-V2/apps/web && npm install <pkg>` (adds to `package.json`).
- System packages: `sudo apt update && sudo apt install -y <pkg>` (needs sudo; ask Mike if a password prompt blocks it).
- See `dependency-management.md` for the full per-language cheat sheet.

## Code agent command allowlist
When the Code Agent runs commands they must be approved and are restricted to safe ones: test runners (`pytest`, `npm test`), builds (`npm run ...`), and read-only git (`git status`/`diff`/`log`). Installs and destructive commands are blocked; do file edits + ask Mike for anything outside the allowlist.
