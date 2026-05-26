from __future__ import annotations

import httpx

from edison_core.schemas import MediaBackendStatus


class Wan22Client:
    def __init__(
        self,
        base_url: str | None,
        timeout_seconds: float = 2.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    def status(self) -> MediaBackendStatus:
        if not self.base_url:
            return MediaBackendStatus(
                status="setup_required",
                base_url=None,
                detail="WAN 2.2 base URL is not configured.",
            )

        # WAN 2.2 deployments vary by wrapper; /health is a pragmatic default.
        # Edison also supports the native ComfyUI WAN templates, which expose
        # ComfyUI's /system_stats endpoint instead of a WAN-specific health API.
        try:
            payload = self._get_json("/health")
        except (httpx.HTTPError, ValueError) as error:
            health_error = error
            try:
                payload = self._get_json("/system_stats")
            except (httpx.HTTPError, ValueError) as system_error:
                return MediaBackendStatus(
                    status="offline",
                    base_url=self.base_url,
                    reachable=False,
                    detail=f"WAN 2.2 service is not reachable: {health_error}; ComfyUI fallback also failed: {system_error}",
                )
            return MediaBackendStatus(
                status="ready",
                base_url=self.base_url,
                reachable=True,
                detail="WAN 2.2 is available through ComfyUI workflow templates.",
                metadata={
                    "adapter": "comfyui",
                    "health_endpoint": "/system_stats",
                    "system": payload if isinstance(payload, dict) else {},
                },
            )

        metadata = payload if isinstance(payload, dict) else {}
        metadata = {**metadata, "health_endpoint": "/health"}
        return MediaBackendStatus(
            status="ready",
            base_url=self.base_url,
            reachable=True,
            detail="WAN 2.2 service responded to health checks.",
            metadata=metadata,
        )

    def _get_json(self, path: str):
        url = f"{self.base_url}{path}"
        if self.http_client is not None:
            response = self.http_client.get(url, timeout=self.timeout_seconds)
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(url)
        response.raise_for_status()
        return response.json()
