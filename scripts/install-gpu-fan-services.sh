#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run with sudo: sudo bash scripts/install-gpu-fan-services.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDISON_HOME="${1:-$(cd "$SCRIPT_DIR/.." && pwd)}"
TEMPLATE_DIR="$EDISON_HOME/deploy/systemd"
FAN_ENV_FILE=/etc/default/edison-gpu-fans

for command in nvidia-smi nvidia-settings nvidia-xconfig Xorg systemctl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
done

install -m 0755 "$EDISON_HOME/scripts/edison-set-gpu-fans.sh" /usr/local/sbin/edison-set-gpu-fans
install -m 0644 "$TEMPLATE_DIR/edison-gpu-xorg.service.in" /etc/systemd/system/edison-gpu-xorg.service
install -m 0644 "$TEMPLATE_DIR/edison-gpu-fans.service.in" /etc/systemd/system/edison-gpu-fans.service
install -m 0644 "$TEMPLATE_DIR/edison-gpu-fans.timer.in" /etc/systemd/system/edison-gpu-fans.timer

if [[ ! -f "$FAN_ENV_FILE" ]]; then
  cat > "$FAN_ENV_FILE" <<'EOF'
# Fan target percentages are indexed by NVIDIA fan target: fan:0, fan:1, ...
# Edison V2's reference three-GPU workstation uses five exposed fan targets.
EDISON_GPU_FAN_DISPLAY=:99
EDISON_GPU_FAN_DEFAULT_SPEED=35
EDISON_GPU_FAN_TARGETS="35 35 35 50 50"
EDISON_GPU_FAN_KICK_SPEED=50
EDISON_GPU_FAN_KICK_SECONDS=4
EOF
fi

stamp="$(date +%Y%m%d-%H%M%S)"
if [[ -f /etc/X11/xorg.conf ]]; then
  cp -a /etc/X11/xorg.conf "/etc/X11/xorg.conf.bak-${stamp}"
fi

nvidia-xconfig \
  --enable-all-gpus \
  --cool-bits=28 \
  --allow-empty-initial-configuration \
  --use-display-device=None \
  --virtual=640x480

systemctl daemon-reload
systemctl enable --now edison-gpu-xorg.service edison-gpu-fans.timer
systemctl restart edison-gpu-xorg.service
systemctl start edison-gpu-fans.service

cat <<EOF
Installed Edison GPU fan services.

Status:
  systemctl status edison-gpu-xorg.service
  systemctl status edison-gpu-fans.timer

Fan targets:
  $FAN_ENV_FILE

Telemetry:
  nvidia-smi --query-gpu=index,name,fan.speed,temperature.gpu --format=csv
EOF
