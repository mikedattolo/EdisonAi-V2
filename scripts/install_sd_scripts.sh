#!/usr/bin/env bash
# Install kohya sd-scripts for multi-GPU SDXL LoRA training on Edison.
# Reuses ComfyUI's torch (cu130) via a layered venv so we don't redownload
# multi-GB CUDA wheels and don't disturb the running ComfyUI service.
set -uxo pipefail

TRAIN=/srv/edison-data/training
COMFY_PY=/srv/edison-data/comfyui/ComfyUI/.venv/bin/python

mkdir -p "$TRAIN"
cd "$TRAIN"

# 1. sd-scripts source
if [ ! -d sd-scripts/.git ]; then
  git clone --depth 1 https://github.com/kohya-ss/sd-scripts.git
fi
cd sd-scripts

# 2. Layered venv: inherits ComfyUI's torch/CUDA, installs training deps on top.
if [ ! -x .venv/bin/python ]; then
  "$COMFY_PY" -m venv --system-site-packages .venv
fi
PY=.venv/bin/python

"$PY" -m pip install --upgrade pip wheel setuptools

# 3. Training deps (torch intentionally NOT installed - inherited from ComfyUI).
"$PY" -m pip install \
  "accelerate>=0.33" "transformers>=4.44" "diffusers>=0.31" \
  safetensors einops ftfy "huggingface_hub>=0.24" \
  opencv-python-headless toml voluptuous rich \
  prodigyopt lion-pytorch || true

# 4. Optional accelerators - may lack a cu130 wheel; never fatal.
"$PY" -m pip install bitsandbytes || echo "bitsandbytes skipped (no compatible wheel)"

# 5. Default multi-GPU accelerate config (3 GPUs, bf16, no distributed launcher).
mkdir -p "$TRAIN/accelerate"
cat > "$TRAIN/accelerate/multi_gpu.yaml" <<'YAML'
compute_environment: LOCAL_MACHINE
distributed_type: MULTI_GPU
downcast_bf16: 'no'
gpu_ids: all
machine_rank: 0
main_training_function: main
mixed_precision: bf16
num_machines: 1
num_processes: 3
rdzv_backend: static
same_network: true
tpu_use_cluster: false
tpu_use_sudo: false
use_cpu: false
YAML

# 6. Verify the toolchain imports against the inherited torch.
"$PY" -c "import torch,accelerate,transformers,diffusers,safetensors; print('VERIFY torch',torch.__version__,'cuda',torch.version.cuda,'gpus',torch.cuda.device_count(),'accelerate',accelerate.__version__,'diffusers',diffusers.__version__)"

echo "SD_SCRIPTS_INSTALL_DONE"
