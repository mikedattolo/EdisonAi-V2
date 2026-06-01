export type ChatMode =
  | 'instant'
  | 'chat'
  | 'reasoning'
  | 'coding'
  | 'agent'
  | 'swarm'
  | 'creative'
  | 'media';

export type MessageRole = 'system' | 'user' | 'assistant' | 'tool';
export type JobType = 'image' | 'image_edit' | 'video' | 'mesh' | 'audio' | 'document' | 'code' | 'system';
export type JobStatus =
  | 'queued'
  | 'setup_required'
  | 'loading'
  | 'generating'
  | 'encoding'
  | 'complete'
  | 'error'
  | 'cancelled';

export interface ModelProfile {
  id: string;
  display_name: string;
  provider: string;
  status: 'ready' | 'not_configured' | 'offline' | 'degraded';
  capabilities: string[];
  context_window: number;
  max_output_tokens: number;
  endpoint_url?: string | null;
  preferred_gpu?: string | null;
  notes?: string | null;
}

export interface ModelSelection {
  mode: ChatMode;
  required_capabilities: string[];
  model: ModelProfile;
  reason: string;
}

export interface GPUDevice {
  index: number;
  name: string;
  vram_total_mb?: number | null;
  vram_used_mb?: number | null;
  temperature_c?: number | null;
  utilization_percent?: number | null;
  power_draw_watts?: number | null;
  fan_speed_percent?: number | null;
}

export type GPUFanMode = 'auto' | 'manual' | 'curve';

export interface GPUFanCurvePoint {
  temperature_c: number;
  speed_percent: number;
}

export interface GPUFanPolicy {
  mode: GPUFanMode;
  manual_speed_percent: number;
  curve: GPUFanCurvePoint[];
}

export interface GPUFanControlState {
  gpu: GPUDevice;
  policy: GPUFanPolicy;
  target_speed_percent?: number | null;
  hardware_control_enabled: boolean;
  backend: string;
  applied: boolean;
  detail: string;
}

export interface GPUFanControlSnapshot {
  service: string;
  hardware_control_enabled: boolean;
  backend: string;
  controllers: GPUFanControlState[];
}

export interface SystemStatus {
  status: 'ok';
  service: string;
  version: string;
  environment: string;
  database_path: string;
  model_count: number;
  configured_model_count: number;
  gpu_devices: GPUDevice[];
  storage_roots: Record<string, string>;
}

export interface ConversationRecord {
  id: string;
  title: string;
  mode: ChatMode;
  memory_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface MessageRecord {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  model?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ConversationWithMessages extends ConversationRecord {
  messages: MessageRecord[];
}

export interface ChatTurnResponse {
  conversation: ConversationWithMessages;
  user_message: MessageRecord;
  assistant_message: MessageRecord;
  inference: {
    model_id: string;
    content: string;
    finish_reason: 'stop' | 'length' | 'error' | 'not_configured';
    metadata: Record<string, unknown>;
  };
  model_selection: ModelSelection;
}

export interface SessionStateRecord {
  session_id: string;
  current_task?: string | null;
  current_project?: string | null;
  active_domain?: string | null;
  last_tool_used?: string | null;
  last_generated_artifact?: string | null;
  task_stage?: string | null;
  last_intent?: string | null;
  current_plan: string[];
  pending_approval?: Record<string, unknown> | null;
  selected_mode: ChatMode;
  selected_model?: string | null;
  updated_at: string;
}

export interface JobRecord {
  id: string;
  job_type: JobType;
  status: JobStatus;
  title: string;
  prompt?: string | null;
  backend: string;
  source_artifact_id?: string | null;
  result_artifact_id?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ArtifactRecord {
  id: string;
  kind: 'image' | 'video' | 'audio' | 'mesh' | 'document' | 'code' | 'data' | 'other';
  title: string;
  path: string;
  mime_type?: string | null;
  source_job_id?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ComfyUIStatus {
  status: 'ready' | 'offline' | 'setup_required';
  base_url?: string | null;
  reachable: boolean;
  queue_running: number;
  queue_pending: number;
  detail: string;
  checked_at: string;
  system: Record<string, unknown>;
}

export interface MediaBackendStatus {
  status: 'ready' | 'offline' | 'setup_required';
  base_url?: string | null;
  reachable: boolean;
  detail: string;
  checked_at: string;
  metadata: Record<string, unknown>;
}

export interface MediaSystemStatus {
  service: string;
  comfyui: ComfyUIStatus;
  invokeai: MediaBackendStatus;
  wan22: MediaBackendStatus;
  modly: MediaBackendStatus;
  job_counts: Record<string, number>;
}

export interface WorkspaceEntry {
  path: string;
  name: string;
  kind: 'file' | 'directory';
  size_bytes?: number | null;
  modified_at?: string | null;
  language?: string | null;
}

export interface WorkspaceFile {
  path: string;
  name: string;
  size_bytes: number;
  modified_at?: string | null;
  language?: string | null;
  content: string;
  truncated: boolean;
}

export interface WorkspaceSummary {
  service: string;
  root_name: string;
  root_path: string;
  file_count: number;
  directory_count: number;
  languages: Record<string, number>;
  package_managers: string[];
  key_files: string[];
}

export interface WorkspaceSearchMatch {
  path: string;
  name: string;
  kind: 'file' | 'content';
  line_number?: number | null;
  line_text?: string | null;
  language?: string | null;
}

export interface WorkspaceEntrypoint {
  path: string;
  kind: string;
  language?: string | null;
  description: string;
}

export interface WorkspaceCommand {
  name: string;
  command: string;
  cwd: string;
  category: 'install' | 'dev' | 'build' | 'test' | 'lint' | 'typecheck' | 'format' | 'run' | 'other';
  source: string;
}

export interface WorkspaceScan {
  service: string;
  root_name: string;
  root_path: string;
  stacks: string[];
  package_managers: string[];
  entrypoints: WorkspaceEntrypoint[];
  commands: WorkspaceCommand[];
  test_targets: string[];
  config_files: string[];
  next_steps: string[];
}

export interface WorkspaceInstructionFile {
  path: string;
  name: string;
  instruction_type: 'repository' | 'path' | 'agent' | 'prompt';
  apply_to?: string | null;
  size_bytes: number;
  modified_at?: string | null;
}

export interface WorkspaceInstructionContext {
  target_path: string;
  selected_files: WorkspaceInstructionFile[];
  combined_text: string;
  warnings: string[];
}

export interface WorkspaceIndexSearchMatch {
  path: string;
  language?: string | null;
  score: number;
  snippet: string;
  line_number?: number | null;
}

export interface WorkspacePatchPreview {
  path: string;
  exists: boolean;
  language?: string | null;
  current_sha256?: string | null;
  proposed_sha256: string;
  diff: string;
  additions: number;
  deletions: number;
  risk_flags: string[];
  requires_approval: boolean;
}

export interface WorkspacePatchApplyResult {
  path: string;
  applied: boolean;
  message: string;
  preview: WorkspacePatchPreview;
  file: WorkspaceFile;
}

export interface WorkspaceCommandRunResult {
  job: JobRecord;
  command: string;
  cwd: string;
  exit_code?: number | null;
  status: 'complete' | 'error' | 'timeout';
  duration_ms: number;
  stdout: string;
  stderr: string;
  output_truncated: boolean;
}

export interface KnowledgeSourceRecord {
  id: string;
  kind: 'text' | 'url' | 'wikipedia' | 'local_file';
  title: string;
  uri?: string | null;
  language?: string | null;
  license?: string | null;
  metadata: Record<string, unknown>;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeStatus {
  service: string;
  source_count: number;
  chunk_count: number;
  latest_ingest_at?: string | null;
}

export interface KnowledgeSearchMatch {
  source_id: string;
  source_title: string;
  source_kind: string;
  uri?: string | null;
  path?: string | null;
  score: number;
  snippet: string;
}

export type OrganizerKind = 'task' | 'note' | 'calendar';
export type OrganizerStatus = 'active' | 'done' | 'archived' | 'cancelled';

export interface OrganizerItemRecord {
  id: string;
  kind: OrganizerKind;
  title: string;
  body: string;
  status: OrganizerStatus;
  due_at?: string | null;
  tags: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export type DocumentFormat = 'markdown' | 'text';

export interface DocumentRecord {
  id: string;
  title: string;
  content: string;
  format: DocumentFormat;
  tags: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export type SearchProvider = 'knowledge' | 'workspace' | 'documents';

export interface SearchCompareResult {
  provider: SearchProvider;
  title: string;
  subtitle?: string | null;
  snippet: string;
  score: number;
  uri?: string | null;
  path?: string | null;
  metadata: Record<string, unknown>;
}

export interface SearchCompareResponse {
  query: string;
  results: Record<SearchProvider, SearchCompareResult[]>;
  provider_counts: Record<SearchProvider, number>;
  best_provider?: SearchProvider | null;
}
