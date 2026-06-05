from __future__ import annotations

import importlib.util
import json
import sys
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx


def load_bridge_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "tools" / "desktop_bridge" / "edison_desktop_bridge.py"
    spec = importlib.util.spec_from_file_location("edison_desktop_bridge_under_test", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@contextmanager
def run_bridge(config: dict, config_path: Path):
    bridge = load_bridge_module()
    server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.make_handler(config, config_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_desktop_bridge_pc_tools_round_trip(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    config_path = tmp_path / "desktop-bridge.local.json"
    config = {
        "allowed_roots": [str(allowed)],
        "apps": {
            "bambu-studio": {
                "id": "bambu-studio",
                "name": "Bambu Studio",
                "path": sys.executable,
                "args": [],
            }
        },
        "printers": [{"name": "DYMO LabelWriter 5XL", "driver": "DYMO", "port": "USB001"}],
        "three_d_printers": [],
        "fusion": {
            "queue_dir": str(allowed / "fusion-jobs" / "queue"),
            "results_dir": str(allowed / "fusion-jobs" / "results"),
            "exports_dir": str(allowed / "fusion-jobs" / "exports"),
            "launch_tool_id": "",
        },
        "slicer_jobs_dir": str(allowed / "slicer-jobs"),
    }

    with run_bridge(config, config_path) as base_url:
        with httpx.Client(timeout=5) as client:
            health = client.get(f"{base_url}/health").json()
            assert health["ok"] is True
            assert "files.write" in {tool["id"] for tool in health["tools"]}

            write = client.post(
                f"{base_url}/files/write",
                json={"path": str(allowed / "notes.txt"), "content": "hello Edison", "overwrite": True},
            ).json()
            assert write["ok"] is True

            read = client.post(f"{base_url}/files/read", json={"path": write["path"]}).json()
            assert read["content"] == "hello Edison"

            listed = client.post(f"{base_url}/files/list", json={"path": str(allowed)}).json()
            assert "notes.txt" in {entry["name"] for entry in listed["entries"]}

            fusion = client.post(
                f"{base_url}/fusion/job",
                json={
                    "launch": False,
                    "prompt": "make a small test block",
                    "parameters": {"command": "box", "width_mm": 20},
                },
            ).json()
            assert fusion["ok"] is True
            job_path = Path(fusion["job_path"])
            assert job_path.exists()
            assert json.loads(job_path.read_text(encoding="utf-8"))["parameters"]["command"] == "box"

            model = allowed / "demo.stl"
            model.write_text("solid demo\nendsolid demo\n", encoding="utf-8")
            slicer = client.post(
                f"{base_url}/slicer/prepare",
                json={"model_path": str(model), "slicer": "Bambu", "launch": False, "printer_id": "bambu-a1"},
            ).json()
            assert slicer["ok"] is True
            manifest = json.loads(Path(slicer["manifest_path"]).read_text(encoding="utf-8"))
            assert manifest["tool_id"] == "bambu-studio"
            assert manifest["printer_id"] == "bambu-a1"

            registered = client.post(
                f"{base_url}/printers/register",
                json={
                    "name": "Bambu A1",
                    "kind": "bambu",
                    "host": "192.168.1.50",
                    "serial": "SERIAL",
                    "access_code": "12345678",
                },
            ).json()
            assert registered["ok"] is True
            assert registered["printer"]["access_code"] == "***"

            printers = client.get(f"{base_url}/printers").json()
            assert printers["three_d_printers"][0]["access_code"] == "***"
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            assert saved["three_d_printers"][0]["access_code"] == "12345678"
