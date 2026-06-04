from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatMode(str, Enum):
    AUTO = "auto"
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
    mode: ChatMode = ChatMode.AUTO
    preferred_model: str | None = None
    agent_enabled: bool = False
    memory_enabled: bool = True
    workspace_path: str | None = None
    workspace_context_paths: list[str] = Field(default_factory=list, max_length=12)
    include_workspace_context: bool = True
    max_workspace_context_matches: int = Field(default=5, ge=0, le=20)
    include_knowledge_context: bool = True
    knowledge_query: str | None = None
    max_knowledge_context_matches: int = Field(default=5, ge=0, le=20)
    include_personal_context: bool = False
    max_personal_context_items: int = Field(default=8, ge=0, le=20)


class ChatResponse(BaseModel):
    conversation: "ConversationWithMessages"
    user_message: "MessageRecord"
    assistant_message: "MessageRecord"
    inference: InferenceResponse
    model_selection: ModelSelection


class AgentRunStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaGenerationMode(str, Enum):
    IMAGE = "image"
    MINECRAFT_TEXTURE = "minecraft_texture"
    MINECRAFT_MODEL = "minecraft_model"
    MINECRAFT_WORLD = "minecraft_world"
    MINECRAFT_STRUCTURE = "minecraft_structure"
    MINECRAFT_TEXTURE_PACK = "minecraft_texture_pack"
    PRODUCT_RENDER = "product_render"
    SOCIAL_MEDIA_CONTENT = "social_media_content"


class AgentRunEventKind(str, Enum):
    STATUS = "status"
    PLAN = "plan"
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    APPROVAL = "approval"
    ARTIFACT = "artifact"
    ERROR = "error"


class AgentRunCreate(BaseModel):
    title: str | None = Field(default=None, max_length=180)
    prompt: str = Field(min_length=1)
    mode: ChatMode = ChatMode.AGENT
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunStatusUpdate(BaseModel):
    status: AgentRunStatus
    current_step: str | None = Field(default=None, max_length=240)
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunEventCreate(BaseModel):
    kind: AgentRunEventKind = AgentRunEventKind.STATUS
    title: str = Field(min_length=1, max_length=180)
    body: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunRecord(BaseModel):
    id: str
    title: str
    prompt: str
    mode: ChatMode
    status: AgentRunStatus
    progress_percent: int = Field(default=0, ge=0, le=100)
    current_step: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AgentRunEventRecord(BaseModel):
    id: str
    run_id: str
    kind: AgentRunEventKind
    title: str
    body: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AgentRunWithEvents(AgentRunRecord):
    events: list[AgentRunEventRecord] = Field(default_factory=list)


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


class MediaJobDeliveryRequest(BaseModel):
    conversation_id: str | None = None


class WorkspaceRootRecord(BaseModel):
    id: str
    name: str
    path: str
    kind: Literal["app", "project"]
    description: str | None = None
    created_at: datetime | None = None


class WorkspaceProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=2000)
    initialize_git: bool = True


class WorkspaceProjectRecord(WorkspaceRootRecord):
    kind: Literal["project"] = "project"


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
    kind: Literal["text", "url", "wikipedia", "local_file", "preset"]
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
    uri: str | None = None
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
    preset: Literal[
        "coding-core",
        "ai-foundations",
        "edison-ops",
        "odysseus-features",
        "mcp-agents",
        "local-ai-hardware",
    ]


class MCPServerRecord(BaseModel):
    id: str
    name: str
    status: Literal["ready", "staged", "missing", "disabled"]
    transport: Literal["stdio", "http", "sse"]
    description: str
    tools: list[str] = Field(default_factory=list)
    command: str | None = None
    source: str | None = None
    enabled: bool = True
    detail: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MediaGenerationRequest(BaseModel):
    mode: MediaGenerationMode
    prompt: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default=None, max_length=180)
    reference_artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MediaGenerationModeRecord(BaseModel):
    id: MediaGenerationMode
    label: str
    group: Literal["core", "minecraft", "commerce", "social"]
    job_type: JobType
    backend: str
    description: str
    reference_supported: bool = False
    output_hint: str
    prompt_hint: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PluginIntegrationRecord(BaseModel):
    id: str
    name: str
    status: Literal["ready", "staged", "missing", "disabled"]
    target: Literal["codex", "claude-code", "generic"]
    description: str
    setup_commands: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    detail: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocalIntegrationRecord(BaseModel):
    id: str
    name: str
    category: Literal[
        "mcp",
        "local-ai",
        "media",
        "minecraft",
        "3d-printing",
        "cad",
        "commerce",
        "developer",
        "automation",
        "hardware",
        "api",
        "notifications",
    ]
    status: Literal["ready", "staged", "missing", "disabled"]
    host: str
    description: str
    detected_tools: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    detail: str
    next_steps: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntegrationRecommendation(BaseModel):
    id: str
    title: str
    priority: Literal["high", "medium", "low"]
    detail: str
    action: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntegrationScanReport(BaseModel):
    service: str = "integration-discovery"
    checked_at: datetime = Field(default_factory=utc_now)
    integrations: list[LocalIntegrationRecord] = Field(default_factory=list)
    recommendations: list[IntegrationRecommendation] = Field(default_factory=list)
    detail: str


class ToyBoxProductionLane(BaseModel):
    id: str
    title: str
    status: Literal["ready", "staged", "missing"]
    description: str
    connected_integrations: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ToyBoxPrinterRecord(BaseModel):
    id: str
    name: str
    kind: Literal["bambu", "orca", "cura", "dymo", "generic"]
    status: Literal["ready", "staged", "missing"]
    role: Literal["printer", "slicer", "label_printer", "camera", "desktop_bridge"]
    detail: str
    paths: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToyBoxNotificationChannel(BaseModel):
    id: str
    name: str
    status: Literal["ready", "staged", "missing"]
    target: Literal["sms", "push", "email", "desktop"]
    detail: str
    setup_hint: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToyBoxManagerStatus(BaseModel):
    service: str = "toybox3d-manager"
    checked_at: datetime = Field(default_factory=utc_now)
    lanes: list[ToyBoxProductionLane] = Field(default_factory=list)
    printers: list[ToyBoxPrinterRecord] = Field(default_factory=list)
    notification_channels: list[ToyBoxNotificationChannel] = Field(default_factory=list)
    recommendations: list[IntegrationRecommendation] = Field(default_factory=list)
    detail: str


class CapabilityStatus(BaseModel):
    service: str = "capabilities"
    mcp_servers: list[MCPServerRecord] = Field(default_factory=list)
    plugins: list[PluginIntegrationRecord] = Field(default_factory=list)
    integrations: list[LocalIntegrationRecord] = Field(default_factory=list)
    recommendations: list[IntegrationRecommendation] = Field(default_factory=list)
    knowledge_presets: list[str] = Field(default_factory=list)
    attribution: list[str] = Field(default_factory=list)
    detail: str


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=240)
    max_results: int = Field(default=10, ge=1, le=50)


class OrganizerKind(str, Enum):
    TASK = "task"
    NOTE = "note"
    CALENDAR = "calendar"


class OrganizerStatus(str, Enum):
    ACTIVE = "active"
    DONE = "done"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class OrganizerItemCreate(BaseModel):
    kind: OrganizerKind
    title: str = Field(min_length=1, max_length=180)
    body: str = ""
    status: OrganizerStatus = OrganizerStatus.ACTIVE
    due_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=16)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrganizerItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    body: str | None = None
    status: OrganizerStatus | None = None
    due_at: datetime | None = None
    tags: list[str] | None = Field(default=None, max_length=16)
    metadata: dict[str, Any] | None = None


class OrganizerItemRecord(OrganizerItemCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class DocumentFormat(str, Enum):
    MARKDOWN = "markdown"
    TEXT = "text"


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    content: str = ""
    format: DocumentFormat = DocumentFormat.MARKDOWN
    tags: list[str] = Field(default_factory=list, max_length=16)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    content: str | None = None
    format: DocumentFormat | None = None
    tags: list[str] | None = Field(default=None, max_length=16)
    metadata: dict[str, Any] | None = None


class DocumentRecord(DocumentCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class SearchProvider(str, Enum):
    KNOWLEDGE = "knowledge"
    WORKSPACE = "workspace"
    DOCUMENTS = "documents"


class SearchCompareRequest(BaseModel):
    query: str = Field(min_length=1, max_length=240)
    providers: list[SearchProvider] = Field(
        default_factory=lambda: [
            SearchProvider.KNOWLEDGE,
            SearchProvider.WORKSPACE,
            SearchProvider.DOCUMENTS,
        ],
        max_length=6,
    )
    max_results: int = Field(default=5, ge=1, le=20)


class SearchCompareResult(BaseModel):
    provider: SearchProvider
    title: str
    subtitle: str | None = None
    snippet: str
    score: float
    uri: str | None = None
    path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchCompareResponse(BaseModel):
    query: str
    results: dict[SearchProvider, list[SearchCompareResult]]
    provider_counts: dict[SearchProvider, int]
    best_provider: SearchProvider | None = None


class HardwareAcceleratorRecord(BaseModel):
    id: str
    name: str
    kind: Literal["hailo8", "gpu", "other"]
    bus: Literal["pcie", "usb", "unknown"] = "unknown"
    status: Literal["ready", "detected", "driver_missing", "runtime_missing", "not_detected", "error"]
    detail: str
    pci_address: str | None = None
    vendor_id: str | None = None
    product_id: str | None = None
    device_nodes: list[str] = Field(default_factory=list)
    driver_loaded: bool = False
    runtime_available: bool = False
    runtime_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraDeviceRecord(BaseModel):
    id: str
    name: str
    status: Literal["ready", "detected", "permission_required", "offline", "error"]
    detail: str
    vendor_id: str | None = None
    product_id: str | None = None
    device_paths: list[str] = Field(default_factory=list)
    media_paths: list[str] = Field(default_factory=list)
    capture_path: str | None = None
    formats: list[str] = Field(default_factory=list, max_length=24)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HardwareStatus(BaseModel):
    service: str = "hardware"
    accelerators: list[HardwareAcceleratorRecord] = Field(default_factory=list)
    cameras: list[CameraDeviceRecord] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utc_now)


class HardwareControlAction(BaseModel):
    id: str
    title: str
    detail: str
    severity: Literal["info", "warning", "critical"] = "info"
    action_label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HardwareControlCenter(BaseModel):
    service: str = "hardware-control-center"
    overall_status: Literal["ready", "attention", "setup_required", "offline"]
    gpu_count: int = 0
    fan_controller_count: int = 0
    writable_fan_target_count: int = 0
    fan_backend: str = "monitor"
    fan_writes_enabled: bool = False
    hailo_status: str = "not_checked"
    camera_status: str = "not_checked"
    storage_roots: dict[str, str] = Field(default_factory=dict)
    actions: list[HardwareControlAction] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraSnapshotRequest(BaseModel):
    device_path: str | None = None
    width: int = Field(default=1280, ge=160, le=4096)
    height: int = Field(default=720, ge=120, le=2160)
    input_format: Literal["mjpeg", "yuyv422"] = "mjpeg"
    title: str | None = Field(default=None, max_length=160)


class CameraAnalyzeRequest(CameraSnapshotRequest):
    prompt: str = Field(
        default=(
            "Describe the visible scene from this camera frame. Identify objects, people, screens, "
            "tools, safety concerns, and anything Edison should pay attention to."
        ),
        min_length=1,
        max_length=1200,
    )


class CameraSnapshotResponse(BaseModel):
    camera: CameraDeviceRecord
    artifact: ArtifactRecord
    detail: str


class CameraVisionStatus(BaseModel):
    service: str = "camera-vision"
    status: Literal["ready", "setup_required", "offline", "error"]
    camera: CameraDeviceRecord | None = None
    backend: str | None = None
    feed_url: str | None = None
    detail: str
    labels: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraFrameAnalysisResponse(BaseModel):
    service: str = "camera-frame-analysis"
    status: Literal["complete", "setup_required", "error"]
    camera: CameraDeviceRecord
    artifact: ArtifactRecord
    summary: str
    model_id: str | None = None
    backend: str | None = None
    detections: list[str] = Field(default_factory=list)
    detail: str
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    target_fan_ids: list[int] = Field(default_factory=list)
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
