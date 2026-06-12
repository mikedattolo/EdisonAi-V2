"""OctoPrint adapter — Creality CR10S (and others) driven through an OctoPrint host."""

from __future__ import annotations

import httpx

from edison_core.services.moonraker_printer import base_url


class OctoPrintPrinter:
    def __init__(self, host: str, api_key: str = "") -> None:
        self.base = base_url(host, 5000)
        self.api_key = (api_key or "").strip()

    def get_status(self, timeout: float = 5.0) -> dict:
        headers = {"X-Api-Key": self.api_key} if self.api_key else {}
        try:
            printer = httpx.get(f"{self.base}/api/printer", headers=headers, timeout=timeout)
            if printer.status_code == 409:
                return {"online": True, "state": "disconnected", "detail": "OctoPrint up, but the printer isn't connected."}
            if printer.status_code in (401, 403):
                return {"online": False, "detail": "OctoPrint rejected the API key."}
            printer.raise_for_status()
            pdata = printer.json()
            job_response = httpx.get(f"{self.base}/api/job", headers=headers, timeout=timeout)
            jdata = job_response.json() if job_response.status_code == 200 else {}
        except (httpx.HTTPError, ValueError) as error:
            return {"online": False, "detail": f"OctoPrint unreachable: {error.__class__.__name__}"}
        temps = pdata.get("temperature", {})
        tool0 = temps.get("tool0", {})
        bed = temps.get("bed", {})
        progress = jdata.get("progress", {}).get("completion")
        time_left = jdata.get("progress", {}).get("printTimeLeft")
        job = jdata.get("job", {}).get("file", {}).get("name")
        return {
            "online": True,
            "state": pdata.get("state", {}).get("text"),
            "progress": round(progress) if isinstance(progress, (int, float)) else None,
            "nozzle_temp": tool0.get("actual"),
            "bed_temp": bed.get("actual"),
            "job_name": job,
            "remaining_min": round(time_left / 60) if isinstance(time_left, (int, float)) else None,
        }
