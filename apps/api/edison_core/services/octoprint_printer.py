"""OctoPrint adapter — Creality CR10S (and others) driven through an OctoPrint host."""

from __future__ import annotations

import os

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

    def upload_and_print(self, local_path: str, filename: str, start: bool = True, timeout: float = 120.0) -> dict:
        if not self.api_key:
            return {"ok": False, "detail": "OctoPrint API key is required to upload."}
        if not os.path.exists(local_path):
            return {"ok": False, "detail": "File not found on the server."}
        try:
            with open(local_path, "rb") as handle:
                response = httpx.post(
                    f"{self.base}/api/files/local",
                    headers={"X-Api-Key": self.api_key},
                    files={"file": (filename, handle, "application/octet-stream")},
                    data={"select": "true", "print": "true" if start else "false"},
                    timeout=timeout,
                )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as error:
            return {"ok": False, "detail": f"OctoPrint upload failed: {error.__class__.__name__}"}
        return {"ok": True, "remote_name": filename, "detail": "Uploaded and print started." if start else "Uploaded."}

    def _job_command(self, command: str, action: str | None = None) -> dict:
        body: dict = {"command": command}
        if action:
            body["action"] = action
        try:
            response = httpx.post(
                f"{self.base}/api/job",
                headers={"X-Api-Key": self.api_key, "Content-Type": "application/json"},
                json=body,
                timeout=10.0,
            )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as error:
            return {"ok": False, "detail": f"OctoPrint {command} failed: {error.__class__.__name__}"}
        return {"ok": True}

    def pause(self) -> dict:
        return self._job_command("pause", "pause")

    def resume(self) -> dict:
        return self._job_command("pause", "resume")

    def stop(self) -> dict:
        return self._job_command("cancel")
