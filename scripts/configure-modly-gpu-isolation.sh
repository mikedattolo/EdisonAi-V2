#!/usr/bin/env bash
set -euo pipefail

TARGET_USER="${TARGET_USER:-${SUDO_USER:-$USER}}"
CUDA_VISIBLE_DEVICES_VALUE="${MODLY_CUDA_VISIBLE_DEVICES:-1}"
SYSTEMD_USER_DIR="/home/${TARGET_USER}/.config/systemd/user"
DROPIN_DIR="${SYSTEMD_USER_DIR}/edison-modly.service.d"
DROPIN_PATH="${DROPIN_DIR}/gpu.conf"

mkdir -p "${DROPIN_DIR}"
cat >"${DROPIN_PATH}" <<EOF
[Service]
Environment=CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES_VALUE}
Environment=PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
EOF

chown -R "${TARGET_USER}:${TARGET_USER}" "${DROPIN_DIR}" 2>/dev/null || true

if command -v systemctl >/dev/null 2>&1; then
  target_uid="$(id -u "${TARGET_USER}")"
  if [[ "$(id -un)" == "${TARGET_USER}" ]]; then
    XDG_RUNTIME_DIR="/run/user/${target_uid}" systemctl --user daemon-reload
    XDG_RUNTIME_DIR="/run/user/${target_uid}" systemctl --user restart edison-modly.service
  else
    sudo -u "${TARGET_USER}" XDG_RUNTIME_DIR="/run/user/${target_uid}" systemctl --user daemon-reload
    sudo -u "${TARGET_USER}" XDG_RUNTIME_DIR="/run/user/${target_uid}" systemctl --user restart edison-modly.service
  fi
fi

echo "Configured Modly to use CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES_VALUE}."
