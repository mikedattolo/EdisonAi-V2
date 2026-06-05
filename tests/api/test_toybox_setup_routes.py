from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app


def make_client(tmp_path):
    settings = EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        runtime_settings_path=tmp_path / "runtime-settings.local.json",
        integration_discovery_path=tmp_path / "missing-integrations.json",
        comfyui_base_url="",
    )
    return TestClient(create_app(settings))


def test_toybox_setup_seeds_runtime_settings_printers_and_mapping(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/v1/toybox/setup/defaults",
        json={
            "desktop_bridge_url": "http://192.168.1.31:8765",
            "shopify_store_url": "https://toybox.example.myshopify.com",
            "dymo_printer_name": "Mike's shipping label printer",
            "default_slicer": "OrcaSlicer",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_settings"]["integrations"]["desktop_bridge_url"] == "http://192.168.1.31:8765"
    assert payload["runtime_settings"]["toybox"]["order_polling_enabled"] is True
    assert {printer["role"] for printer in payload["printers"]} == {"desktop_bridge", "slicer", "label_printer"}
    assert payload["mappings"][0]["sku"] == "TOYBOX-CUSTOM-PRINT"

    second = client.post(
        "/api/v1/toybox/setup/defaults",
        json={
            "desktop_bridge_url": "http://192.168.1.31:8765",
            "dymo_printer_name": "Mike's shipping label printer",
            "default_slicer": "OrcaSlicer",
        },
    )
    assert second.status_code == 200
    assert len(client.get("/api/v1/toybox/printers").json()) == 3
    assert len(client.get("/api/v1/toybox/mappings").json()) == 1


def test_toybox_order_and_queue_round_trip(tmp_path):
    client = make_client(tmp_path)
    setup = client.post(
        "/api/v1/toybox/setup/defaults",
        json={
            "desktop_bridge_url": "http://192.168.1.31:8765",
            "dymo_printer_name": "Mike's shipping label printer",
            "default_slicer": "OrcaSlicer",
        },
    )
    mapping_id = setup.json()["mappings"][0]["id"]

    order = client.post(
        "/api/v1/toybox/orders",
        json={
            "source": "shopify",
            "external_order_id": "gid://shopify/Order/1",
            "items": [{"sku": "TOYBOX-CUSTOM-PRINT", "quantity": 1}],
        },
    )
    assert order.status_code == 200

    planned = client.post(f"/api/v1/toybox/orders/{order.json()['id']}/queue")
    assert planned.status_code == 200
    assert planned.json()[0]["mapping_id"] == mapping_id
    assert planned.json()[0]["status"] == "queued"

    queue = client.post(
        "/api/v1/toybox/queue",
        json={"order_id": order.json()["id"], "title": "Print custom toy"},
    )
    assert queue.status_code == 200
    updated = client.post(
        f"/api/v1/toybox/queue/{queue.json()['id']}/status",
        json={"status": "printing", "detail": "Started on printer 1"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "printing"
    assert updated.json()["metadata"]["last_detail"] == "Started on printer 1"


def test_desktop_bridge_status_reports_missing_config(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/v1/desktop-bridge/status")

    assert response.status_code == 200
    assert response.json()["reachable"] is False
    assert response.json()["configured_url"] == ""
