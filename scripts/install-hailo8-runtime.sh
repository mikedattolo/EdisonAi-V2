#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo HAILO_PACKAGE_DIR=/path/to/packages bash scripts/install-hailo8-runtime.sh" >&2
  exit 1
fi

TARGET_USER="${EDISON_HAILO_USER:-${SUDO_USER:-mike}}"
PACKAGE_DIR="${HAILO_PACKAGE_DIR:-/opt/edison/hailo-packages}"
HAILO_VENV="${HAILO_VENV:-/srv/edison-data/hailo/venv}"

apt-get update
apt-get install -y build-essential dkms linux-headers-"$(uname -r)" pciutils python3-pip python3-venv

if ! lspci -nn | grep -Eiq 'Hailo|1e60:2864'; then
  echo "Warning: no Hailo-8 PCIe device was detected by lspci." >&2
fi

if [[ ! -d "${PACKAGE_DIR}" ]]; then
  cat >&2 <<EOF
Hailo package directory not found: ${PACKAGE_DIR}

Download the Hailo-8 x86_64 Ubuntu packages from the Hailo Developer Zone and
place them in that directory first:
  - hailort-pcie-driver_<version>_all.deb
  - hailort_<version>_amd64.deb
  - optional hailo-tappas-core_<version>_amd64.deb
  - optional hailort Python wheel
  - optional hailo_tappas_core_python_binding Python wheel
EOF
  exit 2
fi

shopt -s nullglob
driver_debs=("${PACKAGE_DIR}"/hailort-pcie-driver*.deb)
runtime_debs=("${PACKAGE_DIR}"/hailort_*_amd64.deb "${PACKAGE_DIR}"/hailort-[0-9]*_amd64.deb)
tappas_debs=("${PACKAGE_DIR}"/hailo-tappas-core*.deb)
python_wheels=("${PACKAGE_DIR}"/hailort-*.whl "${PACKAGE_DIR}"/hailo_tappas_core_python_binding*.whl)

if [[ ${#driver_debs[@]} -eq 0 || ${#runtime_debs[@]} -eq 0 ]]; then
  cat >&2 <<EOF
Missing required Hailo packages in ${PACKAGE_DIR}.

At minimum Edison needs:
  - hailort-pcie-driver_<version>_all.deb
  - hailort_<version>_amd64.deb
EOF
  exit 2
fi

dpkg -i "${driver_debs[@]}" "${runtime_debs[@]}" "${tappas_debs[@]}" || apt-get install -f -y

python3 -m venv "${HAILO_VENV}" --system-site-packages
"${HAILO_VENV}/bin/python" -m pip install --upgrade pip
if [[ ${#python_wheels[@]} -gt 0 ]]; then
  "${HAILO_VENV}/bin/python" -m pip install "${python_wheels[@]}"
else
  echo "No Hailo Python wheels found in ${PACKAGE_DIR}; system runtime install will still be verified."
fi

if command -v modprobe >/dev/null 2>&1; then
  modprobe hailo_pci 2>/dev/null || modprobe hailo 2>/dev/null || true
fi

udevadm settle || true
usermod -aG video "${TARGET_USER}" || true

if command -v hailortcli >/dev/null 2>&1; then
  hailortcli fw-control identify
else
  echo "hailortcli was not found after package installation." >&2
  exit 3
fi

echo "Hailo-8 runtime installed and verified."
