export type ChatMode =
  | 'auto'
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
  target_fan_ids: number[];
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

export interface HardwareAcceleratorRecord {
  id: string;
  name: string;
  kind: 'hailo8' | 'gpu' | 'other';
  bus: 'pcie' | 'usb' | 'unknown';
  status: 'ready' | 'detected' | 'driver_missing' | 'runtime_missing' | 'not_detected' | 'error';
  detail: string;
  pci_address?: string | null;
  vendor_id?: string | null;
  product_id?: string | null;
  device_nodes: string[];
  driver_loaded: boolean;
  runtime_available: boolean;
  runtime_version?: string | null;
  metadata: Record<string, unknown>;
}

export interface CameraDeviceRecord {
  id: string;
  name: string;
  status: 'ready' | 'detected' | 'permission_required' | 'offline' | 'error';
  detail: string;
  vendor_id?: string | null;
  product_id?: string | null;
  device_paths: string[];
  media_paths: string[];
  capture_path?: string | null;
  formats: string[];
  metadata: Record<string, unknown>;
}

export interface HardwareStatus {
  service: string;
  accelerators: HardwareAcceleratorRecord[];
  cameras: CameraDeviceRecord[];
  checked_at: string;
}

export interface HardwareControlAction {
  id: string;
  title: string;
  detail: string;
  severity: 'info' | 'warning' | 'critical';
  action_label?: string | null;
  metadata: Record<string, unknown>;
}

export interface HardwareControlCenter {
  service: string;
  overall_status: 'ready' | 'attention' | 'setup_required' | 'offline';
  gpu_count: number;
  fan_controller_count: number;
  writable_fan_target_count: number;
  fan_backend: string;
  fan_writes_enabled: boolean;
  hailo_status: string;
  camera_status: string;
  storage_roots: Record<string, string>;
  actions: HardwareControlAction[];
  checked_at: string;
  metadata: Record<string, unknown>;
}

export interface CameraSnapshotResponse {
  camera: CameraDeviceRecord;
  artifact: ArtifactRecord;
  detail: string;
}

export interface CameraVisionStatus {
  service: string;
  status: 'ready' | 'setup_required' | 'offline' | 'error';
  camera?: CameraDeviceRecord | null;
  backend?: string | null;
  feed_url?: string | null;
  detail: string;
  labels: string[];
  metadata: Record<string, unknown>;
}

export interface CameraFrameAnalysisResponse {
  service: string;
  status: 'complete' | 'setup_required' | 'error';
  camera: CameraDeviceRecord;
  artifact: ArtifactRecord;
  summary: string;
  model_id?: string | null;
  backend?: string | null;
  detections: string[];
  detail: string;
  metadata: Record<string, unknown>;
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

export type AgentRunStatus =
  | 'queued'
  | 'planning'
  | 'running'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type MediaGenerationMode =
  | 'image'
  | 'minecraft_texture'
  | 'minecraft_model'
  | 'minecraft_world'
  | 'minecraft_structure'
  | 'minecraft_texture_pack'
  | 'creator_photo'
  | 'creator_video'
  | 'creator_dataset'
  | 'product_render'
  | 'social_media_content';

export interface MediaGenerationModeRecord {
  id: MediaGenerationMode;
  label: string;
  group: 'core' | 'minecraft' | 'creator' | 'commerce' | 'social';
  job_type: JobType;
  backend: string;
  description: string;
  reference_supported: boolean;
  output_hint: string;
  prompt_hint: string;
  metadata: Record<string, unknown>;
}

export interface CreatorStudioDatasetRecord {
  id: string;
  name: string;
  root_path: string;
  kind: 'image' | 'video' | 'mixed' | 'unknown';
  status: 'ready' | 'detected' | 'empty';
  item_count: number;
  trigger_token?: string | null;
  metadata: Record<string, unknown>;
}

export interface CreatorStudioAssetRecord {
  id: string;
  name: string;
  kind: 'workflow' | 'model' | 'script' | 'config' | 'document' | 'other';
  status: 'available' | 'candidate' | 'cataloged';
  source_path?: string | null;
  copied_path?: string | null;
  size_bytes?: number | null;
  tags: string[];
  metadata: Record<string, unknown>;
}

export interface CreatorStudioStatus {
  service: string;
  status: 'ready' | 'setup_required' | 'offline' | 'error';
  source_path?: string | null;
  normalized_root?: string | null;
  detail: string;
  datasets: CreatorStudioDatasetRecord[];
  workflow_templates: string[];
  restricted_assets: CreatorStudioAssetRecord[];
  guardrails: string[];
  metadata: Record<string, unknown>;
}

export type AgentRunEventKind =
  | 'status'
  | 'plan'
  | 'thought'
  | 'tool_call'
  | 'tool_result'
  | 'approval'
  | 'artifact'
  | 'error';

export interface AgentRunRecord {
  id: string;
  title: string;
  prompt: string;
  mode: ChatMode;
  status: AgentRunStatus;
  progress_percent: number;
  current_step?: string | null;
  conversation_id?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AgentRunEventRecord {
  id: string;
  run_id: string;
  kind: AgentRunEventKind;
  title: string;
  body: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AgentRunWithEvents extends AgentRunRecord {
  events: AgentRunEventRecord[];
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
  creator_studio: CreatorStudioStatus;
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

export type KnowledgePreset =
  | 'coding-core'
  | 'ai-foundations'
  | 'edison-ops'
  | 'odysseus-features'
  | 'mcp-agents'
  | 'local-ai-hardware'
  | 'business-product-ops'
  | 'coding-reference';

export interface MCPServerRecord {
  id: string;
  name: string;
  status: 'ready' | 'staged' | 'missing' | 'disabled';
  transport: 'stdio' | 'http' | 'sse';
  description: string;
  tools: string[];
  command?: string | null;
  source?: string | null;
  enabled: boolean;
  detail: string;
  metadata: Record<string, unknown>;
}

export interface PluginIntegrationRecord {
  id: string;
  name: string;
  status: 'ready' | 'staged' | 'missing' | 'disabled';
  target: 'codex' | 'claude-code' | 'generic';
  description: string;
  setup_commands: string[];
  scopes: string[];
  detail: string;
  metadata: Record<string, unknown>;
}

export interface LocalIntegrationRecord {
  id: string;
  name: string;
  category:
    | 'mcp'
    | 'local-ai'
    | 'media'
    | 'minecraft'
    | '3d-printing'
    | 'cad'
    | 'commerce'
    | 'developer'
    | 'automation'
    | 'hardware'
    | 'api'
    | 'notifications';
  status: 'ready' | 'staged' | 'missing' | 'disabled';
  host: string;
  description: string;
  detected_tools: string[];
  paths: string[];
  detail: string;
  next_steps: string[];
  metadata: Record<string, unknown>;
}

export interface IntegrationRecommendation {
  id: string;
  title: string;
  priority: 'high' | 'medium' | 'low';
  detail: string;
  action: string;
  metadata: Record<string, unknown>;
}

export interface IntegrationScanReport {
  service: string;
  checked_at: string;
  integrations: LocalIntegrationRecord[];
  recommendations: IntegrationRecommendation[];
  detail: string;
}

export interface ToyBoxProductionLane {
  id: string;
  title: string;
  status: 'ready' | 'staged' | 'missing';
  description: string;
  connected_integrations: string[];
  next_steps: string[];
}

export interface ToyBoxPrinterRecord {
  id: string;
  name: string;
  kind: 'bambu' | 'orca' | 'cura' | 'dymo' | 'generic';
  status: 'ready' | 'staged' | 'missing';
  role: 'printer' | 'slicer' | 'label_printer' | 'camera' | 'desktop_bridge';
  detail: string;
  paths: string[];
  metadata: Record<string, unknown>;
}

export interface ToyBoxNotificationChannel {
  id: string;
  name: string;
  status: 'ready' | 'staged' | 'missing';
  target: 'sms' | 'push' | 'email' | 'desktop';
  detail: string;
  setup_hint: string;
  metadata: Record<string, unknown>;
}

export interface ToyBoxManagerStatus {
  service: string;
  checked_at: string;
  lanes: ToyBoxProductionLane[];
  printers: ToyBoxPrinterRecord[];
  notification_channels: ToyBoxNotificationChannel[];
  recommendations: IntegrationRecommendation[];
  dashboard: Record<string, unknown>;
  detail: string;
}

export interface ToyBoxPrinterProfileRecord {
  id: string;
  name: string;
  kind: 'bambu' | 'creality' | 'moonraker' | 'octoprint' | 'orca' | 'cura' | 'dymo' | 'generic';
  role: 'printer' | 'slicer' | 'label_printer' | 'camera' | 'desktop_bridge';
  bridge_tool_id?: string | null;
  slicer_profile?: string | null;
  camera_url?: string | null;
  status: 'ready' | 'staged' | 'missing' | 'disabled';
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ToyBoxDiscoveredPrinter {
  ip: string;
  kind: string;
  label: string;
  ports: number[];
  already_added: boolean;
  serial?: string;
  model?: string;
}

export interface ToyBoxFileRecord {
  id: string;
  printer_id: string;
  name: string;
  filename: string;
  kind: string;
  size: number;
  created_at: string;
}

export interface ToyBoxPrintResult {
  ok: boolean;
  printer_id: string;
  file_id?: string | null;
  detail: string;
  queue_item_id?: string | null;
}

export interface ToyBoxFulfillStep {
  title: string;
  quantity: number;
  color?: string | null;
  printer_id?: string | null;
  printer_name?: string | null;
  eligible: boolean;
  file?: string | null;
  action: string;
  detail: string;
}

export interface ToyBoxFulfillResult {
  order_name: string;
  dry_run: boolean;
  shipping_label: Record<string, unknown>;
  items: ToyBoxFulfillStep[];
  summary: string;
}

export interface ShopifyConfig {
  store_domain: string;
  has_token: boolean;
  mode: 'off' | 'notify' | 'auto';
  interval_seconds: number;
  last_poll: string;
  last_result: string;
  processed_count: number;
}

export interface ShopifyPollItem {
  order: string;
  dry_run: boolean;
  summary: string;
}

export interface ShopifyPollResult {
  checked: number;
  new_orders: number;
  mode: string;
  detail: string;
  results: ShopifyPollItem[];
}

export interface ToyBoxControlResult {
  ok: boolean;
  printer_id: string;
  action: string;
  detail: string;
}

export interface ToyBoxAmsSlot {
  id: number | null;
  color_hex?: string | null;
  color?: string | null;
  material?: string | null;
  empty: boolean;
}

export interface ToyBoxFilament {
  index: number;
  color_hex?: string | null;
  type: string;
  used_g: string;
}

export interface ToyBoxPrinterLiveStatus {
  printer_id: string;
  online: boolean;
  state?: string | null;
  progress?: number | null;
  nozzle_temp?: number | null;
  bed_temp?: number | null;
  remaining_min?: number | null;
  job_name?: string | null;
  loaded_color?: string | null;
  loaded_material?: string | null;
  sdcard?: boolean;
  ams?: ToyBoxAmsSlot[];
  light_on?: boolean | null;
  detail?: string | null;
}

export interface ToyBoxRouteCandidate {
  printer_id: string;
  printer_name: string;
  loaded_color?: string | null;
  loaded_material?: string | null;
  has_file: boolean;
  eligible: boolean;
  note: string;
}

export interface ToyBoxRouteResult {
  product: string;
  color?: string | null;
  matched_printer_id?: string | null;
  matched_printer_name?: string | null;
  assigned_file?: string | null;
  reason: string;
  candidates: ToyBoxRouteCandidate[];
}

export interface ToyBoxQueueItemRecord {
  id: string;
  order_id?: string | null;
  mapping_id?: string | null;
  printer_id?: string | null;
  title: string;
  status: 'queued' | 'slicing' | 'ready_to_print' | 'printing' | 'paused' | 'blocked' | 'done' | 'cancelled';
  model_path: string;
  gcode_path: string;
  label_path: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RuntimeSettingsRecord {
  service: string;
  updated_at: string;
  media: Record<string, unknown>;
  integrations: Record<string, unknown>;
  toybox: Record<string, unknown>;
  notifications: Record<string, unknown>;
  gallery: Record<string, unknown>;
  hardware: Record<string, unknown>;
  detail: string;
}

export interface CapabilityStatus {
  service: string;
  mcp_servers: MCPServerRecord[];
  plugins: PluginIntegrationRecord[];
  integrations: LocalIntegrationRecord[];
  recommendations: IntegrationRecommendation[];
  knowledge_presets: KnowledgePreset[];
  attribution: string[];
  detail: string;
}

export interface WorkspaceRootRecord {
  id: string;
  name: string;
  path: string;
  kind: 'app' | 'project';
  description?: string | null;
  created_at?: string | null;
}

export type WorkspaceProjectRecord = WorkspaceRootRecord & {
  kind: 'project';
};

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

export interface WorkspaceInstallResult {
  manager: string;
  command: string;
  cwd: string;
  status: 'complete' | 'error' | 'timeout';
  exit_code?: number | null;
  duration_ms: number;
  stdout: string;
  stderr: string;
  output_truncated: boolean;
}

export interface ScheduledTaskRecord {
  id: string;
  title: string;
  prompt: string;
  schedule_kind: 'daily' | 'interval';
  time_of_day: string;
  interval_minutes: number;
  enabled: boolean;
  include_briefing: boolean;
  last_run_at?: string | null;
  last_status?: string | null;
  last_result?: string | null;
  next_run_at?: string | null;
  created_at: string;
}

export interface ScheduledTasksStatus {
  server_time: string;
  tasks: ScheduledTaskRecord[];
}

export interface VoiceEvent {
  id: number;
  source: string;
  transcript: string;
  reply: string;
  conversation_id?: string | null;
  created_at: string;
}

export interface VoiceStatus {
  listening: boolean;
  last_heard_at?: string | null;
  last_transcript?: string | null;
  event_count: number;
  events: VoiceEvent[];
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

export interface WorkspaceCopilotTaskRequest {
  instruction: string;
  target_paths?: string[];
  preferred_model?: string | null;
  auto_apply?: boolean;
  run_commands?: boolean;
  max_context_files?: number;
}

export interface WorkspaceCopilotChange {
  path: string;
  summary: string;
  applied: boolean;
  preview?: WorkspacePatchPreview | null;
  file?: WorkspaceFile | null;
  error?: string | null;
}

export interface WorkspaceCopilotTaskResult {
  job: JobRecord;
  status: 'complete' | 'setup_required' | 'error';
  instruction: string;
  model_id?: string | null;
  summary: string;
  changes: WorkspaceCopilotChange[];
  commands: WorkspaceCommandRunResult[];
  followups: string[];
  raw_response?: string | null;
}

export interface KnowledgeSourceRecord {
  id: string;
  kind: 'text' | 'url' | 'wikipedia' | 'local_file' | 'preset' | 'chat_export' | 'conversation';
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

export interface UserProfileFact {
  id: string;
  content: string;
  updated_at: string;
}

export interface UserProfile {
  summary: string;
  summary_updated_at?: string | null;
  facts: UserProfileFact[];
}

export interface RealtimeContext {
  location: {
    city?: string | null;
    region?: string | null;
    country?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    timezone?: string | null;
    source?: string;
  };
  weather: {
    temperature_f?: number | null;
    feels_like_f?: number | null;
    humidity?: number | null;
    wind_mph?: number | null;
    is_day?: boolean;
    code?: number | null;
    description?: string | null;
    observed_at?: string | null;
  } | null;
  time: { iso: string; display: string; timezone?: string | null };
  summary: string;
}

export type ChatImportSource = 'auto' | 'chatgpt' | 'claude';

export interface KnowledgeChatImportResult {
  detected_source: 'chatgpt' | 'claude' | 'mixed' | 'unknown';
  conversation_count: number;
  imported_count: number;
  skipped_count: number;
  sources: KnowledgeSourceRecord[];
}

export interface CreatorStudioAssistAction {
  mode: 'creator_photo' | 'creator_video' | 'creator_dataset';
  title: string;
  prompt: string;
  rationale?: string | null;
  dataset_hint?: string | null;
}

export interface CreatorStudioAssistResponse {
  status: 'ok' | 'setup_required' | 'error';
  reply: string;
  actions: CreatorStudioAssistAction[];
  model_id?: string | null;
  guardrails: string[];
}

export interface CreatorLabImage {
  id: string;
  filename: string;
  url: string;
  size_bytes?: number | null;
  width?: number | null;
  height?: number | null;
  caption?: string | null;
}

export interface CreatorLabDataset {
  id: string;
  name: string;
  trigger_token: string;
  lora_type: string;
  base_model?: string | null;
  workflow?: string | null;
  notes?: string | null;
  status: 'empty' | 'ready';
  image_count: number;
  created_at?: string | null;
  images: CreatorLabImage[];
}

export interface CreatorLabLoraType {
  id: string;
  label: string;
  base: string;
  available: boolean;
  detail?: string | null;
}

export interface CreatorLabWorkflow {
  id: string;
  label: string;
  kind: 'image' | 'video';
  builtin: boolean;
  node_count: number;
  detail?: string | null;
}

export interface CreatorLabGpu {
  index: number;
  name: string;
  memory_total_mb?: number | null;
  memory_used_mb?: number | null;
  utilization?: number | null;
  temperature?: number | null;
}

export interface CreatorLabOverview {
  status: 'ready';
  root_path?: string | null;
  datasets: CreatorLabDataset[];
  lora_types: CreatorLabLoraType[];
  workflows: CreatorLabWorkflow[];
  gpus: CreatorLabGpu[];
  active_dataset_id?: string | null;
  active_lora_type?: string | null;
  active_workflow?: string | null;
  training_available: boolean;
  guardrails: string[];
  metadata: Record<string, unknown>;
}

export interface CreatorWorkflowNode {
  id: string;
  type: string;
  title?: string | null;
  summary?: string | null;
}

export interface CreatorWorkflowGraph {
  id: string;
  label: string;
  nodes: CreatorWorkflowNode[];
  raw: Record<string, unknown>;
}

export interface CreatorVlmCritique {
  status: 'ok' | 'error' | 'unavailable';
  score?: number | null;
  matches?: boolean | null;
  verdict?: string | null;
  notes?: string | null;
  suggestions: string[];
  model_id?: string | null;
}

export interface CreatorTrainingJob {
  id: string;
  dataset_id: string;
  status: 'queued' | 'preparing' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  current_step: number;
  total_steps: number;
  gpu_ids: number[];
  lora_name?: string | null;
  output_path?: string | null;
  log_tail: string[];
  detail?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface WorkspaceAgentStartPayload {
  task: string;
  root_id?: string;
  auto_run_commands?: boolean;
  max_steps?: number;
  preferred_model?: string | null;
  conversation_id?: string | null;
}

export interface WorkspaceAgentControlResult {
  accepted: boolean;
  run_id: string;
  action: string;
  detail: string;
}

export interface EdisonServiceRestartResult {
  scheduled: boolean;
  services: string[];
  web_build?: string;
  backend_ok?: boolean;
  detail: string;
}

export interface AgentChangedFile {
  path: string;
  additions: number;
  deletions: number;
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
