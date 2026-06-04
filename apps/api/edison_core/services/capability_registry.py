from __future__ import annotations

from edison_core.config import EdisonSettings
from edison_core.schemas import CapabilityStatus, MCPServerRecord, PluginIntegrationRecord
from edison_core.services.hardware_devices import HardwareDeviceService
from edison_core.services.knowledge_store import KnowledgeStore
from edison_core.services.media_orchestrator import MediaOrchestrator
from edison_core.services.personal_workspace import PersonalWorkspaceStore
from edison_core.services.workspace_tools import WorkspaceTools


class CapabilityRegistry:
    def __init__(
        self,
        settings: EdisonSettings,
        hardware: HardwareDeviceService,
        knowledge: KnowledgeStore,
        workspace: WorkspaceTools,
        media: MediaOrchestrator,
        personal: PersonalWorkspaceStore,
    ) -> None:
        self.settings = settings
        self.hardware = hardware
        self.knowledge = knowledge
        self.workspace = workspace
        self.media = media
        self.personal = personal

    def snapshot(self) -> CapabilityStatus:
        knowledge_status = self.knowledge.status()
        hardware_status = self.hardware.snapshot()
        hailo = next((item for item in hardware_status.accelerators if item.kind == "hailo8"), None)
        camera_ready = any(camera.status == "ready" for camera in hardware_status.cameras)

        mcp_servers = [
            MCPServerRecord(
                id="edison-knowledge",
                name="Edison Knowledge MCP",
                status="ready" if knowledge_status.chunk_count else "staged",
                transport="stdio",
                description="Search, ingest, and summarize Edison RAG sources.",
                tools=["knowledge.status", "knowledge.search", "knowledge.sources", "knowledge.ingest_text"],
                command="python -m edison_core.mcp.knowledge",
                source="odysseus-inspired",
                detail=(
                    f"{knowledge_status.source_count} sources and {knowledge_status.chunk_count} chunks are indexed."
                    if knowledge_status.chunk_count
                    else "Ready to use after the first knowledge ingest."
                ),
            ),
            MCPServerRecord(
                id="edison-workspace",
                name="Edison Workspace MCP",
                status="ready",
                transport="stdio",
                description="Expose safe repository search, file reading, patch preview, and approved command runs.",
                tools=["workspace.summary", "workspace.search", "workspace.index_search", "workspace.read"],
                command="python -m edison_core.mcp.workspace",
                source="odysseus-inspired",
                detail=f"Workspace root: {self.settings.workspace_roots[0]}",
            ),
            MCPServerRecord(
                id="edison-media",
                name="Edison Media MCP",
                status="staged",
                transport="stdio",
                description="Create image, video, audio, and mesh jobs and return artifacts into chat.",
                tools=["media.create_job", "media.sync_job", "media.deliver_artifact", "artifacts.download"],
                command="python -m edison_core.mcp.media",
                source="odysseus-inspired",
                detail="Media orchestration APIs are ready; the standalone stdio MCP wrapper is staged next.",
            ),
            MCPServerRecord(
                id="edison-camera",
                name="Edison Camera MCP",
                status="staged" if camera_ready else "missing",
                transport="stdio",
                description="Capture Brio frames, run local VLM analysis, and report Hailo object-detection readiness.",
                tools=["camera.snapshot", "camera.analyze_frame", "camera.vision_status"],
                command="python -m edison_core.mcp.camera",
                source="odysseus-inspired",
                detail="Camera APIs are ready; the standalone stdio MCP wrapper is staged next." if camera_ready else "No ready capture-capable camera was detected.",
            ),
            MCPServerRecord(
                id="edison-hardware",
                name="Edison Hardware MCP",
                status="ready",
                transport="stdio",
                description="Report GPU, fan, Hailo, camera, and storage state for agent planning.",
                tools=["hardware.status", "hardware.fans", "hailo.status", "camera.status"],
                command="python -m edison_core.mcp.hardware",
                source="odysseus-inspired",
                detail="Hardware status MCP server is runnable; Hailo readiness is reported inside tool results.",
                metadata={"hailo_status": hailo.status if hailo else "not_detected"},
            ),
            MCPServerRecord(
                id="edison-organizer",
                name="Edison Organizer MCP",
                status="staged",
                transport="stdio",
                description="Let agent workflows read and update local tasks, notes, calendar items, and documents.",
                tools=["organizer.list", "organizer.create", "documents.list", "documents.ingest"],
                command="python -m edison_core.mcp.organizer",
                source="odysseus-inspired",
                detail="Organizer and document APIs are ready; the standalone stdio MCP wrapper is staged next.",
            ),
        ]

        plugins = [
            PluginIntegrationRecord(
                id="edison-codex",
                name="Edison Codex Plugin",
                status="staged",
                target="codex",
                description="Codex-style plugin bundle that can call scoped Edison capability endpoints.",
                scopes=["chat", "knowledge", "workspace", "media", "hardware"],
                setup_commands=[
                    "export EDISON_URL=http://192.168.1.34:5173",
                    "python scripts/export-edison-codex-plugin.py --out /tmp/edison-codex-plugin.zip",
                    "codex plugin add edison@personal",
                ],
                detail="Plugin manifest and scoped endpoints are staged in Edison; token issuance can be added next.",
                metadata={"reference": "Odysseus integrations/codex"},
            ),
            PluginIntegrationRecord(
                id="edison-claude-code",
                name="Edison Claude Code Skill",
                status="staged",
                target="claude-code",
                description="Claude Code skill bundle for Edison knowledge, workspace, media, and hardware tools.",
                scopes=["chat", "knowledge", "workspace", "media", "hardware"],
                setup_commands=[
                    "export EDISON_URL=http://192.168.1.34:5173",
                    "python scripts/export-edison-claude-skill.py --out /tmp/edison-claude-skill.zip",
                    "python -m zipfile -e /tmp/edison-claude-skill.zip ~/.claude/",
                ],
                detail="Skill bundle shape is staged; server-side scope tokens can be layered on top.",
                metadata={"reference": "Odysseus integrations/claude"},
            ),
            PluginIntegrationRecord(
                id="edison-mcp-client",
                name="Generic MCP Client Bridge",
                status="staged",
                target="generic",
                description="MCP-compatible bridge for local tools that should talk to Edison over scoped APIs.",
                scopes=["capabilities", "knowledge", "workspace", "media", "camera"],
                setup_commands=[
                    "python scripts/export-edison-mcp-config.py --out /tmp/edison-mcp.json",
                ],
                detail="Catalog is available now; process supervision for external MCP servers is the next hardening step.",
                metadata={"reference": "Odysseus mcp_servers"},
            ),
        ]

        return CapabilityStatus(
            mcp_servers=mcp_servers,
            plugins=plugins,
            knowledge_presets=[
                "coding-core",
                "ai-foundations",
                "edison-ops",
                "odysseus-features",
                "mcp-agents",
                "local-ai-hardware",
            ],
            attribution=[
                "Feature mapping inspired by Odysseus MIT-licensed MCP, plugin, memory, and integration surfaces.",
            ],
            detail="Edison capability registry is ready for UI, agent, and external-tool discovery.",
        )
