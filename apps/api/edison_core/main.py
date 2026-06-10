from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from edison_core.api import (
    routes_agents,
    routes_capabilities,
    routes_chat,
    routes_conversations,
    routes_desktop_bridge,
    routes_hardware,
    routes_health,
    routes_jobs,
    routes_knowledge,
    routes_media,
    routes_models,
    routes_personal,
    routes_settings,
    routes_sessions,
    routes_toybox,
    routes_workspace,
    routes_workspace_agent,
    routes_realtime,
)
from edison_core.config import EdisonSettings, load_settings
from edison_core.database import SQLiteDatabase
from edison_core.services.agent_run_store import AgentRunStore
from edison_core.services.capability_registry import CapabilityRegistry
from edison_core.services.comfyui_client import ComfyUIClient
from edison_core.services.conversation_store import ConversationStore
from edison_core.services.creator_studio import CreatorStudioService
from edison_core.services.desktop_bridge import DesktopBridgeClient
from edison_core.services.generation_store import GenerationStore
from edison_core.services.hardware_devices import HardwareDeviceService
from edison_core.services.integration_discovery import IntegrationDiscoveryService
from edison_core.services.invokeai_client import InvokeAIClient
from edison_core.services.model_gateway import ModelGateway
from edison_core.services.media_orchestrator import MediaOrchestrator
from edison_core.services.modly_client import ModlyClient
from edison_core.services.knowledge_store import KnowledgeStore
from edison_core.services.model_registry import ModelRegistry, ModelRouter
from edison_core.services.personal_workspace import PersonalWorkspaceStore
from edison_core.services.runtime_settings import RuntimeSettingsStore
from edison_core.services.session_state import SessionStateStore
from edison_core.services.system_status import GPUFanControlService, SystemStatusService
from edison_core.services.toybox_store import ToyBoxStore
from edison_core.services.wan22_client import Wan22Client
from edison_core.services.realtime import RealtimeService
from edison_core.services.workspace_agent import AgentRunCoordinator, WorkspaceAgent
from edison_core.services.workspace_projects import WorkspaceProjectManager
from edison_core.services.workspace_tools import WorkspaceTools


def create_app(settings: EdisonSettings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    database = SQLiteDatabase(resolved_settings.database_path)
    agent_run_store = AgentRunStore(database)
    conversation_store = ConversationStore(database)
    session_state_store = SessionStateStore(database)
    generation_store = GenerationStore(database)
    knowledge_store = KnowledgeStore(database, resolved_settings.workspace_roots[0])
    personal_workspace_store = PersonalWorkspaceStore(database)
    runtime_settings_store = RuntimeSettingsStore(resolved_settings)
    desktop_bridge_client = DesktopBridgeClient(runtime_settings_store)
    toybox_store = ToyBoxStore(database)
    agent_run_store.initialize()
    conversation_store.initialize()
    session_state_store.initialize()
    generation_store.initialize()
    knowledge_store.initialize()
    personal_workspace_store.initialize()
    toybox_store.initialize()

    model_registry = ModelRegistry.from_file(resolved_settings.model_registry_path)
    model_router = ModelRouter(model_registry)
    model_gateway = ModelGateway(model_router)
    comfyui_client = ComfyUIClient(
        resolved_settings.comfyui_base_url,
        timeout_seconds=resolved_settings.comfyui_timeout_seconds,
    )
    invokeai_client = InvokeAIClient(
        resolved_settings.invokeai_base_url,
        timeout_seconds=resolved_settings.invokeai_timeout_seconds,
    )
    wan22_client = Wan22Client(
        resolved_settings.wan22_base_url,
        timeout_seconds=resolved_settings.wan22_timeout_seconds,
    )
    modly_client = ModlyClient(
        resolved_settings.modly_base_url,
        timeout_seconds=resolved_settings.modly_timeout_seconds,
    )
    creator_studio_service = CreatorStudioService(resolved_settings)
    media_orchestrator = MediaOrchestrator(
        resolved_settings,
        comfyui_client,
        invokeai_client,
        wan22_client,
        modly_client,
    )
    status_service = SystemStatusService(resolved_settings, model_registry)
    fan_control_service = GPUFanControlService(resolved_settings, status_service.gpu_manager)
    hardware_device_service = HardwareDeviceService(resolved_settings)
    integration_discovery_service = IntegrationDiscoveryService(resolved_settings)
    workspace_tools = WorkspaceTools(resolved_settings.workspace_roots[0])
    workspace_project_manager = WorkspaceProjectManager(resolved_settings)
    agent_run_coordinator = AgentRunCoordinator()
    workspace_agent = WorkspaceAgent(model_gateway, agent_run_store, agent_run_coordinator, knowledge_store)
    realtime_service = RealtimeService()
    capability_registry = CapabilityRegistry(
        resolved_settings,
        hardware_device_service,
        knowledge_store,
        workspace_tools,
        media_orchestrator,
        personal_workspace_store,
        integration_discovery_service,
    )

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description="Local-first EDISON V2 core API foundation.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = resolved_settings
    app.state.agent_run_store = agent_run_store
    app.state.conversation_store = conversation_store
    app.state.session_state_store = session_state_store
    app.state.generation_store = generation_store
    app.state.knowledge_store = knowledge_store
    app.state.personal_workspace_store = personal_workspace_store
    app.state.runtime_settings_store = runtime_settings_store
    app.state.desktop_bridge_client = desktop_bridge_client
    app.state.toybox_store = toybox_store
    app.state.model_registry = model_registry
    app.state.model_router = model_router
    app.state.model_gateway = model_gateway
    app.state.comfyui_client = comfyui_client
    app.state.invokeai_client = invokeai_client
    app.state.wan22_client = wan22_client
    app.state.modly_client = modly_client
    app.state.creator_studio_service = creator_studio_service
    app.state.media_orchestrator = media_orchestrator
    app.state.status_service = status_service
    app.state.fan_control_service = fan_control_service
    app.state.hardware_device_service = hardware_device_service
    app.state.integration_discovery_service = integration_discovery_service
    app.state.workspace_tools = workspace_tools
    app.state.workspace_project_manager = workspace_project_manager
    app.state.agent_run_coordinator = agent_run_coordinator
    app.state.workspace_agent = workspace_agent
    app.state.realtime_service = realtime_service
    app.state.capability_registry = capability_registry

    app.include_router(routes_health.router)
    app.include_router(routes_agents.router)
    app.include_router(routes_capabilities.router)
    app.include_router(routes_hardware.router)
    app.include_router(routes_desktop_bridge.router)
    app.include_router(routes_models.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_knowledge.router)
    app.include_router(routes_personal.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_media.router)
    app.include_router(routes_toybox.router)
    app.include_router(routes_workspace.router)
    app.include_router(routes_workspace_agent.router)
    app.include_router(routes_realtime.router)
    app.include_router(routes_conversations.router)
    app.include_router(routes_sessions.router)
    return app
