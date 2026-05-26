#!/usr/bin/env bash
set -euo pipefail

DISPLAY="${EDISON_GPU_FAN_DISPLAY:-:99}"
DEFAULT_SPEED="${EDISON_GPU_FAN_DEFAULT_SPEED:-35}"
TARGETS_STRING="${EDISON_GPU_FAN_TARGETS:-35 35 35 50 50}"
KICK_SPEED="${EDISON_GPU_FAN_KICK_SPEED:-50}"
KICK_SECONDS="${EDISON_GPU_FAN_KICK_SECONDS:-4}"
export DISPLAY

if ! command -v nvidia-settings >/dev/null 2>&1; then
  echo "nvidia-settings is required for GPU fan control" >&2
  exit 1
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi is required for GPU fan telemetry" >&2
  exit 1
fi

for _ in $(seq 1 30); do
  if nvidia-settings -q gpus >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

mapfile -t GPU_IDS < <(nvidia-settings -q gpus 2>/dev/null | sed -n 's/.*\[gpu:\([0-9]\+\)\].*/\1/p' | sort -n | uniq)
mapfile -t FAN_IDS < <(nvidia-settings -q fans 2>/dev/null | sed -n 's/.*\[fan:\([0-9]\+\)\].*/\1/p' | sort -n | uniq)
read -r -a TARGETS <<< "$TARGETS_STRING"

if [[ ${#GPU_IDS[@]} -eq 0 || ${#FAN_IDS[@]} -eq 0 ]]; then
  echo "No NVIDIA GPU/fan targets were exposed on DISPLAY=$DISPLAY" >&2
  exit 1
fi

settings_args=()
for gpu_id in "${GPU_IDS[@]}"; do
  settings_args+=( -a "[gpu:${gpu_id}]/GPUFanControlState=1" )
done
nvidia-settings "${settings_args[@]}" >/dev/null

# Many modern cards have a zero-RPM idle mode and need a short kick before
# settling to a lower manual speed, especially when the GPU is cold.
settings_args=()
for fan_id in "${FAN_IDS[@]}"; do
  settings_args+=( -a "[fan:${fan_id}]/GPUTargetFanSpeed=${KICK_SPEED}" )
done
nvidia-settings "${settings_args[@]}" >/dev/null
sleep "$KICK_SECONDS"

settings_args=()
for fan_id in "${FAN_IDS[@]}"; do
  target="${TARGETS[$fan_id]:-$DEFAULT_SPEED}"
  settings_args+=( -a "[fan:${fan_id}]/GPUTargetFanSpeed=${target}" )
done
nvidia-settings "${settings_args[@]}" >/dev/null

sleep 4
nvidia-smi --query-gpu=index,name,fan.speed,temperature.gpu,power.draw,pstate --format=csv,noheader,nounits
