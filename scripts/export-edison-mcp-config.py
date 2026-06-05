from __future__ import annotations

import argparse
import json
from pathlib import Path


SERVER_MODULES = {
    "edison-knowledge": "edison_core.mcp.knowledge",
    "edison-workspace": "edison_core.mcp.workspace",
    "edison-media": "edison_core.mcp.media",
    "edison-camera": "edison_core.mcp.camera",
    "edison-hardware": "edison_core.mcp.hardware",
    "edison-organizer": "edison_core.mcp.organizer",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Edison MCP stdio server config for local clients.")
    parser.add_argument("--out", type=Path, help="Optional output JSON path. Defaults to stdout.")
    parser.add_argument("--python", default="python", help="Python executable clients should use.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    api_root = repo_root / "apps" / "api"
    config = {
        "mcpServers": {
            server_id: {
                "command": args.python,
                "args": ["-m", module],
                "cwd": str(repo_root),
                "env": {
                    "PYTHONPATH": str(api_root),
                },
            }
            for server_id, module in SERVER_MODULES.items()
        }
    }
    rendered = json.dumps(config, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
