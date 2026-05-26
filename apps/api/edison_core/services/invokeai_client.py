from __future__ import annotations

import httpx

from edison_core.schemas import MediaBackendStatus


class InvokeAIClient:
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
                detail="InvokeAI base URL is not configured.",
            )

        errors: list[str] = []
        for path in ("/api/v1/app/version", "/api/v1/app/config", "/openapi.json"):
            try:
                payload = self._get_json(path)
                break
            except (httpx.HTTPError, ValueError) as error:
                errors.append(f"{path}: {error}")
        else:
            return MediaBackendStatus(
                status="offline",
                base_url=self.base_url,
                reachable=False,
                detail=f"InvokeAI is not reachable: {'; '.join(errors)}",
            )

        metadata = payload if isinstance(payload, dict) else {}
        metadata = {**metadata, "health_endpoint": path}
        return MediaBackendStatus(
            status="ready",
            base_url=self.base_url,
            reachable=True,
            detail="InvokeAI responded to health checks.",
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
