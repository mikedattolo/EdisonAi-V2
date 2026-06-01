import type {
  ArtifactRecord,
  ChatMode,
  ChatTurnResponse,
  ConversationRecord,
  ConversationWithMessages,
  DocumentFormat,
  DocumentRecord,
  GPUFanControlSnapshot,
  GPUFanControlState,
  GPUFanMode,
  JobRecord,
  JobType,
  MediaSystemStatus,
  MessageRecord,
  ModelProfile,
  ModelSelection,
  OrganizerItemRecord,
  OrganizerKind,
  OrganizerStatus,
  KnowledgeSearchMatch,
  KnowledgeSourceRecord,
  KnowledgeStatus,
  SessionStateRecord,
  SearchCompareResponse,
  SearchProvider,
  SystemStatus,
  WorkspaceCommandRunResult,
  WorkspaceEntry,
  WorkspaceFile,
  WorkspaceIndexSearchMatch,
  WorkspaceInstructionContext,
  WorkspacePatchApplyResult,
  WorkspacePatchPreview,
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
  onStart?: (event: { conversation_id: string; user_message: MessageRecord; model_selection: ModelSelection }) => void;
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
  getFanControls: () => request<GPUFanControlSnapshot>('/api/v1/system/fans'),
  updateFanControl: (gpuIndex: number, payload: { mode: GPUFanMode; manual_speed_percent: number; curve?: Array<{ temperature_c: number; speed_percent: number }> }) =>
    request<GPUFanControlState>(`/api/v1/system/fans/${gpuIndex}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  listModels: () => request<ModelProfile[]>('/api/v1/models'),
  selectModel: (mode: ChatMode) => request<ModelSelection>(`/api/v1/models/select?mode=${mode}`),
  listConversations: () => request<ConversationRecord[]>('/api/v1/conversations'),
  createConversation: (payload: { title: string; mode: ChatMode; memory_enabled: boolean }) =>
    request<ConversationRecord>('/api/v1/conversations', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getConversation: (conversationId: string) =>
    request<ConversationWithMessages>(`/api/v1/conversations/${conversationId}`),
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
  listArtifacts: (limit = 24) => request<ArtifactRecord[]>(`/api/v1/artifacts?limit=${limit}`),
  listJobs: (jobType?: JobType) =>
    request<JobRecord[]>(jobType ? `/api/v1/jobs?job_type=${jobType}` : '/api/v1/jobs'),
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
  getWorkspaceSummary: () => request<WorkspaceSummary>('/api/v1/workspace/summary'),
  getWorkspaceScan: () => request<WorkspaceScan>('/api/v1/workspace/scan'),
  listWorkspaceFiles: (path = '') => request<WorkspaceEntry[]>(withQuery('/api/v1/workspace/files', { path })),
  getWorkspaceFile: (path: string) =>
    request<WorkspaceFile>(withQuery('/api/v1/workspace/files/content', { path })),
  searchWorkspace: (payload: { query: string; max_results?: number; case_sensitive?: boolean; include_content?: boolean }) =>
    request<WorkspaceSearchMatch[]>('/api/v1/workspace/search', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  previewWorkspacePatch: (payload: {
    path: string;
    proposed_content: string;
    summary?: string;
    create_if_missing?: boolean;
    expected_sha256?: string | null;
  }) =>
    request<WorkspacePatchPreview>('/api/v1/workspace/patches/preview', {
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
  }) =>
    request<WorkspacePatchApplyResult>('/api/v1/workspace/patches/apply', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  runWorkspaceCommand: (payload: { command: string; cwd: string; timeout_seconds?: number; approved: boolean }) =>
    request<WorkspaceCommandRunResult>('/api/v1/workspace/commands/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getWorkspaceInstructionContext: (path: string) =>
    request<WorkspaceInstructionContext>(withQuery('/api/v1/workspace/instructions/context', { path })),
  searchWorkspaceIndex: (payload: { query: string; max_results?: number }) =>
    request<WorkspaceIndexSearchMatch[]>('/api/v1/workspace/index/search', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getKnowledgeStatus: () => request<KnowledgeStatus>('/api/v1/knowledge/status'),
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
  ingestKnowledgePreset: (payload: { preset: 'coding-core' | 'ai-foundations' }) =>
    request<KnowledgeSourceRecord[]>('/api/v1/knowledge/ingest/preset', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
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
};
