# EDISON V2 Roadmap

## Phase 0: Audit And Architecture

- Audit current repository structure.
- Document missing systems and immediate risks.
- Define the first monorepo layout and service boundaries.

## Phase 1: Core Foundation

- Add local configuration scaffolding.
- Add FastAPI core service.
- Add health and system-status endpoints.
- Add model registry/router abstractions.
- Add model gateway behavior for OpenAI-compatible local model servers.
- Add persistent conversation and message storage.
- Add session-state persistence.
- Add first React workbench shell.
- Add tests for storage, routing, and health behavior.
- Add artifact, generation job, job event, and ComfyUI status foundations.
- Add Code Space workspace browsing, project scan, file preview, search, diff preview, approved patch apply, and approval-gated command runs.
- Add instruction hierarchy support (repository, path-specific, and AGENTS context) and semantic workspace indexing/search.

## Phase 2: Memory And Chat Experience

- Add user memory and project memory tables.
- Add memory retrieval and inspection endpoints.
- Add chat history search and conversation rename/archive actions.
- Connect a configured local model adapter for real assistant responses.

## Phase 3: Agent Engine

- Add agent run records, state machine, task plans, checkpoints, events, and approval requests.
- Add progress event streaming.
- Add durable retry/recovery paths.

## Phase 4: Web Research

- Add search provider adapters.
- Add page fetch/extraction pipeline.
- Add source metadata, citations, and browser activity timeline.

## Phase 5: Coding Agent

- Add workspace registry and multi-root repo scanner.
- Persist and optimize semantic index snapshots for large repositories.
- Persist policy-checked patch proposals, approvals, and apply history.
- Expand command/test runner with saved presets, streaming output, and validation history.
- Add patch summaries and rollback metadata.
- Connect coding tools to chat context and agent runs.

## Phase 6: Media Studio

- Add artifact registry.
- Add media job queue.
- Add ComfyUI workflow runner adapter.
- Add output gallery and metadata inspection.

## Phase 7: Voice Mode

- Add STT/TTS adapter interfaces.
- Add voice session state.
- Add transcript and speaking/listening status UI.

## Phase 8: Swarm Mode

- Add specialist agent roles.
- Add task decomposition and cross-agent review.
- Add swarm timeline UI.

## Phase 9: Distributed Nodes

- Add node registry and heartbeat.
- Add remote worker auth.
- Add safe job dispatch and artifact return.

## Phase 10: Reliability And Packaging

- Add deployment docs.
- Add observability and metrics.
- Add backups and migration tooling.
- Add desktop packaging path if desired.