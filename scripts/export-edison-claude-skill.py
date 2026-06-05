from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an Edison Claude-style skill and MCP bundle.")
    parser.add_argument("--out", required=True, type=Path, help="Output .zip path or destination directory.")
    parser.add_argument("--api-url", default="http://192.168.1.34:8000", help="Edison API URL for README/starter prompts.")
    parser.add_argument("--python", default="python", help="Python executable MCP clients should use.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp_dir:
        bundle_root = Path(temp_dir) / "edison-claude"
        _write_bundle(bundle_root, repo_root, args.api_url, args.python)
        if args.out.suffix.lower() == ".zip":
            args.out.parent.mkdir(parents=True, exist_ok=True)
            _zip_dir(bundle_root, args.out)
        else:
            if args.out.exists():
                shutil.rmtree(args.out)
            shutil.copytree(bundle_root, args.out)
    print(str(args.out))


def _write_bundle(bundle_root: Path, repo_root: Path, api_url: str, python: str) -> None:
    api_root = repo_root / "apps" / "api"
    skills_dir = bundle_root / "skills" / "edison"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        f"""---
name: edison
description: Use Edison V2 local AI PC tools for media, camera, hardware, ToyBox3D production, knowledge, and workspace automation.
---

# Edison V2

Use Edison when the task should interact with Mike's local AI PC, media generation, ToyBox3D, camera/vision, hardware status, knowledge, or code spaces.

Manual Edison API URL: {api_url}

Tool map:
- `edison-media`: media job creation, sync, cancellation, artifacts.
- `edison-camera`: camera status, snapshots, frame analysis.
- `edison-organizer`: documents, product/business briefs, tasks.
- `edison-hardware`: GPU/fan/Hailo/camera/storage status.
- `edison-knowledge`: local knowledge search and ingest.
- `edison-workspace`: safe workspace search and file reads.

Do not expose secrets in chat. Treat Shopify, notification, and printer credentials as local-only configuration.
""",
        encoding="utf-8",
        newline="\n",
    )
    (bundle_root / "edison-mcp.json").write_text(
        json.dumps({"mcpServers": _mcp_servers(repo_root, api_root, python)}, indent=2) + "\n",
        encoding="utf-8",
    )
    (bundle_root / "README.md").write_text(
        f"""# Edison Claude Bundle

Copy `skills/edison` into the Claude skills directory supported by your Claude Code setup and merge `edison-mcp.json` into your MCP settings.

Edison API: {api_url}
Repo root used by MCP commands: {repo_root}

No secrets are included.
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
