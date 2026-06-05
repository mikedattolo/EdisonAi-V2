import json
import subprocess
import sys
import zipfile


def test_codex_and_claude_export_scripts_create_bundles(tmp_path):
    codex_zip = tmp_path / "edison-codex-plugin.zip"
    claude_zip = tmp_path / "edison-claude-skill.zip"

    subprocess.run(
        [sys.executable, "scripts/export-edison-codex-plugin.py", "--out", str(codex_zip)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "scripts/export-edison-claude-skill.py", "--out", str(claude_zip)],
        check=True,
        capture_output=True,
        text=True,
    )

    with zipfile.ZipFile(codex_zip) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("edison-codex/.codex-plugin/plugin.json"))
        mcp_config = json.loads(archive.read("edison-codex/.mcp.json"))

    with zipfile.ZipFile(claude_zip) as archive:
        claude_names = set(archive.namelist())
        claude_mcp = json.loads(archive.read("edison-claude/edison-mcp.json"))

    assert "edison-codex/skills/edison/SKILL.md" in names
    assert manifest["name"] == "edison-codex"
    assert "edison-media" in mcp_config["mcpServers"]
    assert "edison-claude/skills/edison/SKILL.md" in claude_names
    assert "edison-camera" in claude_mcp["mcpServers"]
