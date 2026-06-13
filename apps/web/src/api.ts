import type {
  AgentRunRecord,
  AgentRunWithEvents,
  ArtifactRecord,
  CapabilityStatus,
  ChatMode,
  ChatTurnResponse,
  ConversationRecord,
  ConversationWithMessages,
  DocumentFormat,
  DocumentRecord,
  CameraFrameAnalysisResponse,
  CameraSnapshotResponse,
  CameraVisionStatus,
  GPUFanControlSnapshot,
  GPUFanControlState,
  GPUFanMode,
  HardwareControlCenter,
  HardwareStatus,
  JobRecord,
  JobType,
  MediaGenerationMode,
  MediaGenerationModeRecord,
  MediaSystemStatus,
  MessageRecord,
  ModelProfile,
  ModelSelection,
  OrganizerItemRecord,
  OrganizerKind,
  OrganizerStatus,
  ChatImportSource,
  CreatorStudioAssistResponse,
  CreatorLabOverview,
  CreatorLabDataset,
  CreatorWorkflowGraph,
  CreatorVlmCritique,
  CreatorTrainingJob,
  EdisonServiceRestartResult,
  WorkspaceAgentControlResult,
  WorkspaceAgentStartPayload,
  KnowledgeChatImportResult,
  KnowledgePreset,
  KnowledgeSearchMatch,
  KnowledgeSourceRecord,
  KnowledgeStatus,
  UserProfile,
  RealtimeContext,
  SessionStateRecord,
  SearchCompareResponse,
  SearchProvider,
  SystemStatus,
  RuntimeSettingsRecord,
  ToyBoxManagerStatus,
  ToyBoxPrinterProfileRecord,
  ToyBoxDiscoveredPrinter,
  ToyBoxPrinterLiveStatus,
  ToyBoxRouteResult,
  ToyBoxQueueItemRecord,
  ToyBoxFileRecord,
  ToyBoxFilament,
  ToyBoxPrintResult,
  ToyBoxControlResult,
  WorkspaceCommandRunResult,
  WorkspaceInstallResult,
  ScheduledTaskRecord,
  ScheduledTasksStatus,
  VoiceEvent,
  VoiceStatus,
  WorkspaceCopilotTaskRequest,
  WorkspaceCopilotTaskResult,
  WorkspaceEntry,
  WorkspaceFile,
  WorkspaceIndexSearchMatch,
  WorkspaceInstructionContext,
  WorkspacePatchApplyResult,
  WorkspacePatchPreview,
  WorkspaceProjectRecord,
  WorkspaceRootRecord,
  WorkspaceScan,
  WorkspaceSearchMatch,
  WorkspaceSummary,
} from './types';

const configuredApiBase = import.meta.env.VITE_EDISON_API_URL?.trim();
const API_BASE = configuredApiBase ?? '';

export interface ChatTurnPayload {
  message: string;
  conversation_id?: string | null;
  mode: ChatMode;
  preferred_model?: string | null;
  agent_enabled?: boolean;
  memory_enabled?: boolean;
  workspace_path?: string;
  workspace_context_paths?: string[];
  include_workspace_context?: boolean;
  max_workspace_context_matches?: number;
  include_knowledge_context?: boolean;
  knowledge_query?: string;
  max_knowledge_context_matches?: number;
  include_personal_context?: boolean;
  max_personal_context_items?: number;
}

interface ChatStreamHandlers {
  onStart?: (event: {
    conversation_id: string;
    user_message: MessageRecord;
    model_selection: ModelSelection;
    agent_run?: AgentRunWithEvents | null;
  }) => void;
  onToken?: (delta: string) => void;
  onDone?: (response: ChatTurnResponse) => void;
  onError?: (detail: string) => void;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

function withQuery(path: string, params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      search.set(key, String(value));
    }
  });
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export const edisonApi = {
  apiBase: API_BASE,
  getStatus: () => request<SystemStatus>('/api/v1/status'),
  getCapabilities: () => request<CapabilityStatus>('/api/v1/capabilities'),
  getHardwareStatus: () => request<HardwareStatus>('/api/v1/hardware/status'),
  getHardwareControlCenter: () => request<HardwareControlCenter>('/api/v1/hardware/control-center'),
  getCameraVisionStatus: (devicePath?: string | null) =>
    request<CameraVisionStatus>(withQuery('/api/v1/hardware/cameras/vision', { device_path: devicePath ?? undefined })),
  cameraFeedUrl: (params: { device_path?: string | null; width?: number; height?: number; input_format?: 'mjpeg' | 'yuyv422' } = {}) =>
    `${API_BASE}${withQuery('/api/v1/hardware/cameras/feed', {
      device_path: params.device_path ?? undefined,
      width: params.width ?? 1280,
      height: params.height ?? 720,
      input_format: params.input_format ?? 'mjpeg',
    })}`,
  captureCameraSnapshot: (payload: { device_path?: string | null; width?: number; height?: number; input_format?: 'mjpeg' | 'yuyv422'; title?: string }) =>
    request<CameraSnapshotResponse>('/api/v1/hardware/cameras/snapshot', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  analyzeCameraFrame: (payload: {
    device_path?: string | null;
    width?: number;
    height?: number;
    input_format?: 'mjpeg' | 'yuyv422';
    title?: string;
    prompt?: string;
  }) =>
    request<CameraFrameAnalysisResponse>('/api/v1/hardware/cameras/analyze', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getFanControls: () => request<GPUFanControlSnapshot>('/api/v1/system/fans'),
  updateFanControl: (gpuIndex: number, payload: { mode: GPUFanMode; manual_speed_percent: number; curve?: Array<{ temperature_c: number; speed_percent: number }> }) =>
    request<GPUFanControlState>(`/api/v1/system/fans/${gpuIndex}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  listModels: () => request<ModelProfile[]>('/api/v1/models'),
  selectModel: (mode: ChatMode) => request<ModelSelection>(`/api/v1/models/select?mode=${mode}`),
  listConversations: () => request<ConversationRecord[]>('/api/v1/conversations'),
  listAgentRuns: (limit = 24) => request<AgentRunRecord[]>(withQuery('/api/v1/agents/runs', { limit })),
  getAgentRun: (runId: string) => request<AgentRunWithEvents>(`/api/v1/agents/runs/${runId}`),
  createConversation: (payload: { title: string; mode: ChatMode; memory_enabled: boolean }) =>
    request<ConversationRecord>('/api/v1/conversations', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getConversation: (conversationId: string) =>
    request<ConversationWithMessages>(`/api/v1/conversations/${conversationId}`),
  deleteConversation: async (conversationId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/conversations/${conversationId}`, { method: 'DELETE' });
    if (!response.ok) {
      throw new Error(`Delete failed with ${response.status}`);
    }
  },
  addMessage: (
    conversationId: string,
    payload: {
      role: 'user' | 'assistant' | 'system' | 'tool';
      content: string;
      model?: string | null;
      metadata?: Record<string, unknown>;
    },
  ) =>
    request<MessageRecord>(`/api/v1/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  sendChatTurn: (payload: ChatTurnPayload) =>
    request<ChatTurnResponse>('/api/v1/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  streamChatTurn: async (payload: ChatTurnPayload, handlers: ChatStreamHandlers = {}): Promise<ChatTurnResponse> => {
    const response = await fetch(`${API_BASE}/api/v1/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok || !response.body) {
      const detail = await response.text();
      throw new Error(detail || `Stream failed with ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const finalResponse: { current?: ChatTurnResponse } = {};

    const consumeBlock = (block: string) => {
      const lines = block.split(/\r?\n/);
      const eventName = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() || 'message';
      const dataLines = lines
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim());
      if (dataLines.length === 0) {
        return;
      }
      const raw = dataLines.join('\n');
      const data = JSON.parse(raw);
      if (eventName === 'start') {
        handlers.onStart?.(data);
      } else if (eventName === 'token') {
        handlers.onToken?.(String(data.delta ?? ''));
      } else if (eventName === 'done') {
        finalResponse.current = data as ChatTurnResponse;
        handlers.onDone?.(finalResponse.current);
      } else if (eventName === 'error') {
        handlers.onError?.(String(data.detail ?? 'Chat stream failed'));
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\n\n/);
      buffer = blocks.pop() ?? '';
      blocks.forEach((block) => {
        if (block.trim()) {
          consumeBlock(block);
        }
      });
    }
    if (buffer.trim()) {
      consumeBlock(buffer);
    }
    if (!finalResponse.current) {
      throw new Error('Chat stream ended before Edison sent a final response.');
    }
    return finalResponse.current;
  },
  getSession: (sessionId: string) => request<SessionStateRecord>(`/api/v1/sessions/${sessionId}`),
  updateSession: (sessionId: string, payload: Partial<SessionStateRecord>) =>
    request<SessionStateRecord>(`/api/v1/sessions/${sessionId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  getMediaStatus: () => request<MediaSystemStatus>('/api/v1/media/status'),
  creatorStudioAssist: (payload: {
    message: string;
    history?: Array<{ role: 'user' | 'assistant'; content: string }>;
    preferred_model?: string | null;
  }) =>
    request<CreatorStudioAssistResponse>('/api/v1/media/creator-studio/assist', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getCreatorLabOverview: () => request<CreatorLabOverview>('/api/v1/creator-lab/overview'),
  getCreatorDataset: (datasetId: string) => request<CreatorLabDataset>(`/api/v1/creator-lab/datasets/${datasetId}`),
  createCreatorDataset: (payload: {
    name: string;
    lora_type?: string;
    trigger_token?: string | null;
    workflow?: string | null;
    notes?: string | null;
  }) =>
    request<CreatorLabDataset>('/api/v1/creator-lab/datasets', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteCreatorDataset: async (datasetId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/creator-lab/datasets/${datasetId}`, { method: 'DELETE' });
    if (!response.ok) {
      throw new Error(`Delete failed with ${response.status}`);
    }
    return response.json();
  },
  uploadCreatorImages: async (datasetId: string, files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append('files', file));
    const response = await fetch(`${API_BASE}/api/v1/creator-lab/datasets/${datasetId}/images`, {
      method: 'POST',
      body: form,
    });
    if (!response.ok) {
      throw new Error(`Upload failed with ${response.status}`);
    }
    return (await response.json()) as CreatorLabDataset;
  },
  deleteCreatorImage: async (datasetId: string, imageId: string) => {
    const response = await fetch(
      `${API_BASE}/api/v1/creator-lab/datasets/${datasetId}/images/${encodeURIComponent(imageId)}`,
      { method: 'DELETE' },
    );
    if (!response.ok) {
      throw new Error(`Delete failed with ${response.status}`);
    }
    return (await response.json()) as CreatorLabDataset;
  },
  creatorImageUrl: (datasetId: string, imageId: string) =>
    `${API_BASE}/api/v1/creator-lab/datasets/${datasetId}/images/${encodeURIComponent(imageId)}`,
  setCreatorSelection: (payload: {
    active_dataset_id?: string | null;
    active_lora_type?: string | null;
    active_workflow?: string | null;
  }) =>
    request<CreatorLabOverview>('/api/v1/creator-lab/selection', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getCreatorWorkflowGraph: (workflowId: string) =>
    request<CreatorWorkflowGraph>(`/api/v1/creator-lab/workflows/${workflowId}/graph`),
  creatorVlmCritique: (payload: {
    prompt?: string;
    question?: string | null;
    image_url?: string | null;
    dataset_id?: string | null;
    image_id?: string | null;
  }) =>
    request<CreatorVlmCritique>('/api/v1/creator-lab/vlm-critique', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  startCreatorTraining: (payload: {
    dataset_id: string;
    lora_name?: string | null;
    base_model?: string | null;
    steps?: number;
    resolution?: number;
    network_dim?: number;
    learning_rate?: number;
    gpu_ids?: number[];
  }) =>
    request<CreatorTrainingJob>('/api/v1/creator-lab/training/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listCreatorTrainingJobs: () => request<CreatorTrainingJob[]>('/api/v1/creator-lab/training/jobs'),
  getCreatorTrainingJob: (jobId: string) => request<CreatorTrainingJob>(`/api/v1/creator-lab/training/jobs/${jobId}`),
  cancelCreatorTraining: (jobId: string) =>
    request<CreatorTrainingJob>(`/api/v1/creator-lab/training/jobs/${jobId}/cancel`, { method: 'POST' }),
  listMediaModes: () => request<MediaGenerationModeRecord[]>('/api/v1/media/modes'),
  getToyBoxStatus: () => request<ToyBoxManagerStatus>('/api/v1/toybox/status'),
  listToyBoxPrinters: () => request<ToyBoxPrinterProfileRecord[]>('/api/v1/toybox/printers'),
  upsertToyBoxPrinter: (payload: {
    name: string;
    kind?: string;
    role?: string;
    camera_url?: string | null;
    status?: string;
    metadata?: Record<string, unknown>;
  }) => request<ToyBoxPrinterProfileRecord>('/api/v1/toybox/printers', { method: 'POST', body: JSON.stringify(payload) }),
  discoverToyBoxPrinters: () => request<ToyBoxDiscoveredPrinter[]>('/api/v1/toybox/discover'),
  deleteToyBoxPrinter: async (printerId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/toybox/printers/${printerId}`, { method: 'DELETE' });
    if (!response.ok) {
      throw new Error(`Delete failed with ${response.status}`);
    }
    return response.json();
  },
  getToyBoxPrinterLive: (printerId: string) =>
    request<ToyBoxPrinterLiveStatus>(`/api/v1/toybox/printers/${printerId}/live`),
  routeToyBoxOrder: (payload: { product: string; color?: string | null; quantity?: number }) =>
    request<ToyBoxRouteResult>('/api/v1/toybox/route', { method: 'POST', body: JSON.stringify(payload) }),
  listToyBoxQueue: () => request<ToyBoxQueueItemRecord[]>('/api/v1/toybox/queue'),
  createToyBoxQueueItem: (payload: { title: string; printer_id?: string | null; status?: string; model_path?: string; metadata?: Record<string, unknown> }) =>
    request<ToyBoxQueueItemRecord>('/api/v1/toybox/queue', { method: 'POST', body: JSON.stringify(payload) }),
  listToyBoxFiles: (printerId: string) =>
    request<ToyBoxFileRecord[]>(`/api/v1/toybox/printers/${printerId}/files`),
  uploadToyBoxFile: async (printerId: string, file: File, name: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('name', name);
    const response = await fetch(`${API_BASE}/api/v1/toybox/printers/${printerId}/files`, { method: 'POST', body: form });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail?.detail || `Upload failed with ${response.status}`);
    }
    return response.json() as Promise<ToyBoxFileRecord>;
  },
  deleteToyBoxFile: async (fileId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/toybox/files/${fileId}`, { method: 'DELETE' });
    if (!response.ok) {
      throw new Error(`Delete failed with ${response.status}`);
    }
    return response.json();
  },
  getToyBoxFileFilaments: (fileId: string) =>
    request<ToyBoxFilament[]>(`/api/v1/toybox/files/${fileId}/filaments`),
  printToyBoxFile: (fileId: string, body?: { ams_mapping?: number[]; plate?: number; use_ams?: boolean }) =>
    request<ToyBoxPrintResult>(`/api/v1/toybox/files/${fileId}/print`, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),
  controlToyBoxPrinter: (
    printerId: string,
    action: 'pause' | 'resume' | 'stop' | 'light_on' | 'light_off' | 'home' | 'jog' | 'speed',
    extra?: { axis?: string; distance?: number; percent?: number },
  ) =>
    request<ToyBoxControlResult>(`/api/v1/toybox/printers/${printerId}/control`, {
      method: 'POST',
      body: JSON.stringify({ action, ...(extra ?? {}) }),
    }),
  getDymoStatus: () => request<{ queue: string; available: boolean; detail: string }>('/api/v1/toybox/dymo/status'),
  printDymoTest: () => request<{ ok: boolean; detail: string }>('/api/v1/toybox/dymo/test', { method: 'POST' }),
  printDymoLabel: (payload: { title?: string; lines?: string[]; copies?: number }) =>
    request<{ ok: boolean; detail: string }>('/api/v1/toybox/dymo/print', { method: 'POST', body: JSON.stringify(payload) }),
  getRuntimeSettings: () => request<RuntimeSettingsRecord>('/api/v1/settings/runtime'),
  updateRuntimeSettings: (payload: Partial<Pick<RuntimeSettingsRecord, 'media' | 'integrations' | 'toybox' | 'notifications' | 'gallery' | 'hardware'>>) =>
    request<RuntimeSettingsRecord>('/api/v1/settings/runtime', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  listArtifacts: (limit = 24) => request<ArtifactRecord[]>(`/api/v1/artifacts?limit=${limit}`),
  deleteArtifact: async (artifactId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/artifacts/${artifactId}`, { method: 'DELETE' });
    if (!response.ok) {
      throw new Error(`Delete failed with ${response.status}`);
    }
  },
  uploadArtifact: async (file: File) => {
    const formData = new FormData();
    formData.set('file', file);
    const response = await fetch(`${API_BASE}/api/v1/artifacts/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `Upload failed with ${response.status}`);
    }
    return response.json() as Promise<ArtifactRecord>;
  },
  listJobs: (jobType?: JobType) =>
    request<JobRecord[]>(jobType ? `/api/v1/jobs?job_type=${jobType}` : '/api/v1/jobs'),
  deleteJob: async (jobId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`, { method: 'DELETE' });
    if (!response.ok) {
      throw new Error(`Delete failed with ${response.status}`);
    }
  },
  generateMedia: (payload: {
    mode: MediaGenerationMode;
    prompt: string;
    title?: string;
    reference_artifact_id?: string | null;
    metadata?: Record<string, unknown>;
  }) =>
    request<JobRecord>('/api/v1/media/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  createMediaJob: (payload: { job_type: JobType; title: string; prompt?: string; source_artifact_id?: string | null; metadata?: Record<string, unknown> }) =>
    request<JobRecord>('/api/v1/media/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  syncMediaJob: (jobId: string) =>
    request<JobRecord>(`/api/v1/media/jobs/${jobId}/sync`, {
      method: 'POST',
    }),
  deliverMediaJob: (jobId: string, conversationId?: string | null) =>
    request<MessageRecord>(`/api/v1/media/jobs/${jobId}/deliver`, {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId ?? null }),
    }),
  cancelMediaJob: (jobId: string) =>
    request<JobRecord>(`/api/v1/media/jobs/${jobId}/cancel`, {
      method: 'POST',
    }),
  artifactDownloadUrl: (artifactId: string) => `${API_BASE}/api/v1/artifacts/${artifactId}/download`,
  listWorkspaceRoots: () => request<WorkspaceRootRecord[]>('/api/v1/workspace/roots'),
  createWorkspaceProject: (payload: { name: string; prompt: string; initialize_git?: boolean }) =>
    request<WorkspaceProjectRecord>('/api/v1/workspace/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getWorkspaceSummary: (rootId = 'app') => request<WorkspaceSummary>(withQuery('/api/v1/workspace/summary', { root_id: rootId })),
  getWorkspaceScan: (rootId = 'app') => request<WorkspaceScan>(withQuery('/api/v1/workspace/scan', { root_id: rootId })),
  listWorkspaceFiles: (path = '', rootId = 'app') =>
    request<WorkspaceEntry[]>(withQuery('/api/v1/workspace/files', { path, root_id: rootId })),
  getWorkspaceFile: (path: string, rootId = 'app') =>
    request<WorkspaceFile>(withQuery('/api/v1/workspace/files/content', { path, root_id: rootId })),
  searchWorkspace: (payload: { query: string; max_results?: number; case_sensitive?: boolean; include_content?: boolean }, rootId = 'app') =>
    request<WorkspaceSearchMatch[]>(withQuery('/api/v1/workspace/search', { root_id: rootId }), {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  previewWorkspacePatch: (payload: {
    path: string;
    proposed_content: string;
    summary?: string;
    create_if_missing?: boolean;
    expected_sha256?: string | null;
  }, rootId = 'app') =>
    request<WorkspacePatchPreview>(withQuery('/api/v1/workspace/patches/preview', { root_id: rootId }), {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  applyWorkspacePatch: (payload: {
    path: string;
    proposed_content: string;
    summary?: string;
    create_if_missing?: boolean;
    expected_sha256?: string | null;
    approved: boolean;
  }, rootId = 'app') =>
    request<WorkspacePatchApplyResult>(withQuery('/api/v1/workspace/patches/apply', { root_id: rootId }), {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  runWorkspaceCommand: (payload: { command: string; cwd: string; timeout_seconds?: number; approved: boolean }, rootId = 'app') =>
    request<WorkspaceCommandRunResult>(withQuery('/api/v1/workspace/commands/run', { root_id: rootId }), {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  runWorkspaceCopilotTask: (payload: WorkspaceCopilotTaskRequest, rootId = 'app') =>
    request<WorkspaceCopilotTaskResult>(withQuery('/api/v1/workspace/copilot/tasks', { root_id: rootId }), {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getWorkspaceInstructionContext: (path: string, rootId = 'app') =>
    request<WorkspaceInstructionContext>(withQuery('/api/v1/workspace/instructions/context', { path, root_id: rootId })),
  searchWorkspaceIndex: (payload: { query: string; max_results?: number }, rootId = 'app') =>
    request<WorkspaceIndexSearchMatch[]>(withQuery('/api/v1/workspace/index/search', { root_id: rootId }), {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getKnowledgeStatus: () => request<KnowledgeStatus>('/api/v1/knowledge/status'),
  getEmbeddingStatus: () => request<{ total_chunks: number; embedded_chunks: number; pending: number; model: string; ready: boolean }>('/api/v1/knowledge/embeddings'),
  runEmbedding: (maxChunks = 4000) =>
    request<Record<string, unknown>>(withQuery('/api/v1/knowledge/embeddings/run', { max_chunks: maxChunks }), { method: 'POST' }),
  getUserProfile: () => request<UserProfile>('/api/v1/knowledge/profile'),
  setUserProfile: (text: string) =>
    request<UserProfile>('/api/v1/knowledge/profile', { method: 'PUT', body: JSON.stringify({ text }) }),
  addUserFact: (text: string) =>
    request<UserProfile>('/api/v1/knowledge/profile/facts', { method: 'POST', body: JSON.stringify({ text }) }),
  deleteUserFact: (factId: string) =>
    request<UserProfile>(`/api/v1/knowledge/profile/facts/${factId}`, { method: 'DELETE' }),
  rebuildUserProfile: () => request<UserProfile>('/api/v1/knowledge/profile/rebuild', { method: 'POST' }),
  listKnowledgeSources: (limit = 100) =>
    request<KnowledgeSourceRecord[]>(withQuery('/api/v1/knowledge/sources', { limit })),
  searchKnowledge: (payload: { query: string; max_results?: number }) =>
    request<KnowledgeSearchMatch[]>('/api/v1/knowledge/search', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  ingestKnowledgeText: (payload: {
    title: string;
    text: string;
    uri?: string;
    language?: string;
    license?: string;
    metadata?: Record<string, unknown>;
  }) =>
    request<KnowledgeSourceRecord>('/api/v1/knowledge/ingest/text', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  ingestKnowledgeWikipedia: (payload: { title: string; language?: string }) =>
    request<KnowledgeSourceRecord>('/api/v1/knowledge/ingest/wikipedia', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  ingestKnowledgeUrl: (payload: { url: string; title?: string; language?: string; license?: string }) =>
    request<KnowledgeSourceRecord>('/api/v1/knowledge/ingest/url', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  ingestKnowledgeLocal: (payload: { path: string; glob?: string; max_files?: number }) =>
    request<KnowledgeSourceRecord[]>('/api/v1/knowledge/ingest/local', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  ingestKnowledgePreset: (payload: { preset: KnowledgePreset }) =>
    request<KnowledgeSourceRecord[]>('/api/v1/knowledge/ingest/preset', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  ingestKnowledgeWebSearch: (payload: { query: string; max_results?: number }) =>
    request<KnowledgeSourceRecord[]>('/api/v1/knowledge/ingest/web-search', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  rememberConversation: (conversationId: string) =>
    request<KnowledgeSourceRecord>('/api/v1/knowledge/ingest/conversation', {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId }),
    }),
  downloadWorkspaceUrl: (rootId = 'app', path = '') =>
    `${API_BASE}${withQuery('/api/v1/workspace/download', { root_id: rootId, path })}`,
  installWorkspaceDeps: (payload: { root_id?: string; package?: string | null; cwd?: string }) =>
    request<WorkspaceInstallResult>('/api/v1/workspace/install', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listScheduledTasks: () => request<ScheduledTasksStatus>('/api/v1/scheduler/tasks'),
  createScheduledTask: (payload: {
    title: string;
    prompt: string;
    schedule_kind: 'daily' | 'interval';
    time_of_day?: string;
    interval_minutes?: number;
    enabled?: boolean;
    include_briefing?: boolean;
  }) => request<ScheduledTaskRecord>('/api/v1/scheduler/tasks', { method: 'POST', body: JSON.stringify(payload) }),
  updateScheduledTask: (taskId: string, payload: Partial<{ enabled: boolean; title: string; prompt: string; schedule_kind: 'daily' | 'interval'; time_of_day: string; interval_minutes: number; include_briefing: boolean }>) =>
    request<ScheduledTaskRecord>(`/api/v1/scheduler/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  runScheduledTask: (taskId: string) =>
    request<ScheduledTaskRecord>(`/api/v1/scheduler/tasks/${taskId}/run`, { method: 'POST' }),
  deleteScheduledTask: async (taskId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/scheduler/tasks/${taskId}`, { method: 'DELETE' });
    if (!response.ok) {
      throw new Error(`Delete failed with ${response.status}`);
    }
    return response.json();
  },
  getVoiceStatus: () => request<VoiceStatus>('/api/v1/voice/status'),
  getVoiceEvents: (after = 0) => request<VoiceEvent[]>(withQuery('/api/v1/voice/events', { after })),
  getRealtimeContext: (latitude?: number, longitude?: number) =>
    request<RealtimeContext>(withQuery('/api/v1/realtime/context', { latitude, longitude })),
  importKnowledgeChatExport: async (files: File[], source: ChatImportSource = 'auto') => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    formData.set('source', source);
    const response = await fetch(`${API_BASE}/api/v1/knowledge/ingest/chat-export`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `Chat import failed with ${response.status}`);
    }
    return response.json() as Promise<KnowledgeChatImportResult>;
  },
  listOrganizerItems: (params: { kind?: OrganizerKind; status?: OrganizerStatus; limit?: number } = {}) =>
    request<OrganizerItemRecord[]>(withQuery('/api/v1/organizer/items', params)),
  createOrganizerItem: (payload: {
    kind: OrganizerKind;
    title: string;
    body?: string;
    status?: OrganizerStatus;
    due_at?: string | null;
    tags?: string[];
    metadata?: Record<string, unknown>;
  }) =>
    request<OrganizerItemRecord>('/api/v1/organizer/items', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateOrganizerItem: (
    itemId: string,
    payload: Partial<{
      title: string;
      body: string;
      status: OrganizerStatus;
      due_at: string | null;
      tags: string[];
      metadata: Record<string, unknown>;
    }>,
  ) =>
    request<OrganizerItemRecord>(`/api/v1/organizer/items/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  deleteOrganizerItem: async (itemId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/organizer/items/${itemId}`, { method: 'DELETE' });
    if (!response.ok) {
      throw new Error(`Delete failed with ${response.status}`);
    }
  },
  listDocuments: (limit = 100) => request<DocumentRecord[]>(withQuery('/api/v1/documents', { limit })),
  createDocument: (payload: {
    title: string;
    content?: string;
    format?: DocumentFormat;
    tags?: string[];
    metadata?: Record<string, unknown>;
  }) =>
    request<DocumentRecord>('/api/v1/documents', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateDocument: (
    documentId: string,
    payload: Partial<{
      title: string;
      content: string;
      format: DocumentFormat;
      tags: string[];
      metadata: Record<string, unknown>;
    }>,
  ) =>
    request<DocumentRecord>(`/api/v1/documents/${documentId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  deleteDocument: async (documentId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/documents/${documentId}`, { method: 'DELETE' });
    if (!response.ok) {
      throw new Error(`Delete failed with ${response.status}`);
    }
  },
  ingestDocument: (documentId: string) =>
    request<KnowledgeSourceRecord>(`/api/v1/documents/${documentId}/ingest`, {
      method: 'POST',
    }),
  compareSearch: (payload: { query: string; providers: SearchProvider[]; max_results?: number }) =>
    request<SearchCompareResponse>('/api/v1/search/compare', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  controlWorkspaceAgent: (payload: { run_id: string; action: 'approve' | 'deny' | 'stop'; step_id?: string }) =>
    request<WorkspaceAgentControlResult>('/api/v1/workspace/agent/control', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  restartEdison: (services?: Array<'edison-api' | 'edison-web'>) =>
    request<EdisonServiceRestartResult>('/api/v1/workspace/agent/restart-edison', {
      method: 'POST',
      body: JSON.stringify(services ? { services } : {}),
    }),
  streamWorkspaceAgent: async (
    payload: WorkspaceAgentStartPayload,
    onEvent: (event: string, data: any) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    const response = await fetch(`${API_BASE}/api/v1/workspace/agent/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    });
    if (!response.ok || !response.body) {
      const detail = await response.text().catch(() => '');
      throw new Error(detail || `Agent stream failed with ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const consume = (block: string) => {
      const lines = block.split(/\r?\n/);
      const eventName = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() || 'message';
      const dataLines = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim());
      if (dataLines.length === 0) {
        return;
      }
      let data: unknown = {};
      try {
        data = JSON.parse(dataLines.join('\n'));
      } catch {
        data = {};
      }
      onEvent(eventName, data);
    };
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\n\n/);
      buffer = blocks.pop() ?? '';
      blocks.forEach((block) => {
        if (block.trim()) {
          consume(block);
        }
      });
    }
    if (buffer.trim()) {
      consume(buffer);
    }
  },
};
