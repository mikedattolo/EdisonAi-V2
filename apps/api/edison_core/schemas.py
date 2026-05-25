from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatMode(str, Enum):
    INSTANT = "instant"
    CHAT = "chat"
    REASONING = "reasoning"
    CODING = "coding"
    AGENT = "agent"
    SWARM = "swarm"
    CREATIVE = "creative"
    MEDIA = "media"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ModelCapability(str, Enum):
    CHAT = "chat"
    FAST_CHAT = "fast-chat"
    REASONING = "reasoning"
    CODING = "coding"
    VISION = "vision"
    TOOL_CALLING = "tool-calling"
    LONG_CONTEXT = "long-context"
    JSON_STRUCTURED_OUTPUT = "JSON-structured-output"
    MULTIMODAL = "multimodal"
    EMBEDDINGS = "embeddings"
    RERANKING = "reranking"
    MEDIA = "media"


class ModelStatus(str, Enum):
    READY = "ready"
    NOT_CONFIGURED = "not_configured"
    OFFLINE = "offline"
    DEGRADED = "degraded"


class ArtifactKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MESH = "mesh"
    DOCUMENT = "document"
    CODE = "code"
    DATA = "data"
    OTHER = "other"


class JobType(str, Enum):
    IMAGE = "image"
    IMAGE_EDIT = "image_edit"
    VIDEO = "video"
    MESH = "mesh"
    AUDIO = "audio"
    DOCUMENT = "document"
    CODE = "code"
    SYSTEM = "system"


class JobStatus(str, Enum):
    QUEUED = "queued"
    SETUP_REQUIRED = "setup_required"
    LOADING = "loading"
    GENERATING = "generating"
    ENCODING = "encoding"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


class ModelProfile(BaseModel):
    id: str
    display_name: str
    provider: str
    status: ModelStatus = ModelStatus.NOT_CONFIGURED
    capabilities: list[ModelCapability] = Field(default_factory=list)
    context_window: int = 8192
    max_output_tokens: int = 1024
    endpoint_url: str | None = None
    preferred_gpu: str | None = None
    license: str | None = None
    tags: list[str] = Field(default_factory=list)
    safety_notes: str | None = None
    notes: str | None = None


class ModelSelection(BaseModel):
    mode: ChatMode
    required_capabilities: list[ModelCapability]
    model: ModelProfile
    reason: str


class InferenceRequest(BaseModel):
    prompt: str
    mode: ChatMode = ChatMode.CHAT
    preferred_model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InferenceResponse(BaseModel):
    model_id: str
    content: str
    finish_reason: Literal["stop", "length", "error", "not_configured"] = "stop"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    mode: ChatMode = ChatMode.CHAT
    preferred_model: str | None = None
    memory_enabled: bool = True
    workspace_path: str | None = None
    workspace_context_paths: list[str] = Field(default_factory=list, max_length=12)
    include_workspace_context: bool = True
    max_workspace_context_matches: int = Field(default=5, ge=0, le=20)
    include_knowledge_context: bool = True
    knowledge_query: str | None = None
    max_knowledge_context_matches: int = Field(default=5, ge=0, le=20)


class ChatResponse(BaseModel):
    conversation: "ConversationWithMessages"
    user_message: "MessageRecord"
    assistant_message: "MessageRecord"
    inference: InferenceResponse
    model_selection: ModelSelection


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    mode: ChatMode = ChatMode.CHAT
    memory_enabled: bool = True


class ConversationRecord(BaseModel):
    id: str
    title: str
    mode: ChatMode
    memory_enabled: bool
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    role: MessageRole = MessageRole.USER
    content: str = Field(min_length=1)
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageRecord(BaseModel):
    id: str
    conversation_id: str
    role: MessageRole
    content: str
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ConversationWithMessages(ConversationRecord):
    messages: list[MessageRecord] = Field(default_factory=list)


class SessionStateUpdate(BaseModel):
    current_task: str | None = None
    current_project: str | None = None
    active_domain: str | None = None
    last_tool_used: str | None = None
    last_generated_artifact: str | None = None
    task_stage: str | None = None
    last_intent: str | None = None
    current_plan: list[str] | None = None
    pending_approval: dict[str, Any] | None = None
    selected_mode: ChatMode | None = None
    selected_model: str | None = None


class SessionStateRecord(BaseModel):
    session_id: str
    current_task: str | None = None
    current_project: str | None = None
    active_domain: str | None = None
    last_tool_used: str | None = None
    last_generated_artifact: str | None = None
    task_stage: str | None = None
    last_intent: str | None = None
    current_plan: list[str] = Field(default_factory=list)
    pending_approval: dict[str, Any] | None = None
    selected_mode: ChatMode = ChatMode.CHAT
    selected_model: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class ArtifactCreate(BaseModel):
    kind: ArtifactKind
    title: str
    path: str
    mime_type: str | None = None
    source_job_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactRecord(ArtifactCreate):
    id: str
    created_at: datetime


class JobCreate(BaseModel):
    job_type: JobType
    title: str
    prompt: str | None = None
    backend: str = "manual"
    source_artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    id: str
    job_type: JobType
    status: JobStatus
    title: str
    prompt: str | None = None
    backend: str = "manual"
    source_artifact_id: str | None = None
    result_artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class JobEventRecord(BaseModel):
    id: str
    job_id: str
    status: JobStatus
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ComfyUIStatus(BaseModel):
    status: Literal["ready", "offline", "setup_required"]
    base_url: str | None = None
    reachable: bool = False
    queue_running: int = 0
    queue_pending: int = 0
    detail: str
    checked_at: datetime = Field(default_factory=utc_now)
    system: dict[str, Any] = Field(default_factory=dict)


class MediaBackendStatus(BaseModel):
    status: Literal["ready", "offline", "setup_required"]
    base_url: str | None = None
    reachable: bool = False
    detail: str
    checked_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MediaSystemStatus(BaseModel):
    service: str = "media"
    comfyui: ComfyUIStatus
    invokeai: MediaBackendStatus
    wan22: MediaBackendStatus
    modly: MediaBackendStatus
    job_counts: dict[str, int] = Field(default_factory=dict)


class WorkspaceEntry(BaseModel):
    path: str
    name: str
    kind: Literal["file", "directory"]
    size_bytes: int | None = None
    modified_at: datetime | None = None
    language: str | None = None


class WorkspaceFile(BaseModel):
    path: str
    name: str
    size_bytes: int
    modified_at: datetime | None = None
    language: str | None = None
    content: str
    truncated: bool = False


class WorkspaceSummary(BaseModel):
    service: str = "workspace"
    root_name: str
    root_path: str
    file_count: int
    directory_count: int
    languages: dict[str, int] = Field(default_factory=dict)
    package_managers: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)


class WorkspaceSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    max_results: int = Field(default=50, ge=1, le=200)
    case_sensitive: bool = False
    include_content: bool = True


class WorkspaceSearchMatch(BaseModel):
    path: str
    name: str
    kind: Literal["file", "content"]
    line_number: int | None = None
    line_text: str | None = None
    language: str | None = None


class WorkspaceEntrypoint(BaseModel):
    path: str
    kind: str
    language: str | None = None
    description: str


class WorkspaceCommand(BaseModel):
    name: str
    command: str
    cwd: str
    category: Literal["install", "dev", "build", "test", "lint", "typecheck", "format", "run", "other"]
    source: str


class WorkspaceScan(BaseModel):
    service: str = "workspace-scan"
    root_name: str
    root_path: str
    stacks: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    entrypoints: list[WorkspaceEntrypoint] = Field(default_factory=list)
    commands: list[WorkspaceCommand] = Field(default_factory=list)
    test_targets: list[str] = Field(default_factory=list)
    config_files: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class WorkspaceInstructionFile(BaseModel):
    path: str
    name: str
    instruction_type: Literal["repository", "path", "agent", "prompt"]
    apply_to: str | None = None
    size_bytes: int
    modified_at: datetime | None = None


class WorkspaceInstructionContext(BaseModel):
    target_path: str
    selected_files: list[WorkspaceInstructionFile] = Field(default_factory=list)
    combined_text: str
    warnings: list[str] = Field(default_factory=list)


class WorkspaceIndexStatus(BaseModel):
    service: str = "workspace-index"
    indexed_file_count: int = 0
    index_built_at: datetime | None = None
    latest_workspace_mtime: datetime | None = None
    is_stale: bool = False
    excluded_paths: list[str] = Field(default_factory=list)


class WorkspaceIndexSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=240)
    max_results: int = Field(default=20, ge=1, le=100)


class WorkspaceIndexSearchMatch(BaseModel):
    path: str
    language: str | None = None
    score: float
    snippet: str
    line_number: int | None = None


class WorkspacePatchRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    proposed_content: str
    summary: str | None = Field(default=None, max_length=240)
    create_if_missing: bool = True
    expected_sha256: str | None = None


class WorkspacePatchApplyRequest(WorkspacePatchRequest):
    approved: bool = False


class WorkspacePatchPreview(BaseModel):
    job: JobRecord | None = None
    path: str
    exists: bool
    language: str | None = None
    current_sha256: str | None = None
    proposed_sha256: str
    diff: str
    additions: int
    deletions: int
    risk_flags: list[str] = Field(default_factory=list)
    requires_approval: bool = True


class WorkspacePatchApplyResult(BaseModel):
    job: JobRecord | None = None
    path: str
    applied: bool
    message: str
    preview: WorkspacePatchPreview
    file: WorkspaceFile

class WorkspaceCommandRunRequest(BaseModel):
    command: str = Field(min_length=1, max_length=500)
    cwd: str = "."
    timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    approved: bool = False

class WorkspaceCommandRunResult(BaseModel):
    job: JobRecord
    command: str
    cwd: str
    exit_code: int | None = None
    status: Literal["complete", "error", "timeout"]
    duration_ms: int
    stdout: str = ""
    stderr: str = ""
    output_truncated: bool = False


class KnowledgeSourceRecord(BaseModel):
    id: str
    kind: Literal["text", "url", "wikipedia", "local_file"]
    title: str
    uri: str | None = None
    language: str | None = None
    license: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchMatch(BaseModel):
    source_id: str
    source_title: str
    source_kind: str
    path: str | None = None
    score: float
    snippet: str


class KnowledgeStatus(BaseModel):
    service: str = "knowledge-base"
    source_count: int
    chunk_count: int
    latest_ingest_at: datetime | None = None


class KnowledgeIngestTextRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    text: str = Field(min_length=1)
    uri: str | None = None
    language: str | None = None
    license: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeIngestUrlRequest(BaseModel):
    url: str = Field(min_length=6, max_length=1024)
    title: str | None = Field(default=None, max_length=240)
    language: str | None = None
    license: str | None = None


class KnowledgeIngestWikipediaRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    language: str = Field(default="en", min_length=2, max_length=8)


class KnowledgeIngestLocalRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    glob: str = Field(default="**/*")
    max_files: int = Field(default=200, ge=1, le=2000)


class KnowledgeIngestPresetRequest(BaseModel):
    preset: Literal["coding-core", "ai-foundations"]


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=240)
    max_results: int = Field(default=10, ge=1, le=50)


class GPUDevice(BaseModel):
    index: int
    name: str
    vram_total_mb: int | None = None
    vram_used_mb: int | None = None
    temperature_c: int | None = None
    utilization_percent: int | None = None
    power_draw_watts: float | None = None
    fan_speed_percent: int | None = None


class GPUFanCurvePoint(BaseModel):
    temperature_c: int = Field(ge=0, le=110)
    speed_percent: int = Field(ge=0, le=100)


class GPUFanPolicy(BaseModel):
    mode: Literal["auto", "manual", "curve"] = "auto"
    manual_speed_percent: int = Field(default=35, ge=0, le=100)
    curve: list[GPUFanCurvePoint] = Field(default_factory=list, max_length=8)


class GPUFanControlState(BaseModel):
    gpu: GPUDevice
    policy: GPUFanPolicy
    target_speed_percent: int | None = None
    hardware_control_enabled: bool = False
    backend: str = "monitor"
    applied: bool = False
    detail: str


class GPUFanControlUpdate(BaseModel):
    mode: Literal["auto", "manual", "curve"]
    manual_speed_percent: int = Field(default=35, ge=0, le=100)
    curve: list[GPUFanCurvePoint] = Field(default_factory=list, max_length=8)


class GPUFanControlSnapshot(BaseModel):
    service: str = "gpu-fan-control"
    hardware_control_enabled: bool = False
    backend: str = "monitor"
    controllers: list[GPUFanControlState] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class SystemStatus(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
    database_path: str
    model_count: int
    configured_model_count: int
    gpu_devices: list[GPUDevice] = Field(default_factory=list)
    storage_roots: dict[str, str]