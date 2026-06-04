from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app


def test_runtime_settings_can_be_saved_without_echoing_secrets(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        runtime_settings_path=tmp_path / "runtime-settings.local.json",
        comfyui_base_url="",
    )
    client = TestClient(create_app(settings))

    saved = client.put(
        "/api/v1/settings/runtime",
        json={
            "toybox": {
                "shopify_store_url": "https://toybox.example.myshopify.com",
                "shopify_api_token": "do-not-echo",
                "order_polling_enabled": True,
            },
            "notifications": {
                "enabled": True,
                "provider": "ntfy",
                "target": "edison-alerts",
            },
        },
    )
    loaded = client.get("/api/v1/settings/runtime")

    assert saved.status_code == 200
    assert saved.json()["toybox"]["shopify_store_url"] == "https://toybox.example.myshopify.com"
    assert saved.json()["toybox"]["shopify_api_token"] is True
    assert loaded.status_code == 200
    assert loaded.json()["notifications"]["target"] == "edison-alerts"
    assert "do-not-echo" not in settings.runtime_settings_path.read_text(encoding="utf-8")
