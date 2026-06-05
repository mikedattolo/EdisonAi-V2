from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


PLUGIN_NAME = "edison-codex"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an Edison Codex plugin bundle.")
    parser.add_argument("--out", required=True, type=Path, help="Output .zip path or plugin directory.")
    parser.add_argument("--api-url", default="http://192.168.1.34:8000", help="Edison API URL for README/starter prompts.")
    parser.add_argument("--python", default="python", help="Python executable MCP clients should use.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp_dir:
        plugin_root = Path(temp_dir) / PLUGIN_NAME
        _write_plugin(plugin_root, repo_root, args.api_url, args.python)
        if args.out.suffix.lower() == ".zip":
            args.out.parent.mkdir(parents=True, exist_ok=True)
            _zip_dir(plugin_root, args.out)
        else:
            if args.out.exists():
                shutil.rmtree(args.out)
            shutil.copytree(plugin_root, args.out)
    print(str(args.out))


def _write_plugin(plugin_root: Path, repo_root: Path, api_url: str, python: str) -> None:
    api_root = repo_root / "apps" / "api"
    (plugin_root / ".codex-plugin").mkdir(parents=True)
    (plugin_root / "skills" / "edison").mkdir(parents=True)
    (plugin_root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": PLUGIN_NAME,
                "version": "0.1.0",
                "description": "Edison V2 local AI PC tools for Codex.",
                "author": {"name": "Edison V2", "url": "https://github.com/mikedattolo/EdisonAi-V2"},
                "repository": "https://github.com/mikedattolo/EdisonAi-V2",
                "license": "MIT",
                "keywords": ["edison", "mcp", "local-ai", "toybox3d", "media"],
                "skills": "./skills/",
                "mcpServers": "./.mcp.json",
                "interface": {
                    "displayName": "Edison V2",
                    "shortDescription": "Control Edison knowledge, media, camera, hardware, workspace, and ToyBox tools.",
                    "longDescription": (
                        "Adds Edison V2 MCP servers and a reusable Codex skill for local AI PC workflows, "
                        "media generation, camera analysis, ToyBox3D production, and repository work."
                    ),
                    "developerName": "Edison V2",
                    "category": "Productivity",
                    "capabilities": ["MCP", "Skills", "Local Tools"],
                    "defaultPrompt": [
                        "Ask Edison what tools are ready.",
                        "Create a ToyBox3D product brief.",
                        "Check Edison media and camera status.",
                    ],
                    "brandColor": "#2B7A68",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_root / ".mcp.json").write_text(
        json.dumps({"mcpServers": _mcp_servers(repo_root, api_root, python)}, indent=2) + "\n",
        encoding="utf-8",
    )
    (plugin_root / "skills" / "edison" / "SKILL.md").write_text(
        f"""---
name: edison
description: Use Edison V2 local AI PC tools for media generation, camera checks, hardware status, ToyBox3D production, knowledge, and workspace tasks.
---

# Edison V2

Use the bundled Edison MCP servers when a task involves local Edison knowledge, media jobs, camera frames, hardware status, ToyBox3D orders/print queues, or workspace files.

Default Edison API URL for manual checks: {api_url}

Prefer these flows:
- Use `edison-media` for image/video/mesh jobs and artifact lookup.
- Use `edison-camera` for camera status, snapshots, and frame analysis.
- Use `edison-organizer` for product briefs, business briefs, documents, and next-action tasks.
- Use `edison-hardware` before hardware-sensitive work.
- Use `edison-workspace` for repo search/read operations.
""",
        encoding="utf-8",
        newline="\n",
    )
    (plugin_root / "README.md").write_text(
        f"""# Edison Codex Plugin

This bundle packages Edison V2 MCP servers and a Codex skill.

Edison API: {api_url}
Repo root used by MCP commands: {repo_root}

No secrets are embedded in this plugin. Shopify, notification, printer, and API credentials stay in local environment variables or runtime settings.
""",
        encoding="utf-8",
        newline="\n",
    )


def _mcp_servers(repo_root: Path, api_root: Path, python: str) -> dict[str, dict[str, object]]:
    modules = {
        "edison-knowledge": "edison_core.mcp.knowledge",
        "edison-workspace": "edison_core.mcp.workspace",
        "edison-media": "edison_core.mcp.media",
        "edison-camera": "edison_core.mcp.camera",
        "edison-hardware": "edison_core.mcp.hardware",
        "edison-organizer": "edison_core.mcp.organizer",
    }
    return {
        server_id: {
            "command": python,
            "args": ["-m", module],
            "cwd": str(repo_root),
            "env": {"PYTHONPATH": str(api_root)},
        }
        for server_id, module in modules.items()
    }


def _zip_dir(root: Path, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(root.parent).as_posix())


if __name__ == "__main__":
    main()
