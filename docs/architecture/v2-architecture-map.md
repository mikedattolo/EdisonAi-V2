# EDISON V2 Architecture Map

## Goals For The Foundation

The first foundation layer should make EDISON V2 runnable, inspectable, and extensible. It should not attempt to implement every agent, media, voice, and distributed-node capability immediately.

## Monorepo Layout

```text
apps/
  api/                 FastAPI core API and service modules
  web/                 React workbench UI
config/                Local config and model registry examples
docs/                  Architecture notes, roadmap, operations notes
tests/                 Backend foundation tests
data/                  Local SQLite database, ignored by git
artifacts/             Generated artifacts, ignored by git
logs/                  Runtime logs, ignored by git
```

## Core API Modules

- `config`: loads local-safe defaults, optional TOML settings, and environment overrides.
- `database`: creates and owns the SQLite connection boundary.
- `conversation_store`: persists conversations, messages, and mode metadata.
- `session_state`: stores resumable task/session context.
- `model_registry`: loads model profiles and selects candidate models by mode/capability.
- `model_gateway`: turns selected model profiles into inference calls, starting with OpenAI-compatible local servers.
- `system_status`: reports service health, model registry state, storage paths, and GPU telemetry when available.
- `api.routes`: keeps HTTP route modules separate from service logic.

See `docs/architecture/model-media-strategy.md` and `docs/architecture/huggingface-watchlist.md` for the current model, VLM, media generation, video, 3D, and Hugging Face tool direction. See `docs/architecture/edison-comfyui-lessons.md` for reusable patterns from EDISON-ComfyUI.

See `docs/architecture/artifact-job-system.md` for the shared artifact and generation job foundation.

See `docs/architecture/coding-workspace.md` for the first Code Space workspace tooling layer.

## What Should Be Reused

- The master prompt remains the long-form product specification.
- Future existing Edison modules, if imported later, should be wrapped behind service interfaces rather than rewritten immediately.

## What Should Be Added Now

- FastAPI core service.
- Pydantic schemas for model profiles, inference requests, conversations, messages, session state, and status.
- SQLite-backed conversation/session persistence.
- Model registry/router with explicit `not_configured` model status.
- Model gateway with honest fallback responses when selected local models are not ready.
- Health/status/model/conversation/session endpoints.
- React workbench shell that can display system status, model lanes, chat history, and session state.
- Workspace browsing, project scan, file preview, search, diff preview, approved patch apply, approval-gated command run endpoints, and Code Space UI.
- Repository instruction hierarchy discovery and file-scoped instruction context resolution.
- Workspace semantic index status, rebuild, and scored index search endpoints.

## What Should Be Refactored Later

- Agent execution should become a formal state machine with durable checkpoints.
- Tool execution should become schema-first with approval gates and audit logs.
- Coding tools should be workspace-scoped and policy-checked before any write or command execution.
- Browser/web research should isolate untrusted page content from controlling prompts.
- Media workflows should route through job queues and the GPU resource manager.

## What Should Remain Untouched Initially

- Hardware-specific model assumptions.
- Real shell/file-writing tools beyond the API scaffolding.
- Cloud integrations and external side effects.
- Remote node dispatch.
- ComfyUI execution, until the job queue and GPU scheduler exist.

## Service Direction

EDISON V2 should grow as a set of explicit service boundaries:

- Core API
- Model Gateway
- Memory Service
- Agent Orchestrator
- Tool Registry
- Coding Workspace Service
- Browser Research Service
- Media Generation Service
- Artifact Service
- Voice Service
- Node Manager

Remote private access should use Tailscale first. See `docs/operations/tailscale-access.md`.

The first pass implements the Core API foundation and leaves clean extension points for the rest.