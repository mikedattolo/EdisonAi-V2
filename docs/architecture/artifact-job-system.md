# Artifact And Job System

## Purpose

Artifacts and jobs are the shared backbone for media generation, document exports, coding tasks, browser research deliverables, voice outputs, and agent runs.

## Current Foundation

The API now has persistent records for:

- `artifacts`: generated or imported outputs with type, path, MIME type, source job, metadata, and timestamp.
- `generation_jobs`: long-running or backend-dependent work with type, status, prompt, backend, source/result artifact links, metadata, and timestamps.
- `job_events`: append-only status history for each job.

## Job Lifecycle

The foundation uses the lifecycle from the EDISON-ComfyUI research pass:

```text
queued -> loading -> generating -> encoding -> complete
                           \-> error
any active state -> cancelled
missing backend -> setup_required
```

## API Surface

- `GET /api/v1/artifacts`
- `POST /api/v1/jobs`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/cancel`
- `GET /api/v1/jobs/{job_id}/events`
- `GET /api/v1/media/status`
- `POST /api/v1/media/jobs`

## ComfyUI Status Adapter

`GET /api/v1/media/status` checks ComfyUI through `/system_stats` and `/queue`. If ComfyUI is not configured or unreachable, Edison returns `setup_required` or `offline` honestly instead of pretending generation is available.

`POST /api/v1/media/jobs` currently creates a tracked media job and records setup-required details when ComfyUI is unavailable. The next implementation step is to submit validated workflow templates to ComfyUI when the backend is ready.

## Next Steps

1. Add workflow template discovery and metadata validation.
2. Add required custom node/model checks.
3. Add ComfyUI submit, poll, cancel, and result collection.
4. Create artifacts from generated output paths.
5. Stream job events to the UI.
6. Add GPU reservations and exclusive render mode.