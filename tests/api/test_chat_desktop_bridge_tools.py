from pathlib import Path

from fastapi.testclient import TestClient

from edison_core.config import EdisonSettings
from edison_core.main import create_app
from edison_core.schemas import DesktopBridgeActionResult, DesktopBridgeStatus


def test_chat_fusion_prompt_routes_to_desktop_bridge_instead_of_model(tmp_path):
    app = create_app(_settings(tmp_path))
    bridge = _FakeDesktopBridge()
    app.state.desktop_bridge_client = bridge
    client = TestClient(app)

    response = client.post(
        "/api/v1/chat",
        json={
            "message": (
                "Use Fusion 360 to create a simple 40 mm by 30 mm by 12 mm rectangular block "
                "and export STL. Do not launch Fusion unless required."
            ),
            "mode": "auto",
            "memory_enabled": True,
        },
    )

    body = response.json()
    assistant = body["assistant_message"]

    assert response.status_code == 201
    assert bridge.actions[0][0] == "fusion/job"
    assert bridge.actions[0][1]["launch"] is False
    assert bridge.actions[0][1]["parameters"] == {
        "command": "box",
        "width_mm": 40.0,
        "depth_mm": 30.0,
        "height_mm": 12.0,
    }
    assert body["model_selection"]["model"]["id"] == "edison-desktop-bridge"
    assert body["inference"]["model_id"] == "edison-desktop-bridge"
    assert "Fusion 360" in body["inference"]["content"]
    assert "not Modly" in body["inference"]["content"]
    assert assistant["metadata"]["intent_router"]["tool_action"] == "desktop_bridge.fusion_job"
    assert assistant["metadata"]["knowledge_context"]["enabled"] is False


def test_chat_bambu_handoff_prompt_routes_to_slicer_prepare(tmp_path):
    app = create_app(_settings(tmp_path))
    bridge = _FakeDesktopBridge()
    app.state.desktop_bridge_client = bridge
    client = TestClient(app)
    model_path = r"C:\Users\19087\Documents\edison v2\EdisonAi-V2\projects\fusion-jobs\exports\test-block.stl"

    response = client.post(
        "/api/v1/chat",
        json={
            "message": f"Prepare a Bambu Studio slicer handoff for this STL: {model_path}. Do not start the print.",
            "mode": "auto",
            "memory_enabled": True,
        },
    )

    body = response.json()
    assistant = body["assistant_message"]

    assert response.status_code == 201
    assert bridge.actions[0] == (
        "slicer/prepare",
        {
            "model_path": model_path,
            "slicer": "Bambu Studio",
            "launch": False,
            "notes": f"Prepare a Bambu Studio slicer handoff for this STL: {model_path}. Do not start the print.",
        },
    )
    assert body["model_selection"]["model"]["id"] == "edison-desktop-bridge"
    assert "I prepared a Bambu Studio slicer handoff" in body["inference"]["content"]
    assert "I cannot access local file paths" not in body["inference"]["content"]
    assert assistant["metadata"]["intent_router"]["tool_action"] == "desktop_bridge.slicer_prepare"
    assert assistant["metadata"]["knowledge_context"]["matches"] == []


def test_streaming_chat_fusion_prompt_uses_desktop_bridge_tool(tmp_path):
    app = create_app(_settings(tmp_path))
    bridge = _FakeDesktopBridge()
    app.state.desktop_bridge_client = bridge
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "Use Fusion 360 to make a 10 x 20 x 5 mm block.", "mode": "auto", "memory_enabled": True},
    ) as response:
        stream_body = "".join(response.iter_text())

    conversations = client.get("/api/v1/conversations").json()
    loaded = client.get(f"/api/v1/conversations/{conversations[0]['id']}").json()

    assert response.status_code == 200
    assert bridge.actions[0][0] == "fusion/job"
    assert bridge.actions[0][1]["parameters"]["width_mm"] == 10.0
    assert "event: token" in stream_body
    assert "not Modly" in stream_body
    assert loaded["messages"][1]["metadata"]["streamed"] is True
    assert loaded["messages"][1]["metadata"]["intent_router"]["tool_action"] == "desktop_bridge.fusion_job"


class _FakeDesktopBridge:
    def __init__(self) -> None:
        self.actions: list[tuple[str, dict]] = []

    def action(self, action: str, payload: dict | None = None) -> DesktopBridgeActionResult:
        clean_payload = payload or {}
        self.actions.append((action, clean_payload))
        if action == "fusion/job":
            return DesktopBridgeActionResult(
                ok=True,
                action=action,
                detail="Fusion job queued. Fusion launch was not requested.",
                result={
                    "job_id": "fusion-test-1",
                    "job_path": r"C:\Edison\projects\fusion-jobs\queue\fusion-test-1.json",
                    "result_path": r"C:\Edison\projects\fusion-jobs\results\fusion-test-1.result.json",
                    "exports_dir": r"C:\Edison\projects\fusion-jobs\exports",
                    "launch": {"ok": True},
                },
            )
        if action == "slicer/prepare":
            return DesktopBridgeActionResult(
                ok=True,
                action=action,
                detail="Slicer production handoff was prepared.",
                result={
                    "job_id": "slicer-test-1",
                    "manifest_path": r"C:\Edison\projects\slicer-jobs\slicer-test-1.json",
                    "launch": {"ok": True, "detail": "Slicer launch was not requested."},
                },
            )
        return DesktopBridgeActionResult(ok=False, action=action, detail="Unexpected fake action.")

    def status(self) -> DesktopBridgeStatus:
        return DesktopBridgeStatus(
            configured_url="http://127.0.0.1:8765",
            reachable=True,
            apps=[
                {"id": "fusion-360", "name": "Fusion 360"},
                {"id": "bambu-studio", "name": "Bambu Studio"},
            ],
            printers=[{"name": "Mike's shipping label printer"}],
            three_d_printers=[],
            allowed_roots=[r"C:\Users\19087\Documents\edison v2\EdisonAi-V2\projects"],
            tools=[{"id": "fusion.job"}, {"id": "slicer.prepare"}],
            detail="Desktop bridge is reachable.",
        )


def _settings(tmp_path: Path) -> EdisonSettings:
    return EdisonSettings(
        database_path=tmp_path / "edison.sqlite3",
        model_registry_path=tmp_path / "missing-models.json",
        runtime_settings_path=tmp_path / "runtime-settings.local.json",
        artifact_root=tmp_path / "artifacts",
        log_root=tmp_path / "logs",
        workspace_roots=[tmp_path],
        comfyui_base_url="",
    )
