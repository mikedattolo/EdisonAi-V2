from __future__ import annotations

from typing import Any

import httpx

from edison_core.schemas import ComfyUIStatus


class ComfyUIClient:
    def __init__(
        self,
        base_url: str | None,
        timeout_seconds: float = 2.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    def status(self) -> ComfyUIStatus:
        if not self.base_url:
            return ComfyUIStatus(
                status="setup_required",
                base_url=None,
                detail="ComfyUI base URL is not configured.",
            )

        try:
            system = self._get_json("/system_stats")
            queue = self._get_json("/queue")
        except httpx.HTTPError as error:
            return ComfyUIStatus(
                status="offline",
                base_url=self.base_url,
                reachable=False,
                detail=f"ComfyUI is not reachable: {error}",
            )

        running, pending = _queue_counts(queue)
        return ComfyUIStatus(
            status="ready",
            base_url=self.base_url,
            reachable=True,
            queue_running=running,
            queue_pending=pending,
            detail="ComfyUI responded to status checks.",
            system=system if isinstance(system, dict) else {},
        )

    def _get_json(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        if self.http_client is not None:
            response = self.http_client.get(url, timeout=self.timeout_seconds)
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(url)
        response.raise_for_status()
        return response.json()


def _queue_counts(queue: Any) -> tuple[int, int]:
    if not isinstance(queue, dict):
        return 0, 0
    running = queue.get("queue_running") or []
    pending = queue.get("queue_pending") or []
    return len(running) if isinstance(running, list) else 0, len(pending) if isinstance(pending, list) else 0