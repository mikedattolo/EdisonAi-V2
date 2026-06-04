from __future__ import annotations

import json
import shutil
from pathlib import Path

from edison_core.config import EdisonSettings
from edison_core.schemas import (
    IntegrationRecommendation,
    IntegrationScanReport,
    LocalIntegrationRecord,
    utc_now,
)


class IntegrationDiscoveryService:
    def __init__(self, settings: EdisonSettings) -> None:
        self.settings = settings

    def snapshot(self) -> IntegrationScanReport:
        integrations = self._edison_integrations() + self._external_snapshot_integrations()
        recommendations = self._recommendations(integrations)
        return IntegrationScanReport(
            checked_at=utc_now(),
            integrations=integrations,
            recommendations=recommendations,
            detail=(
                f"Detected {sum(1 for item in integrations if item.status == 'ready')} ready "
                f"integrations across Edison and registered external snapshots."
            ),
        )

    def _edison_integrations(self) -> list[LocalIntegrationRecord]:
        specs = [
            (
                "edison-ollama",
                "Ollama on Edison",
                "local-ai",
                ["ollama"],
                "Local model serving and embeddings candidate for Edison.",
                ["Register Ollama models in the model registry.", "Expose model pull/status tools through MCP."],
            ),
            (
                "edison-comfyui",
                "ComfyUI on Edison",
                "media",
                [],
                "Primary image generation backend for Edison media workflows.",
                ["Keep workflow templates for image, texture, product render, and social content modes."],
            ),
            (
                "edison-ffmpeg",
                "FFmpeg on Edison",
                "media",
                ["ffmpeg"],
                "Video, camera, and artifact conversion utility.",
                ["Use for preview generation, camera frame capture, and media transcoding."],
            ),
            (
                "edison-gpu-stack",
                "NVIDIA GPU Stack",
                "hardware",
                ["nvidia-smi"],
                "GPU telemetry and acceleration layer for local AI workloads.",
                ["Expose GPU allocation and job routing policies to agents."],
            ),
            (
                "edison-hailo-brio",
                "Hailo-8 and Brio Vision",
                "hardware",
                ["hailortcli", "v4l2-ctl"],
                "Camera monitoring and object detection hardware path.",
                ["Finish Hailo driver enrollment/reboot, then attach object detection jobs."],
            ),
            (
                "edison-dev-tools",
                "Edison Developer Toolchain",
                "developer",
                ["git", "python3", "node", "npm", "npx"],
                "Repo, API, and web build tooling available to Edison agents.",
                ["Add command-run presets for safe build, test, and deploy tasks."],
            ),
        ]
        integrations: list[LocalIntegrationRecord] = []
        for item_id, name, category, tools, description, next_steps in specs:
            detected_tools = [tool for tool in tools if shutil.which(tool)]
            if item_id == "edison-comfyui":
                status = "staged" if self.settings.comfyui_base_url else "missing"
                detail = f"Configured URL: {self.settings.comfyui_base_url or 'not configured'}"
            else:
                status = "ready" if detected_tools and len(detected_tools) == len(tools) else "missing"
                detail = (
                    f"Detected tools: {', '.join(detected_tools)}"
                    if detected_tools
                    else f"Missing tools: {', '.join(tools)}"
                )
            integrations.append(
                LocalIntegrationRecord(
                    id=item_id,
                    name=name,
                    category=category,
                    status=status,
                    host="edison-ai-pc",
                    description=description,
                    detected_tools=detected_tools,
                    paths=[shutil.which(tool) for tool in detected_tools if shutil.which(tool)],
                    detail=detail,
                    next_steps=next_steps,
                )
            )
        return integrations

    def _external_snapshot_integrations(self) -> list[LocalIntegrationRecord]:
        path = self.settings.integration_discovery_path
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        snapshots = payload if isinstance(payload, list) else [payload]
        integrations: list[LocalIntegrationRecord] = []
        for snapshot in snapshots:
            if isinstance(snapshot, dict):
                integrations.extend(self._integrations_from_snapshot(snapshot))
        return integrations

    def _integrations_from_snapshot(self, snapshot: dict) -> list[LocalIntegrationRecord]:
        host = str(snapshot.get("host") or "external-workstation")
        tools = [item for item in snapshot.get("tools", []) if isinstance(item, dict)]
        paths = [item for item in snapshot.get("paths", []) if isinstance(item, dict)]
        printers = [item for item in snapshot.get("printers", []) if isinstance(item, dict)]
        mcp_servers = [str(item) for item in snapshot.get("mcp_servers", []) if item]
        detected = {
            str(item.get("name")).lower(): item
            for item in tools
            if item.get("detected") is True and item.get("name")
        }
        path_values = [str(item.get("path")) for item in paths if item.get("path")]
        path_text = "\n".join(path_values).lower()
        printer_text = "\n".join(
            " ".join(str(item.get(key, "")) for key in ("name", "driver", "port", "status"))
            for item in printers
        ).lower()

        grouped = [
            (
                "workstation-local-ai",
                "Main PC Local AI",
                "local-ai",
                ["ollama", "codex"],
                "Local model and Codex desktop tooling detected on the coding workstation.",
                ["Expose Edison MCP servers to Codex.", "Optionally bridge workstation Ollama models into Edison routing."],
            ),
            (
                "workstation-minecraft-tools",
                "Main PC Minecraft Asset Tools",
                "minecraft",
                ["blockbench"],
                "Blockbench is available as the likely Minecraft model and texture workflow editor.",
                ["Register Blockbench export presets for Minecraft 1.7.10 models and texture packs."],
            ),
            (
                "workstation-print-tools",
                "Main PC 3D Print Toolchain",
                "3d-printing",
                ["bambu studio", "orcaslicer", "cura"],
                "Slicer and printer-management tools are installed on the main PC.",
                ["Add slicer profile import, printer profile mapping, and print-farm handoff tools."],
            ),
            (
                "workstation-dev-tools",
                "Main PC Developer Toolchain",
                "developer",
                ["git", "python", "node", "npm", "code", "ffmpeg"],
                "Development and media utility tools are available on the main PC.",
                ["Use the workstation as a companion coding and asset-prep node for Edison."],
            ),
            (
                "workstation-cad-tools",
                "Main PC CAD Tools",
                "cad",
                ["fusion 360"],
                "Fusion 360 is available for CAD model generation through a desktop bridge or Fusion script runner.",
                ["Add a PC-side CAD MCP server that can launch Fusion scripts and return STL/STEP artifacts."],
            ),
            (
                "workstation-desktop-bridge",
                "Main PC Desktop Tools Bridge",
                "automation",
                ["codex", "fusion 360", "blockbench", "bambu studio", "orcaslicer", "cura"],
                "A bridge target for controlling installed Windows apps, editing files, and returning artifacts to Edison.",
                ["Run a scoped local MCP/agent service on the PC with allowlisted folders and commands."],
            ),
            (
                "workstation-label-printer",
                "Main PC Shipping Label Printer",
                "commerce",
                ["dymo labelwriter"],
                "DYMO label printing is available for Shopify shipping-label handoff.",
                ["Add a label-print MCP tool that accepts generated PDF/PNG labels and targets the DYMO printer."],
            ),
            (
                "workstation-notifications",
                "Main PC Text and Push Notifications",
                "notifications",
                ["codex"],
                "Notification channels can be staged from Edison to SMS, push, email, or desktop alerts.",
                ["Configure a notification provider such as Twilio, Pushover, ntfy, email SMTP, or Shopify customer events."],
            ),
            (
                "workstation-mcp-config",
                "Main PC MCP Configuration",
                "mcp",
                ["mcp"],
                "Codex MCP configuration is present on the workstation when server names are registered.",
                ["Add Edison workspace, media, hardware, and ToyBox MCP servers to the local Codex config."],
            ),
        ]

        integrations: list[LocalIntegrationRecord] = []
        for item_id, name, category, needles, description, next_steps in grouped:
            found = []
            for needle in needles:
                normalized = needle.lower()
                if normalized == "mcp" and mcp_servers:
                    found.extend(mcp_servers)
                elif normalized in detected or normalized.replace(" ", "") in detected:
                    found.append(needle)
                elif normalized in path_text or normalized.replace(" ", "") in path_text:
                    found.append(needle)
                elif normalized in printer_text or normalized.replace(" ", "") in printer_text:
                    found.append(needle)
            found = sorted(set(found))
            integrations.append(
                LocalIntegrationRecord(
                    id=item_id,
                    name=name,
                    category=category,
                    status="ready" if found else "missing",
                    host=host,
                    description=description,
                    detected_tools=found,
                    paths=[
                        value for value in path_values
                        if any(needle.lower().replace(" ", "") in value.lower().replace(" ", "") for needle in needles)
                    ][:12],
                    detail=(
                        f"Detected: {', '.join(found)}"
                        if found
                        else "No matching workstation tools were detected in the registered snapshot."
                    ),
                    next_steps=next_steps,
                    metadata={
                        "snapshot_checked_at": snapshot.get("checked_at"),
                        "printer_matches": [
                            item for item in printers
                            if any(needle.lower() in " ".join(str(item.get(key, "")) for key in ("name", "driver", "port")).lower() for needle in needles)
                        ][:6],
                    },
                )
            )
        return integrations

    def _recommendations(self, integrations: list[LocalIntegrationRecord]) -> list[IntegrationRecommendation]:
        ready_ids = {item.id for item in integrations if item.status == "ready"}
        recommendations = [
            IntegrationRecommendation(
                id="install-shopify-mcp",
                title="Add Shopify MCP/order bridge",
                priority="high",
                detail="ToyBox3D needs a scoped Shopify order polling layer before it can listen for real orders.",
                action="Create a Shopify app token flow and an Edison MCP tool that reads unfulfilled orders without storing secrets in the repo.",
            ),
            IntegrationRecommendation(
                id="add-desktop-tools-bridge",
                title="Add PC desktop tools bridge",
                priority="high",
                detail="Fusion 360, Blockbench, Bambu Studio, OrcaSlicer, Cura, and DYMO live on the main PC, so Edison needs a controlled PC-side bridge to use them.",
                action="Run a local MCP server on the PC with allowlisted app launchers, file roots, CAD scripts, slicer commands, printer commands, and artifact upload back to Edison.",
            ),
            IntegrationRecommendation(
                id="add-fusion360-cad-mcp",
                title="Add Fusion 360 CAD MCP",
                priority="high",
                detail="Fusion 360 can be automated by generating Fusion Python scripts and running them through a local desktop bridge.",
                action="Create tools for generate_cad_script, run_fusion_script, export_step, export_stl, and return_artifact.",
            ),
            IntegrationRecommendation(
                id="add-printer-mcp",
                title="Add printer and slicer MCP tools",
                priority="high",
                detail="Bambu/Orca/Cura tools are useful once Edison can map products to slicer profiles and printers.",
                action="Expose printer status, queue, slicing, camera, and filament/color slots through scoped MCP tools.",
            ),
            IntegrationRecommendation(
                id="add-dymo-label-printing",
                title="Add DYMO label printing",
                priority="high",
                detail="A DYMO LabelWriter 5XL can print Shopify shipping labels once labels are generated or downloaded.",
                action="Add a PC-side label-print tool that targets the configured DYMO printer and reports success/failure back to ToyBox3D.",
            ),
            IntegrationRecommendation(
                id="add-text-notifications",
                title="Add text and push notifications",
                priority="high",
                detail="Production failures, paused printers, failed labels, and urgent Shopify exceptions should notify you outside the web UI.",
                action="Add provider settings for Twilio/Pushover/ntfy/email and a notification policy for print-farm errors.",
            ),
            IntegrationRecommendation(
                id="minecraft-asset-pipeline",
                title="Add Minecraft 1.7.10 export pipeline",
                priority="medium",
                detail="Minecraft generation modes need exporters for texture packs, structures, and Blockbench-compatible model specs.",
                action="Add resource-pack zip export, structure schematic/export hooks, and Blockbench model handoff.",
            ),
            IntegrationRecommendation(
                id="register-workstation-codex",
                title="Register Edison MCP servers in Codex",
                priority="medium",
                detail="Codex is present on the main PC, so Edison can expose knowledge, hardware, workspace, and media tools to it.",
                action="Generate a local MCP config pointing Codex at Edison stdio or HTTP bridge tools.",
            ),
        ]
        if "workstation-print-tools" in ready_ids:
            for recommendation in recommendations:
                if recommendation.id == "add-printer-mcp":
                    recommendation.metadata["detected_workstation_print_tools"] = True
                    break
        return recommendations
