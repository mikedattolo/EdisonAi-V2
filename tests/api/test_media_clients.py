import httpx

from edison_core.services.invokeai_client import InvokeAIClient
from edison_core.services.wan22_client import Wan22Client


def test_invokeai_status_accepts_config_endpoint_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/app/version":
            return httpx.Response(404)
        if request.url.path == "/api/v1/app/config":
            return httpx.Response(200, json={"version": "6.12.0"})
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        status = InvokeAIClient("http://invoke.local", http_client=http_client).status()

    assert status.status == "ready"
    assert status.reachable is True
    assert status.metadata["health_endpoint"] == "/api/v1/app/config"


def test_wan22_status_accepts_comfyui_system_stats_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(404)
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"devices": [{"name": "RTX"}]})
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        status = Wan22Client("http://comfy.local", http_client=http_client).status()

    assert status.status == "ready"
    assert status.reachable is True
    assert status.metadata["adapter"] == "comfyui"
    assert status.metadata["health_endpoint"] == "/system_stats"
