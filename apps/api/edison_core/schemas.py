from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    max_knowledge_context_matches: int = Field(default=8, ge=0, le=30)
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
    CREATOR_PHOTO = "creator_photo"
    CREATOR_VIDEO = "creator_video"
    CREATOR_DATASET = "creator_dataset"
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


class WorkspaceAgentStartRequest(BaseModel):
    task: str = Field(min_length=1, max_length=8000)
    root_id: str = "app"
    auto_run_commands: bool = False
    max_steps: int = Field(default=40, ge=1, le=120)
    preferred_model: str | None = None
    conversation_id: str | None = None


class WorkspaceAgentControlRequest(BaseModel):
    run_id: str = Field(min_length=1)
    action: Literal["approve", "deny", "stop"]
    step_id: str | None = None


class WorkspaceAgentControlResult(BaseModel):
    accepted: bool
    run_id: str
    action: str
    detail: str = ""


class EdisonServiceRestartRequest(BaseModel):
    services: list[Literal["edison-api", "edison-web"]] = Field(
        default_factory=lambda: ["edison-api", "edison-web"]
    )
    build_web: bool = True


class EdisonServiceRestartResult(BaseModel):
    scheduled: bool
    services: list[str] = Field(default_factory=list)
    web_build: str = "skipped"
    backend_ok: bool = True
    detail: str = ""


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


class CreatorStudioDatasetRecord(BaseModel):
    id: str
    name: str
    root_path: str
    kind: Literal["image", "video", "mixed", "unknown"] = "unknown"
    status: Literal["ready", "detected", "empty"] = "detected"
    item_count: int = 0
    trigger_token: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatorStudioAssetRecord(BaseModel):
    id: str
    name: str
    kind: Literal["workflow", "model", "script", "config", "document", "other"] = "other"
    status: Literal["available", "candidate", "cataloged"] = "available"
    source_path: str | None = None
    copied_path: str | None = None
    size_bytes: int | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatorStudioStatus(BaseModel):
    service: str = "creator-studio"
    status: Literal["ready", "setup_required", "offline", "error"]
    source_path: str | None = None
    normalized_root: str | None = None
    detail: str
    datasets: list[CreatorStudioDatasetRecord] = Field(default_factory=list)
    workflow_templates: list[str] = Field(default_factory=list)
    restricted_assets: list[CreatorStudioAssetRecord] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatorStudioAssistMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str = Field(min_length=1, max_length=8000)


class CreatorStudioAssistAction(BaseModel):
    mode: Literal["creator_photo", "creator_video", "creator_dataset"]
    title: str = Field(default="Creator action", max_length=160)
    prompt: str = Field(default="", max_length=4000)
    rationale: str | None = Field(default=None, max_length=600)
    dataset_hint: str | None = Field(default=None, max_length=160)


class CreatorStudioAssistRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[CreatorStudioAssistMessage] = Field(default_factory=list)
    preferred_model: str | None = None


class CreatorStudioAssistResponse(BaseModel):
    status: Literal["ok", "setup_required", "error"] = "ok"
    reply: str
    actions: list[CreatorStudioAssistAction] = Field(default_factory=list)
    model_id: str | None = None
    guardrails: list[str] = Field(default_factory=list)


# --- Creator Lab: managed datasets, LoRA/workflow toggles, VLM critique, training ---


class CreatorLabImage(BaseModel):
    id: str
    filename: str
    url: str
    size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    caption: str | None = None


class CreatorLabDataset(BaseModel):
    id: str
    name: str
    trigger_token: str
    lora_type: str = "sdxl"
    base_model: str | None = None
    workflow: str | None = None
    notes: str | None = None
    status: Literal["empty", "ready"] = "empty"
    image_count: int = 0
    created_at: str | None = None
    images: list[CreatorLabImage] = Field(default_factory=list)


class CreatorLabLoraType(BaseModel):
    id: str
    label: str
    base: str
    available: bool = False
    detail: str | None = None


class CreatorLabWorkflow(BaseModel):
    id: str
    label: str
    kind: Literal["image", "video"] = "image"
    builtin: bool = True
    node_count: int = 0
    detail: str | None = None


class CreatorLabGpu(BaseModel):
    index: int
    name: str
    memory_total_mb: int | None = None
    memory_used_mb: int | None = None
    utilization: int | None = None
    temperature: int | None = None


class CreatorLabOverview(BaseModel):
    status: Literal["ready"] = "ready"
    root_path: str | None = None
    datasets: list[CreatorLabDataset] = Field(default_factory=list)
    lora_types: list[CreatorLabLoraType] = Field(default_factory=list)
    workflows: list[CreatorLabWorkflow] = Field(default_factory=list)
    gpus: list[CreatorLabGpu] = Field(default_factory=list)
    active_dataset_id: str | None = None
    active_lora_type: str | None = None
    active_workflow: str | None = None
    training_available: bool = False
    guardrails: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatorLabDatasetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    lora_type: str = "sdxl"
    trigger_token: str | None = Field(default=None, max_length=64)
    workflow: str | None = None
    notes: str | None = Field(default=None, max_length=600)


class CreatorLabSelectionRequest(BaseModel):
    active_dataset_id: str | None = None
    active_lora_type: str | None = None
    active_workflow: str | None = None


class CreatorWorkflowNode(BaseModel):
    id: str
    type: str
    title: str | None = None
    summary: str | None = None


class CreatorWorkflowGraph(BaseModel):
    id: str
    label: str
    nodes: list[CreatorWorkflowNode] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class CreatorVlmCritiqueRequest(BaseModel):
    prompt: str = Field(default="", max_length=4000)
    question: str | None = Field(default=None, max_length=1000)
    image_url: str | None = None
    dataset_id: str | None = None
    image_id: str | None = None


class CreatorVlmCritique(BaseModel):
    status: Literal["ok", "error", "unavailable"] = "ok"
    score: int | None = None
    matches: bool | None = None
    verdict: str | None = None
    notes: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    model_id: str | None = None


class CreatorTrainingConfig(BaseModel):
    dataset_id: str
    lora_name: str | None = Field(default=None, max_length=80)
    base_model: str | None = None
    steps: int = Field(default=1600, ge=100, le=20000)
    resolution: int = Field(default=1024, ge=512, le=1536)
    network_dim: int = Field(default=16, ge=4, le=128)
    learning_rate: float = Field(default=1e-4, gt=0, le=1e-2)
    gpu_ids: list[int] = Field(default_factory=list)


class CreatorTrainingJob(BaseModel):
    id: str
    dataset_id: str
    status: Literal["queued", "preparing", "running", "completed", "failed", "cancelled"] = "queued"
    progress: float = 0.0
    current_step: int = 0
    total_steps: int = 0
    gpu_ids: list[int] = Field(default_factory=list)
    lora_name: str | None = None
    output_path: str | None = None
    log_tail: list[str] = Field(default_factory=list)
    detail: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class MediaSystemStatus(BaseModel):
    service: str = "media"
    comfyui: ComfyUIStatus
    invokeai: MediaBackendStatus
    wan22: MediaBackendStatus
    modly: MediaBackendStatus
    creator_studio: CreatorStudioStatus
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


class WorkspaceInstallRequest(BaseModel):
    root_id: str = "app"
    package: str | None = Field(default=None, max_length=200)
    cwd: str = "."


class WorkspaceInstallResult(BaseModel):
    manager: str
    command: str
    cwd: str = "."
    status: Literal["complete", "error", "timeout"]
    exit_code: int | None = None
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    output_truncated: bool = False


class ScheduledTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=4000)
    schedule_kind: Literal["daily", "interval"] = "daily"
    time_of_day: str = "08:00"
    interval_minutes: int = Field(default=60, ge=5, le=10080)
    enabled: bool = True
    include_briefing: bool = False


class ScheduledTaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    prompt: str | None = Field(default=None, max_length=4000)
    schedule_kind: Literal["daily", "interval"] | None = None
    time_of_day: str | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    enabled: bool | None = None
    include_briefing: bool | None = None


class ScheduledTaskRecord(BaseModel):
    id: str
    title: str
    prompt: str
    schedule_kind: Literal["daily", "interval"] = "daily"
    time_of_day: str = "08:00"
    interval_minutes: int = 60
    enabled: bool = True
    include_briefing: bool = False
    last_run_at: str | None = None
    last_status: str | None = None
    last_result: str | None = None
    next_run_at: str | None = None
    created_at: str


class ScheduledTasksStatus(BaseModel):
    server_time: str
    tasks: list[ScheduledTaskRecord] = Field(default_factory=list)


class VoiceCommandRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=2000)
    source: str = "brio"


class VoiceEvent(BaseModel):
    id: int
    source: str = "brio"
    transcript: str
    reply: str
    conversation_id: str | None = None
    created_at: str


class VoiceStatus(BaseModel):
    listening: bool = False
    last_heard_at: str | None = None
    last_transcript: str | None = None
    event_count: int = 0
    events: list[VoiceEvent] = Field(default_factory=list)


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


class WorkspaceCopilotTaskRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=8000)
    target_paths: list[str] = Field(default_factory=list, max_length=12)
    preferred_model: str | None = "qwen3.6-35b-a3b-hauhaucs-coding"
    auto_apply: bool = True
    run_commands: bool = False
    max_context_files: int = Field(default=8, ge=1, le=20)


class WorkspaceCopilotChange(BaseModel):
    path: str
    summary: str = ""
    applied: bool = False
    preview: WorkspacePatchPreview | None = None
    file: WorkspaceFile | None = None
    error: str | None = None


class WorkspaceCopilotTaskResult(BaseModel):
    job: JobRecord
    status: Literal["complete", "setup_required", "error"]
    instruction: str
    model_id: str | None = None
    summary: str
    changes: list[WorkspaceCopilotChange] = Field(default_factory=list)
    commands: list[WorkspaceCommandRunResult] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    raw_response: str | None = None


class KnowledgeSourceRecord(BaseModel):
    id: str
    kind: Literal["text", "url", "wikipedia", "local_file", "preset", "chat_export", "conversation"]
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


class KnowledgeChatImportResult(BaseModel):
    detected_source: Literal["chatgpt", "claude", "mixed", "unknown"] = "unknown"
    conversation_count: int = 0
    imported_count: int = 0
    skipped_count: int = 0
    sources: list[KnowledgeSourceRecord] = Field(default_factory=list)


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
        "business-product-ops",
        "coding-reference",
    ]


class KnowledgeWebSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    max_results: int = Field(default=4, ge=1, le=8)


class KnowledgeConversationIngestRequest(BaseModel):
    conversation_id: str = Field(min_length=1)


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
    group: Literal["core", "minecraft", "creator", "commerce", "social"]
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
    kind: Literal["bambu", "creality", "moonraker", "octoprint", "orca", "cura", "dymo", "generic"]
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
    dashboard: dict[str, Any] = Field(default_factory=dict)
    detail: str


class ToyBoxPrinterProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: Literal["bambu", "creality", "moonraker", "octoprint", "orca", "cura", "dymo", "generic"] = "generic"
    role: Literal["printer", "slicer", "label_printer", "camera", "desktop_bridge"] = "printer"
    bridge_tool_id: str | None = None
    slicer_profile: str | None = None
    camera_url: str | None = None
    status: Literal["ready", "staged", "missing", "disabled"] = "staged"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToyBoxPrinterProfileRecord(ToyBoxPrinterProfileCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class ToyBoxDiscoveredPrinter(BaseModel):
    ip: str
    kind: str = "unknown"  # bambu / moonraker / octoprint / unknown
    label: str = ""
    ports: list[int] = Field(default_factory=list)
    already_added: bool = False
    serial: str = ""
    model: str = ""


class ToyBoxFileRecord(BaseModel):
    id: str
    printer_id: str
    name: str
    filename: str
    kind: str = "gcode"  # gcode / 3mf
    size: int = 0
    created_at: datetime


class ToyBoxFilament(BaseModel):
    index: int
    color_hex: str | None = None
    type: str = ""
    used_g: str = ""


class ToyBoxPrintRequest(BaseModel):
    # ams_mapping[i] = AMS slot id to use for the model's i-th filament (-1 = leave as sliced)
    ams_mapping: list[int] | None = None
    plate: int = Field(default=1, ge=1, le=64)
    use_ams: bool = True


class ToyBoxPrintResult(BaseModel):
    ok: bool
    printer_id: str
    file_id: str | None = None
    detail: str = ""
    queue_item_id: str | None = None


class ToyBoxControlRequest(BaseModel):
    action: Literal["pause", "resume", "stop", "light_on", "light_off", "home", "jog", "speed"]
    axis: str | None = None
    distance: float | None = None
    percent: int | None = None


class ToyBoxControlResult(BaseModel):
    ok: bool
    printer_id: str
    action: str
    detail: str = ""


class ToyBoxLabelRequest(BaseModel):
    title: str = ""
    lines: list[str] = Field(default_factory=list)
    copies: int = Field(default=1, ge=1, le=20)


class ToyBoxAmsSlot(BaseModel):
    id: int | None = None
    color_hex: str | None = None
    color: str | None = None
    material: str | None = None
    empty: bool = True


class ToyBoxPrinterLiveStatus(BaseModel):
    printer_id: str
    online: bool = False
    state: str | None = None
    progress: int | None = None
    nozzle_temp: float | None = None
    bed_temp: float | None = None
    remaining_min: int | None = None
    job_name: str | None = None
    loaded_color: str | None = None
    loaded_material: str | None = None
    sdcard: bool = False
    ams: list[ToyBoxAmsSlot] = Field(default_factory=list)
    light_on: bool | None = None
    detail: str | None = None


class ToyBoxRouteRequest(BaseModel):
    product: str = Field(min_length=1, max_length=240)
    color: str | None = None
    quantity: int = Field(default=1, ge=1, le=999)


class ToyBoxRouteCandidate(BaseModel):
    printer_id: str
    printer_name: str
    loaded_color: str | None = None
    loaded_material: str | None = None
    has_file: bool = False
    eligible: bool = False
    note: str = ""


class ToyBoxRouteResult(BaseModel):
    product: str
    color: str | None = None
    matched_printer_id: str | None = None
    matched_printer_name: str | None = None
    assigned_file: str | None = None
    reason: str
    candidates: list[ToyBoxRouteCandidate] = Field(default_factory=list)


class ToyBoxProductMappingCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    sku: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=180)
    model_path: str = ""
    slicer_profile: str = ""
    default_printer_id: str | None = None
    material: str = ""
    color: str = ""
    status: Literal["ready", "draft", "disabled"] = "draft"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToyBoxProductMappingRecord(ToyBoxProductMappingCreate):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    created_at: datetime
    updated_at: datetime


class ToyBoxOrderCreate(BaseModel):
    source: Literal["shopify", "manual", "test"] = "manual"
    external_order_id: str = Field(min_length=1, max_length=160)
    status: Literal["new", "mapped", "queued", "printing", "blocked", "done", "cancelled"] = "new"
    items: list[dict[str, Any]] = Field(default_factory=list)
    shipping: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToyBoxOrderRecord(ToyBoxOrderCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class ToyBoxQueueItemCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    order_id: str | None = None
    mapping_id: str | None = None
    printer_id: str | None = None
    title: str = Field(min_length=1, max_length=180)
    status: Literal["queued", "slicing", "ready_to_print", "printing", "paused", "blocked", "done", "cancelled"] = "queued"
    model_path: str = ""
    gcode_path: str = ""
    label_path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToyBoxQueueItemRecord(ToyBoxQueueItemCreate):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    created_at: datetime
    updated_at: datetime


class ToyBoxQueueStatusUpdate(BaseModel):
    status: Literal["queued", "slicing", "ready_to_print", "printing", "paused", "blocked", "done", "cancelled"]
    detail: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToyBoxSetupRequest(BaseModel):
    desktop_bridge_url: str = ""
    shopify_store_url: str = ""
    dymo_printer_name: str = "Mike's shipping label printer"
    default_slicer: str = "OrcaSlicer"
    notification_provider: str = "desktop"
    notification_target: str = "main-pc"
    seed_demo_mapping: bool = True


class ToyBoxSetupResult(BaseModel):
    service: str = "toybox3d-setup"
    runtime_settings: RuntimeSettingsRecord
    printers: list[ToyBoxPrinterProfileRecord]
    mappings: list[ToyBoxProductMappingRecord]
    bridge_status: dict[str, Any] = Field(default_factory=dict)
    detail: str


class ToyBoxShopifyWebhookResult(BaseModel):
    service: str = "toybox3d-shopify-webhook"
    accepted: bool
    duplicate: bool = False
    topic: str = ""
    webhook_id: str = ""
    order: ToyBoxOrderRecord | None = None
    queue: list[ToyBoxQueueItemRecord] = Field(default_factory=list)
    notification: dict[str, Any] | None = None
    detail: str


class ToyBoxNotificationSendRequest(BaseModel):
    title: str = Field(default="Edison ToyBox3D", max_length=160)
    message: str = Field(min_length=1, max_length=1000)
    severity: Literal["info", "warning", "error"] = "info"
    provider: str | None = None
    target: str | None = None
    force: bool = False


class ToyBoxNotificationResult(BaseModel):
    service: str = "toybox3d-notifications"
    ok: bool
    provider: str
    target: str = ""
    status: Literal["sent", "disabled", "setup_required", "error"]
    detail: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DesktopBridgeStatus(BaseModel):
    service: str = "desktop-bridge"
    configured_url: str = ""
    reachable: bool = False
    apps: list[dict[str, Any]] = Field(default_factory=list)
    printers: list[dict[str, Any]] = Field(default_factory=list)
    three_d_printers: list[dict[str, Any]] = Field(default_factory=list)
    allowed_roots: list[str] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    detail: str
    checked_at: datetime = Field(default_factory=utc_now)


class DesktopBridgeActionRequest(BaseModel):
    tool_id: str = Field(min_length=1, max_length=120)
    args: dict[str, Any] = Field(default_factory=dict)


class DesktopBridgeActionResult(BaseModel):
    ok: bool
    action: str
    detail: str
    result: dict[str, Any] = Field(default_factory=dict)


class RuntimeSettingsRecord(BaseModel):
    service: str = "runtime-settings"
    updated_at: datetime = Field(default_factory=utc_now)
    media: dict[str, Any] = Field(default_factory=dict)
    integrations: dict[str, Any] = Field(default_factory=dict)
    toybox: dict[str, Any] = Field(default_factory=dict)
    notifications: dict[str, Any] = Field(default_factory=dict)
    gallery: dict[str, Any] = Field(default_factory=dict)
    hardware: dict[str, Any] = Field(default_factory=dict)
    detail: str = "Runtime settings are stored locally and are not committed to the repository."


class RuntimeSettingsUpdate(BaseModel):
    media: dict[str, Any] | None = None
    integrations: dict[str, Any] | None = None
    toybox: dict[str, Any] | None = None
    notifications: dict[str, Any] | None = None
    gallery: dict[str, Any] | None = None
    hardware: dict[str, Any] | None = None


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
