# EDISON V2 Model And Media Strategy

## Model Routing Principle

EDISON should not be hardcoded to one model forever. The model gateway should route by lane and capability, with profiles stored in the model registry.

## First Local Model Lanes

| Lane | First Choice | Purpose |
| --- | --- | --- |
| Primary LLM | Qwen2.5-Coder 32B Instruct | Coding, tool use, structured outputs, and strong general local chat. |
| Fast LLM | Qwen2.5 7B/14B Instruct or a Qwen3 small model | Instant responses, routing, summarization, and lightweight chat. |
| Reasoning LLM | Qwen2.5 72B Instruct or another larger reasoning profile when installed | Planning, architecture, hard debugging, and multi-step tasks. |
| Primary VLM | Qwen2.5-VL 7B Instruct first, larger VLM later if useful | Screenshots, UI review, images, documents, OCR-like tasks, and visual grounding. |
| Embeddings | Local embedding model | Memory, project recall, semantic search, and RAG. |
| Reranker | Local reranker model | Higher quality memory and document retrieval. |

The RTX 3090 should be the default heavy model GPU. The 16 GB GPUs should handle fast models, auxiliary inference, embeddings, media preprocess, and secondary queues. Do not assume pooled VRAM unless the selected runtime explicitly supports tensor or pipeline parallelism.

## Inference Runtime Direction

- Start with OpenAI-compatible local servers because the API can already route to them.
- Support vLLM or SGLang for high-throughput model serving where compatible.
- Support llama.cpp/GGUF servers for smaller or quantized local models.
- Keep per-model context limits, GPU preference, provider, readiness, and endpoint URL in the registry.

## Media Stack

| Capability | Recommended Foundation | Notes |
| --- | --- | --- |
| Image generation | ComfyUI with FLUX.1 and SDXL workflows | FLUX for high-quality generations, SDXL for speed and broad workflow compatibility. |
| Image editing | ComfyUI inpaint, ControlNet, IP-Adapter, SAM, background removal | Route editing as versioned media jobs tied to source artifacts. |
| Video generation | LTX/Wan candidates, CogVideoX, Stable Video Diffusion, and AnimateDiff through ComfyUI/diffusers | Use queueing and exclusive GPU render mode for heavy jobs. |
| Upscaling/restoration | ComfyUI upscalers and restoration nodes | Keep output metadata and prompt/workflow provenance. |
| 3D generation | TripoSR, Stable Fast 3D, InstantMesh, and Blender automation hooks | Treat 3D as an artifact pipeline for GLB, OBJ, and STL; do not promise production-quality meshes from day one. |

## Hugging Face Candidates Checked

| Area | Candidate IDs | Notes |
| --- | --- | --- |
| Coding/general LLM | `Qwen/Qwen2.5-Coder-32B-Instruct`, `Qwen/Qwen2.5-72B-Instruct` | Good primary and larger-lane candidates; serve through OpenAI-compatible local runtimes. |
| Vision-language | `Qwen/Qwen2.5-VL-7B-Instruct` | Practical first VLM for screenshots, image QA, and document/page inspection. |
| Image generation | `black-forest-labs/FLUX.1-schnell`, `black-forest-labs/FLUX.1-dev` | Strong image base; requires Hugging Face token/license acceptance. |
| Video generation | `Lightricks/LTX-2.3`, `Wan-AI/Wan2.1-T2V-1.3B-Diffusers`, `THUDM/CogVideoX-5b`, `stabilityai/stable-video-diffusion-img2vid-xt` | Keep as pluggable backends because video model support changes quickly. |
| Audio/music | `facebook/musicgen-small`, `facebook/musicgen-medium` | Optional future media lane after image/video job infrastructure lands. |
| 3D | `TencentARC/InstantMesh`, `stabilityai/stable-fast-3d` | Start as image-to-3D artifact workflows with Blender cleanup hooks. |

For the broader Hugging Face model and Spaces shortlist, see `docs/architecture/huggingface-watchlist.md`.

## EDISON-ComfyUI Lessons

See `docs/architecture/edison-comfyui-lessons.md` for reusable workflow, setup, doctor, custom-node, and generation-job ideas from the existing EDISON-ComfyUI repository.

## Implementation Order

1. Add artifact registry and media job records.
2. Add GPU resource manager job reservations.
3. Add ComfyUI workflow runner adapter.
4. Add image generation and image editing jobs.
5. Add video jobs with exclusive GPU render mode.
6. Add 3D artifact generation hooks and Blender post-processing.