from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "desktop-bridge.local.json"
DISCOVERY_CONFIG = ROOT / "config" / "integration-discovery.local.json"
SECRET_MARKERS = ("password", "secret", "token", "api_key", "apikey", "access_code")
MAX_READ_BYTES = 1024 * 1024


def load_config(path: Path) -> dict[str, Any]:
    if path.exists():
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        normalized = normalize_config(config)
        if normalized != config:
            write_config(path, normalized)
        return normalized
    config = build_default_config()
    write_config(path, config)
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
        "three_d_printers": [],
        "fusion": {
            "queue_dir": str(ROOT / "projects" / "fusion-jobs" / "queue"),
            "results_dir": str(ROOT / "projects" / "fusion-jobs" / "results"),
            "exports_dir": str(ROOT / "projects" / "fusion-jobs" / "exports"),
            "launch_tool_id": "",
        },
        "slicer_jobs_dir": str(ROOT / "projects" / "slicer-jobs"),
    }


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    defaults = build_default_config()
    merged = dict(config) if isinstance(config, dict) else {}
    merged["host"] = str(merged.get("host") or defaults["host"])
    merged["port"] = int(merged.get("port") or defaults["port"])
    merged["allowed_roots"] = unique_strings([*defaults["allowed_roots"], *merged.get("allowed_roots", [])])
    merged["apps"] = merged.get("apps") if isinstance(merged.get("apps"), dict) else defaults["apps"]
    merged["printers"] = merged.get("printers") if isinstance(merged.get("printers"), list) else defaults["printers"]
    merged["three_d_printers"] = (
        merged.get("three_d_printers") if isinstance(merged.get("three_d_printers"), list) else []
    )
    fusion = merged.get("fusion") if isinstance(merged.get("fusion"), dict) else {}
    merged["fusion"] = {**defaults["fusion"], **fusion}
    merged["slicer_jobs_dir"] = str(merged.get("slicer_jobs_dir") or defaults["slicer_jobs_dir"])
    return merged


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def write_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8", newline="\n")


def slug(value: str) -> str:
    clean = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in clean:
        clean = clean.replace("--", "-")
    return clean.strip("-")


def make_handler(config: dict[str, Any], config_path: Path | None = None):
    class DesktopBridgeHandler(BaseHTTPRequestHandler):
        server_version = "EdisonDesktopBridge/0.2"

        def do_GET(self) -> None:
            route = self.path.rstrip("/") or "/"
            if route == "/health":
                self.respond(
                    {
                        "ok": True,
                        "service": "edison-desktop-bridge",
                        "apps": redact_secrets(list(config.get("apps", {}).values())),
                        "printers": redact_secrets(config.get("printers", [])),
                        "three_d_printers": redact_secrets(config.get("three_d_printers", [])),
                        "allowed_roots": config.get("allowed_roots", []),
                        "tools": bridge_tools(config),
                        "detail": "Main PC desktop bridge is running with PC control tools enabled.",
                    }
                )
                return
            if route == "/tools":
                self.respond({"ok": True, "tools": bridge_tools(config), "apps": redact_secrets(list(config.get("apps", {}).values()))})
                return
            if route == "/printers":
                self.respond(
                    {
                        "ok": True,
                        "printers": redact_secrets(config.get("printers", [])),
                        "three_d_printers": redact_secrets(config.get("three_d_printers", [])),
                        "slicers": slicer_tools(config),
                        "detail": "Detected Windows printers, configured 3D printers, and allowlisted slicers.",
                    }
                )
                return
            self.respond({"ok": False, "detail": "Unknown route."}, status=404)

        def do_POST(self) -> None:
            payload = self.read_json()
            route = self.path.rstrip("/") or "/"
            if route == "/launch":
                self.launch_tool(payload)
                return
            if route == "/notify":
                self.notify(payload)
                return
            if route == "/print-label":
                self.print_label(payload)
                return
            if route == "/files/list":
                self.files_list(payload)
                return
            if route == "/files/read":
                self.files_read(payload)
                return
            if route == "/files/write":
                self.files_write(payload)
                return
            if route == "/files/mkdir":
                self.files_mkdir(payload)
                return
            if route == "/fusion/job":
                self.fusion_job(payload)
                return
            if route == "/slicer/open":
                self.slicer_open(payload)
                return
            if route == "/slicer/prepare":
                self.slicer_prepare(payload)
                return
            if route == "/printers/register":
                self.printer_register(payload)
                return
            self.respond({"ok": False, "detail": "Unknown route."}, status=404)

        def launch_tool(self, payload: dict[str, Any]) -> None:
            tool_id = str(payload.get("tool_id") or "")
            tool = config.get("apps", {}).get(tool_id, {})
            raw_args = payload.get("args", tool.get("args", []))
            if isinstance(raw_args, str):
                args = [raw_args]
            elif isinstance(raw_args, list):
                args = [str(item) for item in raw_args if item]
            else:
                args = []
            result, status = launch_configured_tool(config, tool_id, args)
            self.respond(result, status=status)

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
            path = resolve_allowed_path(label_path, config)
            if path is None:
                self.respond({"ok": False, "detail": "Label path must be inside an allowed root."}, status=400)
                return
            if not path.exists():
                self.respond({"ok": False, "detail": "Label file was not found."}, status=404)
                return
            subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process -FilePath {json.dumps(str(path))} -Verb Print"])
            self.respond({"ok": True, "detail": "Label print was sent to Windows."})

        def files_list(self, payload: dict[str, Any]) -> None:
            path = resolve_allowed_path(str(payload.get("path") or first_allowed_root(config)), config)
            if path is None:
                self.respond({"ok": False, "detail": "Path is outside the allowed roots."}, status=400)
                return
            if not path.exists():
                self.respond({"ok": False, "detail": "Path was not found."}, status=404)
                return
            max_entries = clamp_int(payload.get("max_entries"), 1, 500, 120)
            if path.is_file():
                entries = [file_entry(path)]
            else:
                entries = [
                    file_entry(item)
                    for item in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))[:max_entries]
                ]
            self.respond({"ok": True, "path": str(path), "entries": entries, "detail": "Allowed path listed."})

        def files_read(self, payload: dict[str, Any]) -> None:
            path = resolve_allowed_path(str(payload.get("path") or ""), config)
            if path is None:
                self.respond({"ok": False, "detail": "Path is outside the allowed roots."}, status=400)
                return
            if not path.is_file():
                self.respond({"ok": False, "detail": "File was not found."}, status=404)
                return
            max_bytes = clamp_int(payload.get("max_bytes"), 1, MAX_READ_BYTES, MAX_READ_BYTES)
            data = path.read_bytes()
            truncated = len(data) > max_bytes
            content = data[:max_bytes].decode(str(payload.get("encoding") or "utf-8"), errors="replace")
            self.respond(
                {
                    "ok": True,
                    "path": str(path),
                    "content": content,
                    "truncated": truncated,
                    "size_bytes": len(data),
                    "detail": "Allowed file read.",
                }
            )

        def files_write(self, payload: dict[str, Any]) -> None:
            path = resolve_allowed_path(str(payload.get("path") or ""), config, allow_missing=True)
            if path is None:
                self.respond({"ok": False, "detail": "Path is outside the allowed roots."}, status=400)
                return
            if path.exists() and not bool(payload.get("overwrite")) and not bool(payload.get("append")):
                self.respond({"ok": False, "detail": "File already exists. Set overwrite or append to true."}, status=409)
                return
            content = str(payload.get("content") or "")
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if bool(payload.get("append")) else "w"
            with path.open(mode, encoding=str(payload.get("encoding") or "utf-8"), newline="\n") as handle:
                handle.write(content)
            self.respond({"ok": True, "path": str(path), "size_bytes": path.stat().st_size, "detail": "Allowed file written."})

        def files_mkdir(self, payload: dict[str, Any]) -> None:
            path = resolve_allowed_path(str(payload.get("path") or ""), config, allow_missing=True)
            if path is None:
                self.respond({"ok": False, "detail": "Path is outside the allowed roots."}, status=400)
                return
            path.mkdir(parents=True, exist_ok=True)
            self.respond({"ok": True, "path": str(path), "detail": "Allowed folder is ready."})

        def fusion_job(self, payload: dict[str, Any]) -> None:
            fusion = config.get("fusion", {})
            queue_dir = ensure_allowed_directory(str(fusion.get("queue_dir") or ""), config)
            results_dir = ensure_allowed_directory(str(fusion.get("results_dir") or ""), config)
            exports_dir = ensure_allowed_directory(str(fusion.get("exports_dir") or ""), config)
            if queue_dir is None or results_dir is None or exports_dir is None:
                self.respond({"ok": False, "detail": "Fusion queue/results/export paths must be inside allowed roots."}, status=400)
                return
            job_id = slug(str(payload.get("job_id") or f"fusion-{utc_stamp()}-{uuid.uuid4().hex[:8]}"))
            result_path = results_dir / f"{job_id}.result.json"
            job_path = queue_dir / f"{job_id}.json"
            job = {
                "id": job_id,
                "status": "queued",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "prompt": str(payload.get("prompt") or ""),
                "job_type": str(payload.get("job_type") or "script"),
                "script": str(payload.get("script") or ""),
                "parameters": payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {},
                "exports": payload.get("exports") if isinstance(payload.get("exports"), list) else [],
                "exports_dir": str(exports_dir),
                "result_path": str(result_path),
            }
            job_path.write_text(json.dumps(job, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
            launch_detail = "Fusion launch was not requested."
            launch_result: dict[str, Any] = {"ok": True}
            if bool(payload.get("launch", True)):
                tool_id = str(payload.get("tool_id") or fusion.get("launch_tool_id") or "")
                if not tool_id:
                    tool = find_tool(config, ["fusion 360", "fusion360", "fusion launcher"])
                    tool_id = str(tool.get("id") or "") if tool else ""
                if tool_id:
                    launch_result, _ = launch_configured_tool(config, tool_id, [])
                    launch_detail = str(launch_result.get("detail") or "")
                else:
                    launch_detail = "Fusion job queued, but Fusion 360 is not allowlisted in bridge config."
            self.respond(
                {
                    "ok": True,
                    "job_id": job_id,
                    "job_path": str(job_path),
                    "result_path": str(result_path),
                    "exports_dir": str(exports_dir),
                    "launch": launch_result,
                    "detail": f"Fusion job queued. {launch_detail}",
                }
            )

        def slicer_open(self, payload: dict[str, Any]) -> None:
            model_path = resolve_allowed_path(str(payload.get("model_path") or payload.get("path") or ""), config)
            if model_path is None or not model_path.is_file():
                self.respond({"ok": False, "detail": "Model path must be an existing file inside an allowed root."}, status=400)
                return
            tool_id = str(payload.get("tool_id") or "")
            if not tool_id:
                tool = choose_slicer_tool(config, str(payload.get("slicer") or ""))
                tool_id = str(tool.get("id") or "") if tool else ""
            result, status = launch_configured_tool(config, tool_id, [str(model_path)])
            self.respond(result, status=status)

        def slicer_prepare(self, payload: dict[str, Any]) -> None:
            jobs_dir = ensure_allowed_directory(str(config.get("slicer_jobs_dir") or ""), config)
            if jobs_dir is None:
                self.respond({"ok": False, "detail": "Slicer jobs path must be inside an allowed root."}, status=400)
                return
            model_path = None
            if payload.get("model_path") or payload.get("path"):
                model_path = resolve_allowed_path(str(payload.get("model_path") or payload.get("path") or ""), config)
                if model_path is None or not model_path.exists():
                    self.respond({"ok": False, "detail": "Model path must be inside an allowed root."}, status=400)
                    return
            job_id = slug(str(payload.get("job_id") or f"slicer-{utc_stamp()}-{uuid.uuid4().hex[:8]}"))
            tool = choose_slicer_tool(config, str(payload.get("slicer") or ""))
            manifest = {
                "id": job_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "ready_to_slice",
                "tool_id": str(payload.get("tool_id") or (tool.get("id") if tool else "")),
                "model_path": str(model_path) if model_path else "",
                "order_id": str(payload.get("order_id") or ""),
                "mapping_id": str(payload.get("mapping_id") or ""),
                "printer_id": str(payload.get("printer_id") or ""),
                "material": str(payload.get("material") or ""),
                "color": str(payload.get("color") or ""),
                "slicer_profile": str(payload.get("slicer_profile") or ""),
                "notes": str(payload.get("notes") or ""),
            }
            manifest_path = jobs_dir / f"{job_id}.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
            launch_result: dict[str, Any] = {"ok": True, "detail": "Slicer launch was not requested."}
            if bool(payload.get("launch") or payload.get("open")):
                if not model_path:
                    launch_result = {"ok": False, "detail": "Slicer job was created, but no model path was provided to open."}
                else:
                    launch_result, _ = launch_configured_tool(config, manifest["tool_id"], [str(model_path)])
            self.respond(
                {
                    "ok": True,
                    "job_id": job_id,
                    "manifest_path": str(manifest_path),
                    "launch": launch_result,
                    "detail": "Slicer production handoff was prepared.",
                }
            )

        def printer_register(self, payload: dict[str, Any]) -> None:
            if config_path is None:
                self.respond({"ok": False, "detail": "Bridge config path is not writable for printer registration."}, status=400)
                return
            name = str(payload.get("name") or "").strip()
            if not name:
                self.respond({"ok": False, "detail": "Printer name is required."}, status=400)
                return
            printer_id = slug(str(payload.get("id") or name))
            record = {
                "id": printer_id,
                "name": name,
                "kind": str(payload.get("kind") or "bambu"),
                "host": str(payload.get("host") or ""),
                "serial": str(payload.get("serial") or ""),
                "access_code": str(payload.get("access_code") or ""),
                "slicer": str(payload.get("slicer") or ""),
                "camera_url": str(payload.get("camera_url") or ""),
                "notes": str(payload.get("notes") or ""),
            }
            printers = [item for item in config.get("three_d_printers", []) if isinstance(item, dict) and item.get("id") != printer_id]
            printers.append(record)
            config["three_d_printers"] = printers
            write_config(config_path, config)
            self.respond(
                {
                    "ok": True,
                    "printer": redact_secrets(record),
                    "detail": "3D printer profile saved to the local desktop bridge config.",
                }
            )

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


def bridge_tools(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"id": "launch", "method": "POST", "path": "/launch", "description": "Launch an allowlisted Windows app."},
        {"id": "notify", "method": "POST", "path": "/notify", "description": "Show a desktop alert on the main PC."},
        {"id": "print-label", "method": "POST", "path": "/print-label", "description": "Print an allowed PDF/PNG label path."},
        {"id": "files.list", "method": "POST", "path": "/files/list", "description": "List an allowlisted folder."},
        {"id": "files.read", "method": "POST", "path": "/files/read", "description": "Read an allowlisted text file."},
        {"id": "files.write", "method": "POST", "path": "/files/write", "description": "Write an allowlisted text file."},
        {"id": "files.mkdir", "method": "POST", "path": "/files/mkdir", "description": "Create an allowlisted folder."},
        {"id": "fusion.job", "method": "POST", "path": "/fusion/job", "description": "Queue a Fusion 360 automation job."},
        {"id": "slicer.open", "method": "POST", "path": "/slicer/open", "description": "Open a model file in Bambu/Orca/Cura."},
        {"id": "slicer.prepare", "method": "POST", "path": "/slicer/prepare", "description": "Create a slicer production handoff."},
        {"id": "printers", "method": "GET", "path": "/printers", "description": "List Windows printers and configured 3D printers."},
        {"id": "printers.register", "method": "POST", "path": "/printers/register", "description": "Save a local 3D printer profile."},
    ]


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


def resolve_allowed_path(value: str, config: dict[str, Any], allow_missing: bool = False) -> Path | None:
    if not value:
        return None
    first_root = first_allowed_root(config)
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() and first_root:
        candidate = Path(first_root) / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return None
    if not allow_missing and not resolved.exists():
        return None
    return resolved if path_allowed(str(resolved), config.get("allowed_roots", [])) else None


def ensure_allowed_directory(value: str, config: dict[str, Any]) -> Path | None:
    path = resolve_allowed_path(value, config, allow_missing=True)
    if path is None:
        return None
    path.mkdir(parents=True, exist_ok=True)
    return path


def first_allowed_root(config: dict[str, Any]) -> str:
    roots = config.get("allowed_roots", [])
    return str(roots[0]) if roots else ""


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def file_entry(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "kind": "directory" if path.is_dir() else "file",
        "size_bytes": stat.st_size if path.is_file() else None,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def launch_configured_tool(config: dict[str, Any], tool_id: str, args: list[str]) -> tuple[dict[str, Any], int]:
    tool = config.get("apps", {}).get(tool_id)
    if not tool:
        return {"ok": False, "detail": f"Tool is not allowlisted: {tool_id}"}, 404
    path = Path(str(tool.get("path") or ""))
    if not path.exists():
        return {"ok": False, "detail": f"Tool path does not exist: {path}"}, 404
    if not all(path_allowed(item, config.get("allowed_roots", [])) or not looks_like_path(item) for item in args):
        return {"ok": False, "detail": "One or more arguments are outside the allowed roots."}, 400
    subprocess.Popen([str(path), *args], cwd=str(path.parent))
    return {"ok": True, "tool_id": tool_id, "detail": f"Launched {tool.get('name') or tool_id}."}, 200


def find_tool(config: dict[str, Any], keywords: list[str]) -> dict[str, Any] | None:
    for tool in config.get("apps", {}).values():
        haystack = " ".join(str(tool.get(key) or "") for key in ("id", "name", "path")).lower()
        if any(keyword.lower() in haystack for keyword in keywords):
            return tool
    return None


def slicer_tools(config: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for tool in config.get("apps", {}).values():
        haystack = " ".join(str(tool.get(key) or "") for key in ("id", "name", "path")).lower()
        if any(keyword in haystack for keyword in ("bambu", "orca", "cura", "slicer")):
            result.append(redact_secrets(tool))
    return result


def choose_slicer_tool(config: dict[str, Any], requested: str = "") -> dict[str, Any] | None:
    if requested:
        requested_lower = requested.lower()
        for tool in config.get("apps", {}).values():
            haystack = " ".join(str(tool.get(key) or "") for key in ("id", "name", "path")).lower()
            if requested_lower in haystack:
                return tool
    for keywords in (["bambu"], ["orca"], ["cura"], ["slicer"]):
        tool = find_tool(config, keywords)
        if tool:
            return tool
    return None


def redact_secrets(value: Any) -> Any:
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): ("***" if any(marker in str(key).lower() for marker in SECRET_MARKERS) and item else redact_secrets(item))
            for key, item in value.items()
        }
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Edison main-PC desktop bridge.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)
    host = str(config.get("host") or "0.0.0.0")
    port = int(config.get("port") or 8765)
    server = ThreadingHTTPServer((host, port), make_handler(config, config_path))
    print(f"Edison desktop bridge listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
