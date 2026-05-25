# Hugging Face AI And Tool Watchlist

Snapshot source: Hugging Face public APIs queried during the EDISON V2 build. Download and like counts change over time, so treat this as a living shortlist rather than a locked dependency list.

## Selection Rules

- Prefer local-first models that can run through an OpenAI-compatible server, ComfyUI, diffusers, transformers, sentence-transformers, or a small dedicated service.
- Favor models with strong adoption, clear library support, and realistic hardware fit for the Edison AI PC.
- Treat Hugging Face Spaces as reference demos and integration ideas, not production dependencies.
- Keep gated/license-required models explicit and require user-provided tokens through environment variables.

## Core LLM And VLM Picks

| Edison Lane | Model | Task | Library | Why It Matters |
| --- | --- | --- | --- | --- |
| Primary coding/general LLM | `Qwen/Qwen2.5-Coder-32B-Instruct` | text-generation | transformers | Best first local workhorse for coding, tool use, structured output, and general chat. |
| Heavy reasoning/general LLM | `Qwen/Qwen2.5-72B-Instruct` | text-generation | transformers | Bigger lane for deep planning and harder reasoning when hardware/runtime can handle it. |
| Primary VLM | `Qwen/Qwen2.5-VL-7B-Instruct` | image-text-to-text | transformers | Practical first visual model for screenshots, image QA, document pages, and UI inspection. |
| Multimodal alternative | `microsoft/Phi-4-multimodal-instruct` | image-text-to-text | transformers | Useful comparison point for lighter multimodal experiments. |
| OCR specialist | `zai-org/GLM-OCR` | image-to-text | transformers | Candidate for document/screenshot OCR workflows if VLM OCR is not enough. |

Qwen3 model IDs checked during this pass were not consistently available through the public API, so keep them as a recheck item rather than wiring them now.

## Memory, RAG, And Retrieval

| Use | Model | Task | Why It Matters |
| --- | --- | --- | --- |
| Baseline embeddings | `sentence-transformers/all-MiniLM-L6-v2` | sentence-similarity | Very high adoption and fast enough for baseline local semantic memory. |
| Strong multilingual embeddings | `BAAI/bge-m3` | sentence-similarity | Better long-term candidate for project memory, RAG, and mixed document collections. |
| Reranking | `BAAI/bge-reranker-v2-m3` | text-classification | Useful second-stage retrieval quality boost for memory and document search. |

## Image, Video, Audio, And 3D

| Capability | Model | Task | Notes |
| --- | --- | --- | --- |
| Fast image generation | `black-forest-labs/FLUX.1-schnell` | text-to-image | First FLUX lane for faster local generation; requires license/token handling. |
| High-quality image generation | `black-forest-labs/FLUX.1-dev` | text-to-image | Higher-quality FLUX lane; should run through ComfyUI workflow templates. |
| Compatibility image base | `stabilityai/stable-diffusion-xl-base-1.0` | text-to-image | Broad ecosystem support and useful fallback for SDXL workflows. |
| Text-to-video | `Lightricks/LTX-2.3` | text-to-video | Trending video candidate and worth tracking for local video studio workflows. |
| Text-to-video | `Wan-AI/Wan2.1-T2V-1.3B-Diffusers` | text-to-video | Promising lighter Wan lane; keep pluggable because video moves quickly. |
| Text-to-video | `THUDM/CogVideoX-5b` | text-to-video | Established diffusers candidate for video generation experiments. |
| Image-to-video | `stabilityai/stable-video-diffusion-img2vid-xt` | image-to-video | Strong candidate for animating generated images and storyboards. |
| Speech-to-text | `openai/whisper-large-v3` | automatic-speech-recognition | High-quality local transcription lane. |
| Fast speech-to-text | `openai/whisper-large-v3-turbo` | automatic-speech-recognition | Lower latency voice mode candidate. |
| Text-to-speech | `hexgrad/Kokoro-82M` | text-to-speech | Strong lightweight TTS candidate for Edison voice output. |
| Music/audio | `facebook/musicgen-small`, `facebook/musicgen-medium` | text-to-audio | Future media studio lane after core artifact/job flow lands. |
| Image-to-3D | `TencentARC/InstantMesh` | image-to-3d | Good first 3D artifact workflow candidate. |
| Image-to-3D | `stabilityai/stable-fast-3d` | image-to-3d | Fast 3D candidate; watch gated/license status. |
| Image-to-3D | `tencent/Hunyuan3D-2.1` | image-to-3d | Trending 3D candidate to compare with InstantMesh and Stable Fast 3D. |

## Useful Spaces And Tool Demos

| Area | Space | Why It Matters |
| --- | --- | --- |
| FLUX image workflows | `black-forest-labs/FLUX.1-dev` | Reference demo for prompt behavior and output quality. |
| ComfyUI demo | `kadirnar/ComfyUI-Demo` | Reference for hosted ComfyUI UX and workflow exposure. |
| Video generation | `Wan-AI/Wan2.2-Animate` | Strong signal for Wan video tooling direction. |
| Video studio | `techfreakworm/LTX2.3-Studio` | Useful UX reference for LTX-style video controls. |
| TTS | `hexgrad/Kokoro-TTS` | Reference for lightweight voice output quality and controls. |
| STT | `sanchit-gandhi/whisper-jax` | Reference for Whisper transcription UX/performance patterns. |
| Agents | `smolagents/computer-agent` | Useful reference for browser/computer-use agent patterns. |
| 3D | `tencent/Hunyuan3D-2.1` | Reference demo for image-to-3D output expectations. |
| 3D | `TencentARC/Pixal3D` | Trending 3D demo to monitor. |
| Qwen voice/tools | `Qwen/Qwen3-TTS` | Track for future Qwen voice/model ecosystem options. |

## Edison Integration Priority

1. Wire `Qwen/Qwen2.5-Coder-32B-Instruct` as the first real ready profile once a local server is installed.
2. Add `Qwen/Qwen2.5-VL-7B-Instruct` as the first vision profile.
3. Add `BAAI/bge-m3` plus `BAAI/bge-reranker-v2-m3` before serious memory/RAG work.
4. Build the media job/artifact layer before adding one-click FLUX installs.
5. Add ComfyUI workflow discovery and setup-required checks before video/3D claims.
6. Add Whisper and Kokoro behind voice service adapters after the chat and memory loop stabilizes.