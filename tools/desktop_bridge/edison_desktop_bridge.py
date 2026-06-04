from __future__ import annotations

import argparse
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "desktop-bridge.local.json"
DISCOVERY_CONFIG = ROOT / "config" / "integration-discovery.local.json"


def load_config(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    config = build_default_config()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return config


def build_default_config() -> dict[str, Any]:
    apps: dict[str, dict[str, Any]] = {}
    printers: list[dict[str, Any]] = []
    if DISCOVERY_CONFIG.exists():
        try:
            snapshot = json.loads(DISCOVERY_CONFIG.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            snapshot = {}
        for item in snapshot.get("paths", []):
            name = str(item.get("name") or "")
            path = str(item.get("path") or "")
            if not name or not path:
                continue
            tool_id = slug(name)
            apps[tool_id] = {"id": tool_id, "name": name, "path": path, "args": []}
        printers = [
            {
                "name": str(item.get("name") or ""),
                "driver": str(item.get("driver") or ""),
                "port": str(item.get("port") or ""),
                "status": str(item.get("status") or ""),
            }
            for item in snapshot.get("printers", [])
            if item.get("name")
        ]
    return {
        "host": "0.0.0.0",
        "port": 8765,
        "allowed_roots": [
            str(ROOT / "projects"),
            str(ROOT / "artifacts"),
            str(Path.home() / "Documents"),
            str(Path.home() / "Downloads"),
        ],
        "apps": apps,
        "printers": printers,
    }


def slug(value: str) -> str:
    clean = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in clean:
        clean = clean.replace("--", "-")
    return clean.strip("-")


def make_handler(config: dict[str, Any]):
    class DesktopBridgeHandler(BaseHTTPRequestHandler):
        server_version = "EdisonDesktopBridge/0.1"

        def do_GET(self) -> None:
            if self.path.rstrip("/") == "/health":
                self.respond(
                    {
                        "ok": True,
                        "service": "edison-desktop-bridge",
                        "apps": list(config.get("apps", {}).values()),
                        "printers": config.get("printers", []),
                        "allowed_roots": config.get("allowed_roots", []),
                        "detail": "Main PC desktop bridge is running.",
                    }
                )
                return
            self.respond({"ok": False, "detail": "Unknown route."}, status=404)

        def do_POST(self) -> None:
            payload = self.read_json()
            if self.path.rstrip("/") == "/launch":
                self.launch_tool(payload)
                return
            if self.path.rstrip("/") == "/notify":
                self.notify(payload)
                return
            if self.path.rstrip("/") == "/print-label":
                self.print_label(payload)
                return
            self.respond({"ok": False, "detail": "Unknown route."}, status=404)

        def launch_tool(self, payload: dict[str, Any]) -> None:
            tool_id = str(payload.get("tool_id") or "")
            tool = config.get("apps", {}).get(tool_id)
            if not tool:
                self.respond({"ok": False, "detail": f"Tool is not allowlisted: {tool_id}"}, status=404)
                return
            path = Path(str(tool.get("path") or ""))
            if not path.exists():
                self.respond({"ok": False, "detail": f"Tool path does not exist: {path}"}, status=404)
                return
            args = [str(item) for item in payload.get("args", tool.get("args", [])) if item]
            if not all(path_allowed(item, config.get("allowed_roots", [])) or not looks_like_path(item) for item in args):
                self.respond({"ok": False, "detail": "One or more arguments are outside the allowed roots."}, status=400)
                return
            subprocess.Popen([str(path), *args], cwd=str(path.parent))
            self.respond({"ok": True, "tool_id": tool_id, "detail": f"Launched {tool.get('name') or tool_id}."})

        def notify(self, payload: dict[str, Any]) -> None:
            title = str(payload.get("title") or "Edison")
            message = str(payload.get("message") or "Desktop bridge notification")
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                f"[System.Windows.Forms.MessageBox]::Show({json.dumps(message)}, {json.dumps(title)}) | Out-Null"
            )
            subprocess.Popen(["powershell", "-NoProfile", "-Command", script])
            self.respond({"ok": True, "detail": "Desktop notification posted."})

        def print_label(self, payload: dict[str, Any]) -> None:
            label_path = str(payload.get("path") or "")
            if not label_path or not path_allowed(label_path, config.get("allowed_roots", [])):
                self.respond({"ok": False, "detail": "Label path must be inside an allowed root."}, status=400)
                return
            path = Path(label_path)
            if not path.exists():
                self.respond({"ok": False, "detail": "Label file was not found."}, status=404)
                return
            subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process -FilePath {json.dumps(str(path))} -Verb Print"])
            self.respond({"ok": True, "detail": "Label print was sent to Windows."})

        def read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return {}
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}

        def respond(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    return DesktopBridgeHandler


def looks_like_path(value: str) -> bool:
    return ":\\" in value or value.startswith("/") or "\\" in value


def path_allowed(value: str, roots: list[str]) -> bool:
    try:
        candidate = Path(value).expanduser().resolve()
    except OSError:
        return False
    for root in roots:
        try:
            root_path = Path(root).expanduser().resolve()
        except OSError:
            continue
        if candidate == root_path or root_path in candidate.parents:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Edison main-PC desktop bridge.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)
    host = str(config.get("host") or "0.0.0.0")
    port = int(config.get("port") or 8765)
    server = ThreadingHTTPServer((host, port), make_handler(config))
    print(f"Edison desktop bridge listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
