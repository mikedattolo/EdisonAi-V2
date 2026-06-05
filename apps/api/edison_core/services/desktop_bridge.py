from __future__ import annotations

from typing import Any

import httpx

from edison_core.schemas import DesktopBridgeActionResult, DesktopBridgeStatus
from edison_core.services.runtime_settings import RuntimeSettingsStore


class DesktopBridgeClient:
    def __init__(self, runtime_settings: RuntimeSettingsStore, timeout_seconds: float = 2.5) -> None:
        self.runtime_settings = runtime_settings
        self.timeout_seconds = timeout_seconds

    def status(self) -> DesktopBridgeStatus:
        bridge_url = self._bridge_url()
        if not bridge_url:
            return DesktopBridgeStatus(
                configured_url="",
                reachable=False,
                detail="Desktop bridge URL is not configured in runtime settings.",
            )
        try:
            payload = self._get(bridge_url, "/health")
        except httpx.HTTPError as error:
            return DesktopBridgeStatus(
                configured_url=bridge_url,
                reachable=False,
                detail=f"Desktop bridge is configured but not reachable: {error.__class__.__name__}",
            )
        return DesktopBridgeStatus(
            configured_url=bridge_url,
            reachable=True,
            apps=[item for item in payload.get("apps", []) if isinstance(item, dict)],
            printers=[item for item in payload.get("printers", []) if isinstance(item, dict)],
            three_d_printers=[item for item in payload.get("three_d_printers", []) if isinstance(item, dict)],
            allowed_roots=[str(item) for item in payload.get("allowed_roots", []) if item],
            tools=[item for item in payload.get("tools", []) if isinstance(item, dict)],
            detail=str(payload.get("detail") or "Desktop bridge is reachable."),
        )

    def fetch(self, path: str) -> DesktopBridgeActionResult:
        action = path.strip("/")
        bridge_url = self._bridge_url()
        if not bridge_url:
            return DesktopBridgeActionResult(
                ok=False,
                action=action,
                detail="Desktop bridge URL is not configured.",
            )
        try:
            result = self._get(bridge_url, f"/{action}")
        except httpx.HTTPError as error:
            return DesktopBridgeActionResult(
                ok=False,
                action=action,
                detail=f"Desktop bridge fetch failed: {error.__class__.__name__}",
            )
        return DesktopBridgeActionResult(
            ok=bool(result.get("ok", True)),
            action=action,
            detail=str(result.get("detail") or "Desktop bridge fetch completed."),
            result={key: value for key, value in result.items() if key not in {"ok", "detail"}},
        )

    def action(self, action: str, payload: dict[str, Any] | None = None) -> DesktopBridgeActionResult:
        bridge_url = self._bridge_url()
        if not bridge_url:
            return DesktopBridgeActionResult(
                ok=False,
                action=action,
                detail="Desktop bridge URL is not configured.",
            )
        try:
            result = self._post(bridge_url, f"/{action.strip('/')}", payload or {})
        except httpx.HTTPError as error:
            return DesktopBridgeActionResult(
                ok=False,
                action=action,
                detail=f"Desktop bridge action failed: {error.__class__.__name__}",
            )
        return DesktopBridgeActionResult(
            ok=bool(result.get("ok", True)),
            action=action,
            detail=str(result.get("detail") or "Desktop bridge action completed."),
            result={key: value for key, value in result.items() if key not in {"ok", "detail"}},
        )

    def _bridge_url(self) -> str:
        settings = self.runtime_settings.get()
        value = settings.integrations.get("desktop_bridge_url")
        return str(value).rstrip("/") if value else ""

    def _get(self, base_url: str, path: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(f"{base_url}{path}")
            response.raise_for_status()
            payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _post(self, base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{base_url}{path}", json=payload)
            response.raise_for_status()
            result = response.json()
        return result if isinstance(result, dict) else {}
