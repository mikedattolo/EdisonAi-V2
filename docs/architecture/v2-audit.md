# EDISON V2 Repository Audit

## Current State

The repository currently contains only documentation-level source material:

- `README.md` with the project name.
- `EDISON_V2_Master_Copilot_Prompt.md` with the full product, architecture, and phased build prompt.

There are no existing backend entrypoints, frontend files, ComfyUI integrations, model-management modules, memory stores, agent engines, tests, package manifests, or runtime configuration files to preserve.

## Existing Entrypoints

- Backend: none detected.
- Frontend: none detected.
- Tests: none detected.
- Config: none detected.
- CI/build scripts: none detected.

## Reuse Candidates

- The master prompt is the canonical product brief and should remain as the source of truth for long-term scope.
- The repository name and README establish the V2 project identity.

## Gaps To Fill First

- Add a real project layout.
- Add safe local configuration defaults.
- Add a core API foundation with health/status endpoints.
- Add model registry and routing abstractions without assuming a configured local model server.
- Add persistent conversation and session-state storage.
- Add tests that verify core behavior.
- Add a first frontend workbench shell that targets the API.

## Risks

- The product vision is broad enough to invite a giant first commit. The first implementation should stay inside Phase 1 boundaries.
- Local model and GPU availability will vary. The platform must report unconfigured services honestly rather than pretending inference is available.
- Future coding, browser, media, and shell tools need permission and audit boundaries from the beginning.

## Initial Decision

Start with an additive monorepo structure:

- `apps/api` for the FastAPI core service.
- `apps/web` for the React workbench UI.
- `config` for local-first configuration and model registry examples.
- `docs` for architecture and roadmap material.
- `tests` for foundation validation.