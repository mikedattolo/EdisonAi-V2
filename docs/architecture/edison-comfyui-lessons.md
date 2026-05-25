# EDISON-ComfyUI Lessons To Reuse

Research source: `mikedattolo/EDISON-ComfyUI`.

## Reusable Architecture Ideas

- Keep ComfyUI as a separate service and integrate through HTTP, not by embedding it inside the core API.
- Add a `ComfyWorkflowRunner` contract that can discover templates, validate metadata, inject variables, submit jobs, poll status, cancel jobs, and return setup-required details when nodes or models are missing.
- Use versioned workflow templates with Edison metadata and placeholders such as `source_segment_path`, `source_frame_path`, `persona_paths`, `output_path`, `quality_preset`, `segment_id`, `gpu_index`, and `gpu_name`.
- Track all generation work through a unified job lifecycle: `queued`, `loading`, `generating`, `encoding`, `complete`, `error`, `cancelled`.
- Keep media APIs consistent across image, video, music, and mesh generation, with job detail, list, cancel, and result endpoints.
- Preserve artifact provenance: prompt, workflow template, model, seed, source file, output path, and backend status.

## Setup And Operations Ideas

- Add a doctor command that checks CUDA, GPU visibility, Python packages, model directories, ComfyUI install, custom nodes, service ports, and optional accelerators.
- Keep media setup scripts idempotent and dry-run capable.
- Accept Hugging Face tokens from environment variables such as `HF_TOKEN` or `HUGGINGFACE_TOKEN`; never store them in the repo.
- Separate install bundles: vision, image, video, and optional 3D.
- Install ComfyUI-Manager by default for workflow maintenance.
- Keep FLUX model setup explicit because Black Forest Labs models require license acceptance and Hugging Face authentication.

## ComfyUI Features To Bring Forward

- Edison custom nodes for `EDISON Chat` and `EDISON Health Check` so ComfyUI workflows can call back into Edison safely.
- Image editing fallback behavior: use ComfyUI when available, but return clear fallback/setup-required states when it is not.
- Video helper stack: AnimateDiff Evolved, VideoHelperSuite, `imageio`, `imageio-ffmpeg`, `opencv-python-headless`, and `ffmpeg`.
- 3D hooks should start as configurable repo/model URLs rather than hardcoded claims of support.
- Remote node ideas from the node-agent docs should inform the future Node Manager, especially for CAD/Blender/Rhino-style workers.

## V2 Implementation Targets

1. Add media job tables and artifact records.
2. Add a ComfyUI service adapter with template discovery and validation.
3. Add setup-required status payloads for missing models or nodes.
4. Add a doctor/status endpoint before adding one-click installs.
5. Add Edison ComfyUI custom nodes after the core chat and health contracts stabilize.