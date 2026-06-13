"""Creality K1 / K1 SE adapter over the stock LAN websocket (port 9999).

Creality's own app and web UI talk to the printer through a JSON websocket on
port 9999, which stock firmware leaves open — so Edison can read live status and
send control commands without rooting the printer or enabling Moonraker."""

from __future__ import annotations

import asyncio
import json

import httpx

try:
    import websockets

    HAVE_WS = True
except ImportError:  # pragma: no cover
    HAVE_WS = False

GCODE_DIR = "/usr/data/printer_data/gcodes"


_STATE = {0: "idle", 1: "printing", 2: "complete", 3: "failed", 4: "paused", 5: "paused"}


def _as_float(value) -> float | None:
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _host_only(host: str) -> str:
    host = (host or "").strip()
    for prefix in ("ws://", "wss://", "http://", "https://"):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host.split("/")[0].split(":")[0]


class CrealityPrinter:
    def __init__(self, host: str) -> None:
        self.host = _host_only(host)
        self.url = f"ws://{self.host}:9999/"

    # --- status ---

    def get_status(self, timeout: float = 6.0) -> dict:
        if not HAVE_WS:
            return {"online": False, "detail": "The websockets library is not installed on the server."}
        if not self.host:
            return {"online": False, "detail": "Missing host/IP."}
        try:
            data = asyncio.run(self._read_status(timeout))
        except Exception as error:  # noqa: BLE001
            return {"online": False, "detail": f"K1 not reachable on :9999 ({error.__class__.__name__})."}
        if not data:
            return {"online": False, "detail": "Connected to the K1 but it sent no status."}
        device_state = data.get("deviceState", data.get("state"))
        progress = data.get("printProgress")
        left = data.get("printLeftTime")
        return {
            "online": True,
            "state": _STATE.get(device_state, str(device_state) if device_state is not None else None),
            "progress": int(progress) if isinstance(progress, (int, float)) else None,
            "nozzle_temp": _as_float(data.get("nozzleTemp")),
            "bed_temp": _as_float(data.get("bedTemp0")),
            "remaining_min": int(left / 60) if isinstance(left, (int, float)) and left else None,
            "job_name": (data.get("printFileName") or None),
            "light_on": bool(data.get("lightSw", 0)),
        }

    async def _read_status(self, timeout: float) -> dict:
        merged: dict = {}
        async with websockets.connect(self.url, open_timeout=timeout, close_timeout=2, max_size=None) as ws:
            for _ in range(6):
                message = await asyncio.wait_for(ws.recv(), timeout=timeout)
                try:
                    merged.update(json.loads(message))
                except (ValueError, TypeError):
                    continue
                if "deviceState" in merged and "nozzleTemp" in merged:
                    break
        return merged

    # --- control ---

    def _send(self, params: dict, timeout: float = 6.0) -> dict:
        if not HAVE_WS:
            return {"ok": False, "detail": "The websockets library is not installed on the server."}
        if not self.host:
            return {"ok": False, "detail": "Missing host/IP."}
        try:
            asyncio.run(self._asend(params, timeout))
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "detail": f"K1 command failed ({error.__class__.__name__})."}
        return {"ok": True}

    async def _asend(self, params: dict, timeout: float) -> None:
        async with websockets.connect(self.url, open_timeout=timeout, close_timeout=2, max_size=None) as ws:
            await ws.send(json.dumps({"method": "set", "params": params}))
            try:
                await asyncio.wait_for(ws.recv(), timeout=2)
            except asyncio.TimeoutError:
                pass

    def run_gcode(self, gcode: str) -> dict:
        return self._send({"gcodeCmd": gcode})

    def set_light(self, on: bool) -> dict:
        return self._send({"lightSw": 1 if on else 0})

    def home(self) -> dict:
        return self.run_gcode("G28\r\n")

    def jog(self, axis: str, distance: float, feedrate: int = 3000) -> dict:
        axis = (axis or "").upper()
        if axis not in ("X", "Y", "Z"):
            return {"ok": False, "detail": f"Invalid axis '{axis}'."}
        rate = 600 if axis == "Z" else feedrate
        return self.run_gcode(f"G91\r\nG1 {axis}{distance} F{rate}\r\nG90\r\n")

    def pause(self) -> dict:
        return self._send({"pause": 1})

    def resume(self) -> dict:
        return self._send({"pause": 0})

    def stop(self) -> dict:
        return self._send({"stop": 1})

    def set_speed(self, percent: int) -> dict:
        return self._send({"setFeedratePct": int(percent)})

    def upload_file(self, local_path: str, filename: str, timeout: float = 180.0) -> dict:
        """Upload a .gcode to the K1 over its stock HTTP endpoint (POST /upload/<name>)."""
        try:
            with open(local_path, "rb") as handle:
                response = httpx.post(
                    f"http://{self.host}/upload/{filename}",
                    files={"file": (filename, handle, "application/octet-stream")},
                    timeout=timeout,
                )
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as error:
            return {"ok": False, "detail": f"K1 upload failed: {error.__class__.__name__}"}
        return {"ok": True, "remote_name": filename}

    def start_print(self, filename: str) -> dict:
        return self._send({"opGcodeFile": f"printprt:{GCODE_DIR}/{filename}"})
