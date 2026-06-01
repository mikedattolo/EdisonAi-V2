from __future__ import annotations

from fastapi import Request

from edison_core.services.comfyui_client import ComfyUIClient
from edison_core.services.conversation_store import ConversationStore
from edison_core.services.generation_store import GenerationStore
from edison_core.services.invokeai_client import InvokeAIClient
from edison_core.services.model_gateway import ModelGateway
from edison_core.services.media_orchestrator import MediaOrchestrator
from edison_core.services.modly_client import ModlyClient
from edison_core.services.knowledge_store import KnowledgeStore
from edison_core.services.model_registry import ModelRegistry, ModelRouter
from edison_core.services.personal_workspace import PersonalWorkspaceStore
from edison_core.services.session_state import SessionStateStore
from edison_core.services.system_status import GPUFanControlService, SystemStatusService
from edison_core.services.wan22_client import Wan22Client
from edison_core.services.workspace_tools import WorkspaceTools


def get_conversation_store(request: Request) -> ConversationStore:
    return request.app.state.conversation_store


def get_session_state_store(request: Request) -> SessionStateStore:
    return request.app.state.session_state_store


def get_personal_workspace_store(request: Request) -> PersonalWorkspaceStore:
    return request.app.state.personal_workspace_store


def get_generation_store(request: Request) -> GenerationStore:
    return request.app.state.generation_store


def get_model_registry(request: Request) -> ModelRegistry:
    return request.app.state.model_registry


def get_model_router(request: Request) -> ModelRouter:
    return request.app.state.model_router


def get_model_gateway(request: Request) -> ModelGateway:
    return request.app.state.model_gateway


def get_comfyui_client(request: Request) -> ComfyUIClient:
    return request.app.state.comfyui_client


def get_workspace_tools(request: Request) -> WorkspaceTools:
    return request.app.state.workspace_tools


def get_knowledge_store(request: Request) -> KnowledgeStore:
    return request.app.state.knowledge_store


def get_invokeai_client(request: Request) -> InvokeAIClient:
    return request.app.state.invokeai_client


def get_wan22_client(request: Request) -> Wan22Client:
    return request.app.state.wan22_client


def get_modly_client(request: Request) -> ModlyClient:
    return request.app.state.modly_client


def get_media_orchestrator(request: Request) -> MediaOrchestrator:
    return request.app.state.media_orchestrator


def get_status_service(request: Request) -> SystemStatusService:
    return request.app.state.status_service


def get_fan_control_service(request: Request) -> GPUFanControlService:
    return request.app.state.fan_control_service
