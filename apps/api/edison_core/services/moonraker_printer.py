"""Moonraker (Klipper) adapter — Creality K1 SE and any CR10S running Klipper."""

from __future__ import annotations

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
        except (httpx.HTTPError, ValueError) as error:
            return {"online": False, "detail": f"Moonraker unreachable: {error.__class__.__name__}"}
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
