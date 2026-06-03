# Hailo-8 and Logitech Brio Setup

This Edison V2 hardware pass targets:

- Hailo-8 PCIe AI accelerator: `1e60:2864`
- Logitech Brio Ultra HD Webcam: `046d:085e`

## Current Edison PC Probe

The Edison PC detected both devices physically:

```text
0a:00.0 Co-processor [0b40]: Hailo Technologies Ltd. Hailo-8 AI Processor [1e60:2864] (rev 01)
Bus 001 Device 007: ID 046d:085e Logitech, Inc. BRIO Ultra HD Webcam
```

The Brio is configured with `v4l-utils`, `ffmpeg`, GStreamer base/good plugins,
udev permissions, and immediate ACLs. A 1280x720 JPEG smoke frame was captured
to:

```text
/home/mike/EdisonAi-V2/artifacts/camera/brio-smoke.jpg
```

The Hailo card is visible on PCIe, but the runtime stack is not installed yet:

- No `/dev/hailo*` device node
- No loaded Hailo kernel module
- No `hailortcli`
- No installed `hailo` or `hailort` packages

Edison reports that as `driver_missing` or `runtime_missing` instead of marking
the accelerator ready.

## Edison API

Hardware status:

```bash
curl http://127.0.0.1:8000/api/v1/hardware/status
```

Capture a Brio frame into Edison artifacts:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/hardware/cameras/snapshot \
  -H 'Content-Type: application/json' \
  -d '{"device_path":"/dev/video0","width":1280,"height":720,"input_format":"mjpeg"}'
```

## Brio Install

Repeat the camera setup with:

```bash
sudo bash scripts/install-brio-camera.sh
```

Then restart Edison services or log out and back in so long-running processes see
the `video` group:

```bash
systemctl restart edison-api.service edison-web.service
```

## Hailo-8 Runtime Install

Hailo's public repositories provide HailoRT and PCIe driver source, but the
x86_64 Ubuntu runtime packages are distributed through the Hailo Developer Zone.
For Hailo-8, use the `hailo8` branch for HailoRT/driver source compatibility.

Stage the official Hailo-8 Ubuntu packages on the Edison PC, for example:

```text
/opt/edison/hailo-packages/hailort-pcie-driver_<version>_all.deb
/opt/edison/hailo-packages/hailort_<version>_amd64.deb
/opt/edison/hailo-packages/hailo-tappas-core_<version>_amd64.deb
/opt/edison/hailo-packages/hailort-<version>-<pytag>-linux_x86_64.whl
/opt/edison/hailo-packages/hailo_tappas_core_python_binding-<version>-py3-none-any.whl
```

Then run:

```bash
sudo HAILO_PACKAGE_DIR=/opt/edison/hailo-packages bash scripts/install-hailo8-runtime.sh
```

Successful verification should show:

```bash
ls /dev/hailo*
hailortcli fw-control identify
```

References:

- Hailo PCIe driver: https://github.com/hailo-ai/hailort-drivers
- HailoRT runtime: https://github.com/hailo-ai/hailort
- Hailo apps installation package list: https://github.com/hailo-ai/hailo-apps/blob/main/doc/user_guide/installation.md
