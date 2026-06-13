"""Moonraker (Klipper) adapter — Creality K1 SE and any CR10S running Klipper."""

from __future__ import annotations

import os

import httpx


def base_url(host: str, default_port: int) -> str:
    host = (host or "").strip().rstrip("/")
    if host.startswith(("http://", "https://")):
        return host
    if ":" in host:
        return f"http://{host}"
    return f"http://{host}:{default_port}"


class MoonrakerPrinter:
    def __init__(self, host: str) -> None:
        self.base = base_url(host, 7125)

    def get_status(self, timeout: float = 5.0) -> dict:
        try:
            response = httpx.get(
                f"{self.base}/printer/objects/query",
                params={"extruder": "", "heater_bed": "", "print_stats": "", "display_status": ""},
                timeout=timeout,
            )
            response.raise_for_status()
            status = response.json().get("result", {}).get("status", {})
        except (httpx.HTTPError, ValueError):
            return {
                "online": False,
                "detail": (
                    f"Moonraker API not reachable at {self.base}. On a Creality K1/K1 SE the stock "
                    "firmware keeps Moonraker on localhost only — root the printer and run the Creality "
                    "Helper Script (installs Moonraker remote + Fluidd) so port 7125 opens, then Edison connects."
                ),
            }
        extruder = status.get("extruder", {})
        bed = status.get("heater_bed", {})
        print_stats = status.get("print_stats", {})
        display = status.get("display_status", {})
        progress = display.get("progress")
        remaining = print_stats.get("print_duration")
        return {
            "online": True,
            "state": print_stats.get("state"),
            "progress": round(progress * 100) if isinstance(progress, (int, float)) else None,
            "nozzle_temp": extruder.get("temperature"),
            "bed_temp": bed.get("temperature"),
            "job_name": print_stats.get("filename") or None,
            "remaining_min": None if not isinstance(remaining, (int, float)) else None,
        }

    def upload_and_print(self, local_path: str, filename: str, start: bool = True, timeout: float = 120.0) -> dict:
        if not os.path.exists(local_path):
            return {"ok": False, "detail": "File not found on the server."}
        try:
            with open(local_path, "rb") as handle:
                response = httpx.post(
                    f"{self.base}/server/files/upload",
                    files={"file": (filename, handle, "application/octet-stream")},
                    data={"root": "gcodes", "print": "true" if start else "false"},
                    timeout=timeout,
                )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as error:
            return {"ok": False, "detail": f"Moonraker upload failed: {error.__class__.__name__}"}
        return {"ok": True, "remote_name": filename, "detail": "Uploaded and print started." if start else "Uploaded."}

    def _job_action(self, action: str) -> dict:
        try:
            response = httpx.post(f"{self.base}/printer/print/{action}", timeout=10.0)
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as error:
            return {"ok": False, "detail": f"Moonraker {action} failed: {error.__class__.__name__}"}
        return {"ok": True}

    def pause(self) -> dict:
        return self._job_action("pause")

    def resume(self) -> dict:
        return self._job_action("resume")

    def stop(self) -> dict:
        return self._job_action("cancel")

    def run_gcode(self, script: str) -> dict:
        try:
            response = httpx.post(f"{self.base}/printer/gcode/script", params={"script": script}, timeout=12.0)
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as error:
            return {"ok": False, "detail": f"Moonraker gcode failed: {error.__class__.__name__}"}
        return {"ok": True}

    def set_light(self, on: bool) -> dict:
        return self.run_gcode("LIGHTS_ON" if on else "LIGHTS_OFF")

    def home(self) -> dict:
        return self.run_gcode("G28")

    def jog(self, axis: str, distance: float, feedrate: int = 3000) -> dict:
        axis = (axis or "").upper()
        if axis not in ("X", "Y", "Z"):
            return {"ok": False, "detail": f"Invalid axis '{axis}'."}
        rate = 600 if axis == "Z" else feedrate
        return self.run_gcode(f"G91\nG1 {axis}{distance} F{rate}\nG90")
