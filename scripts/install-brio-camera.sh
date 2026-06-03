#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash scripts/install-brio-camera.sh" >&2
  exit 1
fi

TARGET_USER="${EDISON_CAMERA_USER:-${SUDO_USER:-mike}}"
EDISON_HOME="${EDISON_HOME:-/home/${TARGET_USER}/EdisonAi-V2}"

apt-get update
apt-get install -y acl ffmpeg gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-tools v4l-utils

usermod -aG video "${TARGET_USER}"

cat >/etc/udev/rules.d/90-edison-brio.rules <<'RULE'
SUBSYSTEM=="video4linux", ATTRS{idVendor}=="046d", ATTRS{idProduct}=="085e", GROUP="video", MODE="0660", TAG+="uaccess"
SUBSYSTEM=="media", ATTRS{idVendor}=="046d", ATTRS{idProduct}=="085e", GROUP="video", MODE="0660", TAG+="uaccess"
RULE

udevadm control --reload-rules
udevadm trigger --subsystem-match=video4linux || true
udevadm trigger --subsystem-match=media || true

if compgen -G "/dev/video*" >/dev/null || compgen -G "/dev/media*" >/dev/null; then
  setfacl -m "u:${TARGET_USER}:rw" /dev/video* /dev/media* 2>/dev/null || true
fi

install -d -o "${TARGET_USER}" -g "${TARGET_USER}" "${EDISON_HOME}/artifacts/camera"

echo "Brio camera support installed for ${TARGET_USER}."
echo "Log out and back in, or restart Edison services, so the video group is visible to long-running processes."
v4l2-ctl --list-devices || true
