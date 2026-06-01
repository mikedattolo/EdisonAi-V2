import {
  Activity,
  Bot,
  Box,
  Brain,
  BookOpen,
  ChevronUp,
  Code2,
  Cpu,
  Database,
  Fan,
  FileCode2,
  FileText,
  Folder,
  GalleryHorizontalEnd,
  Globe2,
  Image,
  Link2,
  MessageSquare,
  Network,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Search,
  Send,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Upload,
  Video,
  Waypoints,
  X,
} from 'lucide-react';
import { CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from 'react';

import { edisonApi } from './api';
import type {
  ArtifactRecord,
  ChatMode,
  ConversationRecord,
  ConversationWithMessages,
  GPUFanControlSnapshot,
  GPUFanMode,
  JobRecord,
  JobType,
  KnowledgeSearchMatch,
  KnowledgeSourceRecord,
  KnowledgeStatus,
  MediaSystemStatus,
  MessageRecord,
  ModelProfile,
  ModelSelection,
  SessionStateRecord,
  SystemStatus,
  WorkspaceCommand,
  WorkspaceCommandRunResult,
  WorkspaceEntry,
  WorkspaceFile,
  WorkspaceIndexSearchMatch,
  WorkspaceInstructionContext,
  WorkspacePatchPreview,
  WorkspaceScan,
  WorkspaceSearchMatch,
  WorkspaceSummary,
} from './types';

const SESSION_ID = 'local-workbench';

type ViewId = 'chat' | 'agent' | 'compare' | 'code' | 'media' | 'memory' | 'system' | 'settings';
type IconType = typeof MessageSquare;
type ContextFilter = 'all' | 'instructions' | 'index' | 'warnings';
type CompareStatus = 'idle' | 'streaming' | 'done' | 'error';

type CompareRun = {
  id: string;
  modelId: string;
  displayName: string;
  status: CompareStatus;
  content: string;
  conversationId?: string;
  error?: string;
  startedAt: number;
  finishedAt?: number;
};

const CONTEXT_VISIBILITY_STORAGE_KEY = 'edison-chat-context-visible';
const CONTEXT_FILTER_STORAGE_KEY = 'edison-chat-context-filter';
const CONTEXT_COLLAPSED_STORAGE_KEY_PREFIX = 'edison-chat-context-collapsed';
const CHAT_WORKSPACE_PATH_STORAGE_KEY = 'edison-chat-workspace-path';
const CHAT_CONTEXT_MATCHES_STORAGE_KEY = 'edison-chat-context-matches';
const CHAT_AUTO_PREVIEW_STORAGE_KEY = 'edison-chat-auto-preview';
const CHAT_CONTEXT_PATHS_STORAGE_KEY = 'edison-chat-context-paths';
const CHAT_KNOWLEDGE_ENABLED_STORAGE_KEY = 'edison-chat-knowledge-enabled';
const CHAT_KNOWLEDGE_MATCHES_STORAGE_KEY = 'edison-chat-knowledge-matches';

const modes: Array<{ value: ChatMode; label: string; description: string }> = [
  { value: 'instant', label: 'Quick', description: 'Fast replies' },
  { value: 'chat', label: 'Chat', description: 'Everyday help' },
  { value: 'reasoning', label: 'Think', description: 'Harder problems' },
  { value: 'coding', label: 'Code', description: 'Repo-aware edits' },
  { value: 'agent', label: 'Agent', description: 'Multi-step work' },
  { value: 'swarm', label: 'Swarm', description: 'Parallel lanes' },
  { value: 'creative', label: 'Create', description: 'Images and ideas' },
];

const navigation: Array<{ id: ViewId; label: string; icon: IconType }> = [
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'agent', label: 'Agent', icon: Waypoints },
  { id: 'compare', label: 'Compare', icon: Network },
  { id: 'code', label: 'Code Space', icon: Code2 },
  { id: 'media', label: 'Media', icon: GalleryHorizontalEnd },
  { id: 'memory', label: 'Memory', icon: Brain },
  { id: 'system', label: 'System', icon: Server },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const mediaPlan = [
  {
    title: 'Image Generation',
    jobType: 'image' as JobType,
    icon: Image,
    stack: 'ComfyUI with FLUX.1 and SDXL workflows',
    lane: 'RTX 3090 for quality, 16 GB cards for lighter batches',
  },
  {
    title: 'Image Editing',
    jobType: 'image_edit' as JobType,
    icon: SlidersHorizontal,
    stack: 'ComfyUI inpaint, ControlNet, IP-Adapter, SAM, background removal',
    lane: 'Shared media queue with artifact versioning',
  },
  {
    title: 'Video Generation',
    jobType: 'video' as JobType,
    icon: Video,
    stack: 'LTX, Wan, CogVideoX, SVD, and AnimateDiff through ComfyUI or diffusers',
    lane: 'Exclusive GPU render mode for heavy jobs',
  },
  {
    title: '3D Model Generation',
    jobType: 'mesh' as JobType,
    icon: Box,
    stack: 'TripoSR, Stable Fast 3D, InstantMesh, Blender automation hooks',
    lane: 'Artifact-first pipeline for GLB, OBJ, STL outputs',
  },
];

const modelPlan = [
  ['Primary LLM', 'Qwen2.5-Coder 32B Instruct as the first local workhorse for code, tools, and general chat.'],
  ['Fast LLM', 'Qwen2.5 7B/14B Instruct or a small Qwen3 profile for routing, summaries, and low-latency chat.'],
  ['Reasoning Lane', 'Qwen2.5 72B Instruct or another large reasoning profile when installed.'],
  ['Primary VLM', 'Qwen2.5-VL 7B Instruct first for screenshots, images, OCR-like work, and UI inspection.'],
  ['Media Stack', 'FLUX for image generation, LTX/Wan/CogVideoX/SVD for video, InstantMesh and Stable Fast 3D for mesh workflows.'],
];

const promptSuggestions: Array<{ title: string; subtitle: string; prompt: string; icon: IconType }> = [
  {
    title: 'Check GPUs and fans',
    subtitle: 'System status',
    prompt: 'Check the GPU, temperature, and fan status on this Edison AI PC and tell me what needs attention.',
    icon: Fan,
  },
  {
    title: 'Work on this repo',
    subtitle: 'Coding session',
    prompt: 'Look through the current repo and suggest the next highest-impact UI improvement, then help me implement it.',
    icon: Code2,
  },
  {
    title: 'Find a file or setting',
    subtitle: 'Workspace search',
    prompt: 'Help me find the file or setting that controls this behavior in the Edison repo.',
    icon: Search,
  },
  {
    title: 'Plan a media job',
    subtitle: 'Image/video workflow',
    prompt: 'Help me plan a local image or video generation workflow for this Edison machine.',
    icon: Image,
  },
];

export default function App() {
  const [activeView, setActiveView] = useState<ViewId>('chat');
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [modelSelection, setModelSelection] = useState<ModelSelection | null>(null);
  const [sessionState, setSessionState] = useState<SessionStateRecord | null>(null);
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [mediaStatus, setMediaStatus] = useState<MediaSystemStatus | null>(null);
  const [fanControls, setFanControls] = useState<GPUFanControlSnapshot | null>(null);
  const [mediaJobs, setMediaJobs] = useState<JobRecord[]>([]);
  const [mediaArtifacts, setMediaArtifacts] = useState<ArtifactRecord[]>([]);
  const [workspaceSummary, setWorkspaceSummary] = useState<WorkspaceSummary | null>(null);
  const [workspaceScan, setWorkspaceScan] = useState<WorkspaceScan | null>(null);
  const [workspaceEntries, setWorkspaceEntries] = useState<WorkspaceEntry[]>([]);
  const [workspacePath, setWorkspacePath] = useState('');
  const [workspaceFile, setWorkspaceFile] = useState<WorkspaceFile | null>(null);
  const [workspaceDraftContent, setWorkspaceDraftContent] = useState('');
  const [workspacePatchPreview, setWorkspacePatchPreview] = useState<WorkspacePatchPreview | null>(null);
  const [workspaceCommandResult, setWorkspaceCommandResult] = useState<WorkspaceCommandRunResult | null>(null);
  const [workspaceSearchQuery, setWorkspaceSearchQuery] = useState('');
  const [workspaceSearchResults, setWorkspaceSearchResults] = useState<WorkspaceSearchMatch[]>([]);
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatus | null>(null);
  const [knowledgeSources, setKnowledgeSources] = useState<KnowledgeSourceRecord[]>([]);
  const [knowledgeSearchQuery, setKnowledgeSearchQuery] = useState('');
  const [knowledgeSearchResults, setKnowledgeSearchResults] = useState<KnowledgeSearchMatch[]>([]);
  const [knowledgeNotice, setKnowledgeNotice] = useState<string | null>(null);
  const [activeConversation, setActiveConversation] = useState<ConversationWithMessages | null>(null);
  const [activeMode, setActiveMode] = useState<ChatMode>('chat');
  const [showWorkspaceContext, setShowWorkspaceContext] =
    useState<boolean>(() => readStoredBoolean(CONTEXT_VISIBILITY_STORAGE_KEY, true));
  const [workspaceContextFilter, setWorkspaceContextFilter] =
    useState<ContextFilter>(() => readStoredContextFilter(CONTEXT_FILTER_STORAGE_KEY, 'all'));
  const [collapsedContextMessageIds, setCollapsedContextMessageIds] = useState<Record<string, boolean>>({});
  const [chatWorkspacePath, setChatWorkspacePath] =
    useState<string>(() => readStoredString(CHAT_WORKSPACE_PATH_STORAGE_KEY, ''));
  const [chatContextPaths, setChatContextPaths] =
    useState<string[]>(() => readStoredStringArray(CHAT_CONTEXT_PATHS_STORAGE_KEY, []));
  const [chatContextMatches, setChatContextMatches] =
    useState<number>(() => readStoredInt(CHAT_CONTEXT_MATCHES_STORAGE_KEY, 5, 1, 20));
  const [chatContextPreview, setChatContextPreview] = useState<ChatContextPreview | null>(null);
  const [chatAutoPreviewEnabled, setChatAutoPreviewEnabled] =
    useState<boolean>(() => readStoredBoolean(CHAT_AUTO_PREVIEW_STORAGE_KEY, true));
  const [chatKnowledgeEnabled, setChatKnowledgeEnabled] =
    useState<boolean>(() => readStoredBoolean(CHAT_KNOWLEDGE_ENABLED_STORAGE_KEY, true));
  const [chatKnowledgeQuery, setChatKnowledgeQuery] = useState('');
  const [chatKnowledgeMatches, setChatKnowledgeMatches] =
    useState<number>(() => readStoredInt(CHAT_KNOWLEDGE_MATCHES_STORAGE_KEY, 5, 1, 20));
  const [chatContextPreviewUpdatedAt, setChatContextPreviewUpdatedAt] = useState<string | null>(null);
  const [isPreviewingContext, setIsPreviewingContext] = useState(false);
  const [composer, setComposer] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isMediaBusy, setIsMediaBusy] = useState(false);
  const [isWorkspaceBusy, setIsWorkspaceBusy] = useState(false);
  const [isKnowledgeBusy, setIsKnowledgeBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    void refreshModelSelection(activeMode);
  }, [activeMode]);

  useEffect(() => {
    if (activeView === 'media') {
      void refreshMediaSurface();
    }
    if (activeView === 'system') {
      void refreshSystemSurface();
    }
    if (activeView === 'code') {
      void refreshWorkspaceSurface(workspacePath);
    }
    if (activeView === 'memory') {
      void refreshKnowledgeSurface();
    }
  }, [activeView]);

  useEffect(() => {
    writeStoredBoolean(CONTEXT_VISIBILITY_STORAGE_KEY, showWorkspaceContext);
  }, [showWorkspaceContext]);

  useEffect(() => {
    writeStoredString(CONTEXT_FILTER_STORAGE_KEY, workspaceContextFilter);
  }, [workspaceContextFilter]);

  useEffect(() => {
    writeStoredString(CHAT_WORKSPACE_PATH_STORAGE_KEY, chatWorkspacePath);
  }, [chatWorkspacePath]);

  useEffect(() => {
    writeStoredStringArray(CHAT_CONTEXT_PATHS_STORAGE_KEY, chatContextPaths);
  }, [chatContextPaths]);

  useEffect(() => {
    writeStoredString(CHAT_CONTEXT_MATCHES_STORAGE_KEY, String(chatContextMatches));
  }, [chatContextMatches]);

  useEffect(() => {
    writeStoredBoolean(CHAT_AUTO_PREVIEW_STORAGE_KEY, chatAutoPreviewEnabled);
  }, [chatAutoPreviewEnabled]);

  useEffect(() => {
    writeStoredBoolean(CHAT_KNOWLEDGE_ENABLED_STORAGE_KEY, chatKnowledgeEnabled);
  }, [chatKnowledgeEnabled]);

  useEffect(() => {
    writeStoredString(CHAT_KNOWLEDGE_MATCHES_STORAGE_KEY, String(chatKnowledgeMatches));
  }, [chatKnowledgeMatches]);

  useEffect(() => {
    if (!activeConversation?.id) {
      setCollapsedContextMessageIds({});
      return;
    }
    setCollapsedContextMessageIds(
      readStoredCollapsedMap(
        collapsedContextStorageKey(activeConversation.id),
      ),
    );
  }, [activeConversation?.id]);

  useEffect(() => {
    if (!activeConversation?.id) {
      return;
    }
    writeStoredRecord(
      collapsedContextStorageKey(activeConversation.id),
      collapsedContextMessageIds,
    );
  }, [activeConversation?.id, collapsedContextMessageIds]);

  const groupedModels = useMemo(() => {
    const ready = models.filter((model) => model.status === 'ready');
    const pending = models.filter((model) => model.status !== 'ready');
    return { ready, pending };
  }, [models]);

  const chatContextDiagnostics = useMemo(
    () => summarizeConversationContext(activeConversation),
    [activeConversation],
  );

  useEffect(() => {
    if (!chatAutoPreviewEnabled || activeView !== 'chat') {
      return;
    }
    if (!['coding', 'agent', 'swarm'].includes(activeMode)) {
      return;
    }

    const timer = window.setTimeout(() => {
      void previewChatContext({ silent: true });
    }, 450);

    return () => {
      window.clearTimeout(timer);
    };
  }, [
    chatAutoPreviewEnabled,
    activeView,
    activeMode,
    chatWorkspacePath,
    chatContextMatches,
    composer,
  ]);

  async function bootstrap() {
    try {
      setError(null);
      const [
        nextStatus,
        nextFanControls,
        nextModels,
        nextConversations,
        nextSession,
        nextKnowledgeStatus,
        nextKnowledgeSources,
      ] = await Promise.all([
        edisonApi.getStatus(),
        edisonApi.getFanControls(),
        edisonApi.listModels(),
        edisonApi.listConversations(),
        edisonApi.getSession(SESSION_ID),
        edisonApi.getKnowledgeStatus(),
        edisonApi.listKnowledgeSources(50),
      ]);
      setStatus(nextStatus);
      setFanControls(nextFanControls);
      setModels(nextModels);
      setConversations(nextConversations);
      setSessionState(nextSession);
      setKnowledgeStatus(nextKnowledgeStatus);
      setKnowledgeSources(nextKnowledgeSources);
      setActiveMode(nextSession.selected_mode ?? 'chat');
      if (nextConversations[0]) {
        await loadConversation(nextConversations[0].id);
      }
      await refreshMediaSurface();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to reach EDISON Core API');
    }
  }

  async function refreshModelSelection(mode: ChatMode) {
    try {
      const selection = await edisonApi.selectModel(mode);
      setModelSelection(selection);
      const nextSession = await edisonApi.updateSession(SESSION_ID, {
        selected_mode: mode,
        selected_model: selection.model.id,
      });
      setSessionState(nextSession);
    } catch {
      setModelSelection(null);
    }
  }

  async function loadConversation(conversationId: string) {
    const loaded = await edisonApi.getConversation(conversationId);
    setActiveConversation(loaded);
    setActiveMode(loaded.mode);
    setActiveView('chat');
  }

  function startNewConversation() {
    setActiveConversation(null);
    setComposer('');
    setActiveView('chat');
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = composer.trim();
    if (!content || isSending) {
      return;
    }

    setIsSending(true);
    setError(null);
    try {
      if (activeMode === 'media') {
        await handleMediaChatSend(content);
        return;
      }

      const payload = {
        conversation_id: activeConversation?.id ?? null,
        message: content,
        mode: activeMode,
        preferred_model: modelSelection?.model.id ?? null,
        memory_enabled: true,
        workspace_path: chatWorkspacePath.trim() || workspaceFile?.path,
        workspace_context_paths: chatContextPaths,
        include_workspace_context: ['coding', 'agent', 'swarm'].includes(activeMode),
        max_workspace_context_matches: chatContextMatches,
        include_knowledge_context: chatKnowledgeEnabled,
        knowledge_query: chatKnowledgeQuery.trim() || undefined,
        max_knowledge_context_matches: chatKnowledgeMatches,
      };
      const draftUserId = `draft-user-${Date.now()}`;
      const draftAssistantId = `draft-assistant-${Date.now()}`;
      let streamedContent = '';
      setActiveConversation((current) =>
        appendDraftChatTurn(current, activeMode, content, draftUserId, draftAssistantId),
      );
      setComposer('');

      const response = await edisonApi.streamChatTurn(payload, {
        onStart: (start) => {
          setModelSelection(start.model_selection);
          setActiveConversation((current) =>
            replaceDraftMessage(current, draftUserId, start.user_message, start.conversation_id),
          );
        },
        onToken: (delta) => {
          streamedContent += delta;
          setActiveConversation((current) =>
            updateDraftAssistantMessage(current, draftAssistantId, streamedContent),
          );
        },
        onError: (detail) => {
          setError(detail);
        },
      });
      setActiveConversation(response.conversation);
      setModelSelection(response.model_selection);
      setConversations(await edisonApi.listConversations());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Message failed');
    } finally {
      setIsSending(false);
    }
  }

  async function handleMediaChatSend(content: string) {
    const jobType = inferMediaJobType(content);
    const sourceArtifact = jobType === 'mesh' ? latestImageArtifactFromConversation(activeConversation) : null;
    const conversation = await ensureChatConversation(content, 'media');
    await edisonApi.addMessage(conversation.id, {
      role: 'user',
      content,
      metadata: { mode: 'media', source: 'chat-media-request' },
    });
    if (jobType === 'mesh' && !sourceArtifact) {
      await edisonApi.addMessage(conversation.id, {
        role: 'assistant',
        content: 'Modly is ready for image-to-3D. Add or generate an image in this chat first, then ask me to turn it into a 3D mesh.',
        model: 'modly',
        metadata: { delivery_type: 'media_job_guidance', backend: 'modly' },
      });
      setComposer('');
      setActiveConversation(await edisonApi.getConversation(conversation.id));
      setConversations(await edisonApi.listConversations());
      return;
    }
    const job = await edisonApi.createMediaJob({
      job_type: jobType,
      title: mediaJobTitle(content, jobType),
      prompt: content,
      source_artifact_id: sourceArtifact?.id ?? null,
      metadata: {
        source: 'chat',
        conversation_id: conversation.id,
        deliver_to_chat: true,
        source_artifact_id: sourceArtifact?.id ?? null,
        model_id: jobType === 'mesh' ? 'hunyuan3d-mini-fast/generate' : undefined,
        width: 1024,
        height: 1024,
        steps: 30,
        cfg: 6.5,
        sampler_name: 'dpmpp_2m',
        scheduler: 'karras',
        enhance_prompt: true,
      },
    });
    const statusLine = mediaJobStatusLine(job);
    const statusMessage = await edisonApi.addMessage(conversation.id, {
      role: 'assistant',
      content: statusLine,
      model: job.backend,
      metadata: {
        delivery_type: 'media_job_status',
        media_job: job,
      },
    });
    setComposer('');
    setActiveConversation(await edisonApi.getConversation(conversation.id));
    setConversations(await edisonApi.listConversations());
    await refreshMediaSurface();
    if (['queued', 'loading', 'generating', 'encoding'].includes(job.status)) {
      void pollMediaJobForChat(job.id, conversation.id, statusMessage.id);
    }
  }

  async function ensureChatConversation(firstMessage: string, mode: ChatMode): Promise<ConversationRecord> {
    if (activeConversation) {
      return activeConversation;
    }
    const created = await edisonApi.createConversation({
      title: conversationTitle(firstMessage),
      mode,
      memory_enabled: true,
    });
    setActiveConversation({ ...created, messages: [] });
    return created;
  }

  async function pollMediaJobForChat(jobId: string, conversationId: string, statusMessageId?: string) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      await sleep(2500);
      try {
        const synced = await edisonApi.syncMediaJob(jobId);
        if (statusMessageId) {
          setActiveConversation((current) => updateMediaStatusMessage(current, statusMessageId, synced));
        }
        if (synced.status === 'complete' && synced.result_artifact_id) {
          await edisonApi.deliverMediaJob(synced.id, conversationId);
          setActiveConversation(await edisonApi.getConversation(conversationId));
          await refreshMediaSurface();
          return;
        }
        if (['error', 'cancelled', 'setup_required'].includes(synced.status)) {
          await edisonApi.addMessage(conversationId, {
            role: 'assistant',
            content: mediaJobFailureLine(synced),
            model: synced.backend,
            metadata: {
              delivery_type: 'media_job_error',
              media_job: synced,
            },
          });
          setActiveConversation(await edisonApi.getConversation(conversationId));
          await refreshMediaSurface();
          return;
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'Media delivery failed');
        return;
      }
    }
    await refreshMediaSurface();
  }

  async function refreshMediaSurface() {
    try {
      const currentJobs = await edisonApi.listJobs();
      const activeJobs = currentJobs.filter((job) =>
        ['queued', 'loading', 'generating', 'encoding'].includes(job.status)
        && ['image', 'image_edit', 'video', 'mesh', 'audio'].includes(job.job_type)
        && typeof job.metadata.remote_job_id === 'string',
      );
      if (activeJobs.length > 0) {
        await Promise.all(activeJobs.slice(0, 6).map((job) => edisonApi.syncMediaJob(job.id)));
      }

      const [nextMediaStatus, nextMediaJobs, nextArtifacts] = await Promise.all([
        edisonApi.getMediaStatus(),
        edisonApi.listJobs(),
        edisonApi.listArtifacts(),
      ]);
      setMediaStatus(nextMediaStatus);
      setMediaJobs(nextMediaJobs.filter((job) => ['image', 'image_edit', 'video', 'mesh', 'audio'].includes(job.job_type)));
      setMediaArtifacts(nextArtifacts.filter((artifact) => ['image', 'video', 'mesh', 'audio'].includes(artifact.kind)));
      await deliverCompletedChatJobs(nextMediaJobs);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Media status failed');
    }
  }

  async function deliverCompletedChatJobs(jobs: JobRecord[]) {
    const deliverableJobs = jobs.filter((job) =>
      job.status === 'complete'
      && typeof job.result_artifact_id === 'string'
      && job.metadata.deliver_to_chat === true
      && typeof job.metadata.conversation_id === 'string'
      && typeof job.metadata.delivered_message_id !== 'string',
    );
    if (deliverableJobs.length === 0) {
      return;
    }
    const deliveredConversationIds = new Set<string>();
    for (const job of deliverableJobs) {
      const conversationId = String(job.metadata.conversation_id);
      await edisonApi.deliverMediaJob(job.id, conversationId);
      deliveredConversationIds.add(conversationId);
    }
    if (activeConversation?.id && deliveredConversationIds.has(activeConversation.id)) {
      setActiveConversation(await edisonApi.getConversation(activeConversation.id));
    }
  }

  async function refreshSystemSurface() {
    try {
      const [nextStatus, nextFanControls] = await Promise.all([
        edisonApi.getStatus(),
        edisonApi.getFanControls(),
      ]);
      setStatus(nextStatus);
      setFanControls(nextFanControls);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'System status failed');
    }
  }

  async function updateFanControl(gpuIndex: number, mode: GPUFanMode, manualSpeed: number) {
    setError(null);
    try {
      const updated = await edisonApi.updateFanControl(gpuIndex, {
        mode,
        manual_speed_percent: manualSpeed,
      });
      setFanControls((current) => {
        const controllers = current?.controllers ?? [];
        const nextControllers = controllers.some((controller) => controller.gpu.index === gpuIndex)
          ? controllers.map((controller) => (controller.gpu.index === gpuIndex ? updated : controller))
          : [...controllers, updated];
        return {
          service: current?.service ?? 'gpu-fan-control',
          hardware_control_enabled: updated.hardware_control_enabled,
          backend: updated.backend,
          controllers: nextControllers,
        };
      });
      setStatus(await edisonApi.getStatus());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Fan control update failed');
    }
  }

  async function useArtifactInChat(artifact: ArtifactRecord) {
    setError(null);
    try {
      const conversation = await ensureChatConversation(`Generated ${artifact.title}`, 'media');
      await edisonApi.addMessage(conversation.id, {
        role: 'assistant',
        content: `Here is ${artifact.title}.`,
        model: artifact.metadata.backend as string | undefined,
        metadata: {
          delivery_type: 'artifact_reference',
          artifacts: [artifact],
        },
      });
      setActiveConversation(await edisonApi.getConversation(conversation.id));
      setActiveView('chat');
      setConversations(await edisonApi.listConversations());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to add artifact to chat');
    }
  }

  async function createMediaReadinessJob(jobType: JobType, title: string, prompt: string) {
    setIsMediaBusy(true);
    setError(null);
    try {
      await edisonApi.createMediaJob({
        job_type: jobType,
        title,
        prompt,
        metadata: {
          source: 'media-studio-readiness-check',
          width: 1024,
          height: 1024,
          steps: jobType === 'image' ? 30 : undefined,
          cfg: jobType === 'image' ? 6.5 : undefined,
          sampler_name: jobType === 'image' ? 'dpmpp_2m' : undefined,
          scheduler: jobType === 'image' ? 'karras' : undefined,
          enhance_prompt: jobType === 'image',
        },
      });
      await refreshMediaSurface();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Media job failed');
    } finally {
      setIsMediaBusy(false);
    }
  }

  async function refreshWorkspaceSurface(path = workspacePath) {
    setIsWorkspaceBusy(true);
    setError(null);
    try {
      const [nextSummary, nextEntries] = await Promise.all([
        edisonApi.getWorkspaceSummary(),
        edisonApi.listWorkspaceFiles(path),
      ]);
      const nextScan = await edisonApi.getWorkspaceScan();
      setWorkspaceSummary(nextSummary);
      setWorkspaceScan(nextScan);
      setWorkspaceEntries(nextEntries);
      setWorkspacePath(path);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Workspace tools failed');
    } finally {
      setIsWorkspaceBusy(false);
    }
  }

  async function openWorkspaceEntry(entry: WorkspaceEntry) {
    setIsWorkspaceBusy(true);
    setError(null);
    try {
      if (entry.kind === 'directory') {
        setWorkspaceFile(null);
        setWorkspaceDraftContent('');
        setWorkspacePatchPreview(null);
        await refreshWorkspaceSurface(entry.path);
        return;
      }
      const file = await edisonApi.getWorkspaceFile(entry.path);
      setWorkspaceFile(file);
      setWorkspaceDraftContent(file.content);
      setWorkspacePatchPreview(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Workspace file failed');
    } finally {
      setIsWorkspaceBusy(false);
    }
  }

  async function openWorkspaceParent() {
    const parentPath = workspacePath.split('/').slice(0, -1).join('/');
    setWorkspaceFile(null);
    setWorkspaceDraftContent('');
    setWorkspacePatchPreview(null);
    await refreshWorkspaceSurface(parentPath);
  }

  async function previewWorkspacePatch() {
    if (!workspaceFile) {
      return;
    }
    setIsWorkspaceBusy(true);
    setError(null);
    try {
      const preview = await edisonApi.previewWorkspacePatch({
        path: workspaceFile.path,
        proposed_content: workspaceDraftContent,
      });
      setWorkspacePatchPreview(preview);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Patch preview failed');
    } finally {
      setIsWorkspaceBusy(false);
    }
  }

  async function applyWorkspacePatch() {
    if (!workspaceFile || !workspacePatchPreview) {
      return;
    }
    setIsWorkspaceBusy(true);
    setError(null);
    try {
      const result = await edisonApi.applyWorkspacePatch({
        path: workspaceFile.path,
        proposed_content: workspaceDraftContent,
        expected_sha256: workspacePatchPreview.current_sha256,
        approved: true,
      });
      setWorkspaceFile(result.file);
      setWorkspaceDraftContent(result.file.content);
      setWorkspacePatchPreview(null);
      await refreshWorkspaceSurface(workspacePath);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Patch apply failed');
    } finally {
      setIsWorkspaceBusy(false);
    }
  }

  async function runWorkspaceCommand(command: WorkspaceCommand) {
    setIsWorkspaceBusy(true);
    setError(null);
    try {
      const result = await edisonApi.runWorkspaceCommand({
        command: command.command,
        cwd: command.cwd,
        timeout_seconds: 120,
        approved: true,
      });
      setWorkspaceCommandResult(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Command run failed');
    } finally {
      setIsWorkspaceBusy(false);
    }
  }

  async function handleWorkspaceSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = workspaceSearchQuery.trim();
    if (!query) {
      return;
    }
    setIsWorkspaceBusy(true);
    setError(null);
    try {
      const results = await edisonApi.searchWorkspace({ query, max_results: 80 });
      setWorkspaceSearchResults(results);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Workspace search failed');
    } finally {
      setIsWorkspaceBusy(false);
    }
  }

  async function refreshKnowledgeSurface() {
    setIsKnowledgeBusy(true);
    setError(null);
    try {
      const [nextStatus, nextSources] = await Promise.all([
        edisonApi.getKnowledgeStatus(),
        edisonApi.listKnowledgeSources(100),
      ]);
      setKnowledgeStatus(nextStatus);
      setKnowledgeSources(nextSources);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Knowledge status failed');
    } finally {
      setIsKnowledgeBusy(false);
    }
  }

  async function handleKnowledgeSearch(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const query = knowledgeSearchQuery.trim();
    if (!query) {
      setKnowledgeSearchResults([]);
      return;
    }
    setIsKnowledgeBusy(true);
    setError(null);
    try {
      const results = await edisonApi.searchKnowledge({ query, max_results: 20 });
      setKnowledgeSearchResults(results);
      setKnowledgeNotice(results.length > 0 ? `Found ${results.length} knowledge match${results.length === 1 ? '' : 'es'}.` : 'No knowledge matches found.');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Knowledge search failed');
    } finally {
      setIsKnowledgeBusy(false);
    }
  }

  async function ingestKnowledgeText(payload: { title: string; text: string; uri?: string }) {
    setIsKnowledgeBusy(true);
    setError(null);
    try {
      const source = await edisonApi.ingestKnowledgeText({
        title: payload.title,
        text: payload.text,
        uri: payload.uri || undefined,
        metadata: { source: 'memory-center' },
      });
      setKnowledgeNotice(`Imported ${source.title}.`);
      await refreshKnowledgeSurface();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Text import failed');
    } finally {
      setIsKnowledgeBusy(false);
    }
  }

  async function ingestKnowledgeUrl(payload: { url: string; title?: string }) {
    setIsKnowledgeBusy(true);
    setError(null);
    try {
      const source = await edisonApi.ingestKnowledgeUrl({
        url: payload.url,
        title: payload.title || undefined,
      });
      setKnowledgeNotice(`Imported ${source.title}.`);
      await refreshKnowledgeSurface();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'URL import failed');
    } finally {
      setIsKnowledgeBusy(false);
    }
  }

  async function ingestKnowledgeWikipedia(payload: { title: string; language?: string }) {
    setIsKnowledgeBusy(true);
    setError(null);
    try {
      const source = await edisonApi.ingestKnowledgeWikipedia({
        title: payload.title,
        language: payload.language || 'en',
      });
      setKnowledgeNotice(`Imported ${source.title}.`);
      await refreshKnowledgeSurface();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Wikipedia import failed');
    } finally {
      setIsKnowledgeBusy(false);
    }
  }

  async function ingestKnowledgeLocal(payload: { path: string; glob: string; max_files: number }) {
    setIsKnowledgeBusy(true);
    setError(null);
    try {
      const sources = await edisonApi.ingestKnowledgeLocal(payload);
      setKnowledgeNotice(`Indexed ${sources.length} local file${sources.length === 1 ? '' : 's'}.`);
      await refreshKnowledgeSurface();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Local knowledge import failed');
    } finally {
      setIsKnowledgeBusy(false);
    }
  }

  async function ingestKnowledgePreset(preset: 'coding-core' | 'ai-foundations') {
    setIsKnowledgeBusy(true);
    setError(null);
    try {
      const sources = await edisonApi.ingestKnowledgePreset({ preset });
      setKnowledgeNotice(`Loaded ${sources.length} ${preset.replace('-', ' ')} source${sources.length === 1 ? '' : 's'}.`);
      await refreshKnowledgeSurface();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Preset import failed');
    } finally {
      setIsKnowledgeBusy(false);
    }
  }

  async function previewChatContext(options: { silent?: boolean } = {}) {
    const silent = Boolean(options.silent);
    setIsPreviewingContext(true);
    if (!silent) {
      setError(null);
    }
    try {
      const warnings: string[] = [];
      const instructionPath = chatWorkspacePath.trim();
      const query = composer.trim();

      const instructionPromise = instructionPath
        ? edisonApi.getWorkspaceInstructionContext(instructionPath)
        : Promise.resolve(null);
      const indexPromise = query
        ? edisonApi.searchWorkspaceIndex({ query, max_results: chatContextMatches })
        : Promise.resolve([] as WorkspaceIndexSearchMatch[]);

      const [instructionContext, indexMatches] = await Promise.all([instructionPromise, indexPromise]);

      if (!instructionPath) {
        warnings.push('Set a target file path to preview instruction context.');
      }
      if (!query) {
        warnings.push('Type a draft message to preview semantic index hits.');
      }

      setChatContextPreview({
        instructionContext,
        indexMatches,
        warnings,
      });
      setChatContextPreviewUpdatedAt(new Date().toLocaleTimeString());
    } catch (caught) {
      if (!silent) {
        setError(caught instanceof Error ? caught.message : 'Context preview failed');
      }
    } finally {
      setIsPreviewingContext(false);
    }
  }

  function addChatContextPath(path: string) {
    const normalized = path.trim();
    if (!normalized) {
      return;
    }
    setChatContextPaths((current) => {
      if (current.includes(normalized)) {
        return current;
      }
      return [...current, normalized].slice(-12);
    });
  }

  function removeChatContextPath(path: string) {
    setChatContextPaths((current) => current.filter((value) => value !== path));
  }

  return (
    <div className={inspectorCollapsed ? 'app-shell inspector-collapsed' : 'app-shell'}>
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-block">
          <div className="brand-mark"><Sparkles size={20} /></div>
          <div>
            <h1>EDISON V2</h1>
            <p>Local AI PC</p>
          </div>
        </div>

        <button className="new-chat-button" onClick={startNewConversation} type="button">
          <MessageSquare size={17} />
          <span>New chat</span>
        </button>

        <nav className="nav-stack">
          {navigation.map((item) => {
            const Icon = item.icon;
            return (
              <button
                aria-current={item.id === activeView ? 'page' : undefined}
                className={item.id === activeView ? 'nav-item active' : 'nav-item'}
                key={item.id}
                onClick={() => setActiveView(item.id)}
                type="button"
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <section className="sidebar-section">
          <div className="section-label">Conversations</div>
          <div className="conversation-list">
            {conversations.map((conversation) => (
              <button
                className={conversation.id === activeConversation?.id ? 'conversation-item active' : 'conversation-item'}
                key={conversation.id}
                onClick={() => void loadConversation(conversation.id)}
                type="button"
              >
                <span>{conversation.title}</span>
                <small>{conversation.mode}</small>
              </button>
            ))}
            {conversations.length === 0 && <div className="empty-line">No conversations</div>}
          </div>
        </section>

        <section className="sidebar-footer">
          <ShieldCheck size={17} />
          <span>{status?.gpu_devices.length ?? 0} GPUs available</span>
        </section>
      </aside>

      <main className={activeView === 'chat' ? 'workspace chat-workspace' : 'workspace section-workspace'}>
        <header className="topbar">
          <div>
            <p className="eyebrow">{activeView === 'chat' ? 'Conversation' : 'Workspace'}</p>
            <h2>{viewTitle(activeView, activeConversation)}</h2>
          </div>
          <div className="status-row">
            <span className={status?.status === 'ok' ? 'status-pill ok' : 'status-pill'}>
              <Activity size={15} /> {status?.status === 'ok' ? 'Connected' : status?.status ?? 'Offline'}
            </span>
            <span className="status-pill"><Cpu size={15} /> {status?.gpu_devices.length ?? 0} GPUs</span>
            <span className="status-pill"><Fan size={15} /> {fanControls?.controllers.length ?? 0} fan controls</span>
            <button
              className="icon-button"
              onClick={() => setInspectorCollapsed((current) => !current)}
              title={inspectorCollapsed ? 'Show system panel' : 'Hide system panel'}
              type="button"
            >
              {inspectorCollapsed ? <PanelRightOpen size={18} /> : <PanelRightClose size={18} />}
            </button>
          </div>
        </header>

        {activeView === 'chat' && (
          <section className="mode-strip" aria-label="Mode selector">
            {modes.map((mode) => (
              <button
                className={mode.value === activeMode ? 'mode-button active' : 'mode-button'}
                key={mode.value}
                onClick={() => setActiveMode(mode.value)}
                type="button"
              >
                <span>{mode.label}</span>
                <small>{mode.description}</small>
              </button>
            ))}
          </section>
        )}

        {error && <div className="error-banner">{friendlyError(error)}</div>}

        {activeView === 'chat' ? (
          <ChatView
            activeConversation={activeConversation}
            composer={composer}
            handleSend={handleSend}
            isSending={isSending}
            modelSelection={modelSelection}
            setComposer={setComposer}
            showWorkspaceContext={showWorkspaceContext}
            setShowWorkspaceContext={setShowWorkspaceContext}
            workspaceContextFilter={workspaceContextFilter}
            setWorkspaceContextFilter={setWorkspaceContextFilter}
            collapsedContextMessageIds={collapsedContextMessageIds}
            setCollapsedContextMessageIds={setCollapsedContextMessageIds}
            chatWorkspacePath={chatWorkspacePath}
            setChatWorkspacePath={setChatWorkspacePath}
            chatContextPaths={chatContextPaths}
            addChatContextPath={addChatContextPath}
            removeChatContextPath={removeChatContextPath}
            chatContextMatches={chatContextMatches}
            setChatContextMatches={setChatContextMatches}
            activeWorkspaceFilePath={workspaceFile?.path}
            chatContextDiagnostics={chatContextDiagnostics}
            chatContextPreview={chatContextPreview}
            chatContextPreviewUpdatedAt={chatContextPreviewUpdatedAt}
            isPreviewingContext={isPreviewingContext}
            previewChatContext={previewChatContext}
            chatAutoPreviewEnabled={chatAutoPreviewEnabled}
            setChatAutoPreviewEnabled={setChatAutoPreviewEnabled}
            chatKnowledgeEnabled={chatKnowledgeEnabled}
            setChatKnowledgeEnabled={setChatKnowledgeEnabled}
            chatKnowledgeQuery={chatKnowledgeQuery}
            setChatKnowledgeQuery={setChatKnowledgeQuery}
            chatKnowledgeMatches={chatKnowledgeMatches}
            setChatKnowledgeMatches={setChatKnowledgeMatches}
            knowledgeStatus={knowledgeStatus}
            resetWorkspaceContextPreferences={() => {
              setShowWorkspaceContext(true);
              setWorkspaceContextFilter('all');
              setCollapsedContextMessageIds({});
              setChatWorkspacePath('');
              setChatContextPaths([]);
              setChatContextMatches(5);
              setChatAutoPreviewEnabled(true);
              setChatKnowledgeEnabled(true);
              setChatKnowledgeQuery('');
              setChatKnowledgeMatches(5);
              setChatContextPreview(null);
              setChatContextPreviewUpdatedAt(null);
              removeStoredValue(CONTEXT_VISIBILITY_STORAGE_KEY);
              removeStoredValue(CONTEXT_FILTER_STORAGE_KEY);
              removeStoredValue(CHAT_WORKSPACE_PATH_STORAGE_KEY);
              removeStoredValue(CHAT_CONTEXT_PATHS_STORAGE_KEY);
              removeStoredValue(CHAT_CONTEXT_MATCHES_STORAGE_KEY);
              removeStoredValue(CHAT_AUTO_PREVIEW_STORAGE_KEY);
              removeStoredValue(CHAT_KNOWLEDGE_ENABLED_STORAGE_KEY);
              removeStoredValue(CHAT_KNOWLEDGE_MATCHES_STORAGE_KEY);
              if (activeConversation?.id) {
                removeStoredValue(collapsedContextStorageKey(activeConversation.id));
              }
            }}
            recentArtifacts={mediaArtifacts.slice(0, 4)}
            onUseArtifactInChat={useArtifactInChat}
          />
        ) : (
          <WorkbenchView
            activeView={activeView}
            groupedModels={groupedModels}
            fanControls={fanControls}
            artifacts={mediaArtifacts}
            isMediaBusy={isMediaBusy}
            isWorkspaceBusy={isWorkspaceBusy}
            isKnowledgeBusy={isKnowledgeBusy}
            knowledgeNotice={knowledgeNotice}
            knowledgeSearchQuery={knowledgeSearchQuery}
            knowledgeSearchResults={knowledgeSearchResults}
            knowledgeSources={knowledgeSources}
            knowledgeStatus={knowledgeStatus}
            mediaJobs={mediaJobs}
            mediaStatus={mediaStatus}
            models={models}
            onCreateMediaJob={createMediaReadinessJob}
            onOpenCompareConversation={loadConversation}
            onRefreshConversations={async () => {
              setConversations(await edisonApi.listConversations());
            }}
            onIngestKnowledgeLocal={ingestKnowledgeLocal}
            onIngestKnowledgePreset={ingestKnowledgePreset}
            onIngestKnowledgeText={ingestKnowledgeText}
            onIngestKnowledgeUrl={ingestKnowledgeUrl}
            onIngestKnowledgeWikipedia={ingestKnowledgeWikipedia}
            onOpenWorkspaceEntry={openWorkspaceEntry}
            onRefreshKnowledge={refreshKnowledgeSurface}
            onRefreshMedia={refreshMediaSurface}
            onRefreshSystem={refreshSystemSurface}
            onUpdateFanControl={updateFanControl}
            onUseArtifactInChat={useArtifactInChat}
            onRefreshWorkspace={() => refreshWorkspaceSurface(workspacePath)}
            onKnowledgeSearch={handleKnowledgeSearch}
            onWorkspaceParent={openWorkspaceParent}
            onWorkspaceSearch={handleWorkspaceSearch}
            sessionState={sessionState}
            status={status}
            workspaceCommandResult={workspaceCommandResult}
            workspaceEntries={workspaceEntries}
            workspaceDraftContent={workspaceDraftContent}
            workspaceFile={workspaceFile}
            workspacePath={workspacePath}
            workspacePatchPreview={workspacePatchPreview}
            workspaceScan={workspaceScan}
            workspaceSearchQuery={workspaceSearchQuery}
            workspaceSearchResults={workspaceSearchResults}
            workspaceSummary={workspaceSummary}
            setWorkspaceDraftContent={(value) => {
              setWorkspaceDraftContent(value);
              setWorkspacePatchPreview(null);
            }}
            setKnowledgeSearchQuery={setKnowledgeSearchQuery}
            setWorkspaceSearchQuery={setWorkspaceSearchQuery}
            onApplyWorkspacePatch={applyWorkspacePatch}
            onPreviewWorkspacePatch={previewWorkspacePatch}
            onRunWorkspaceCommand={runWorkspaceCommand}
            onAddChatContextPath={addChatContextPath}
          />
        )}
      </main>

      <aside className={inspectorCollapsed ? 'inspector collapsed' : 'inspector'} aria-label="System inspector">
        <section className="inspector-section inspector-header">
          <div className="section-heading">
            <Server size={18} />
            <h3>Edison</h3>
          </div>
          <button className="icon-button" onClick={() => setInspectorCollapsed(true)} title="Collapse panel" type="button">
            <PanelRightClose size={18} />
          </button>
        </section>

        <section className="inspector-section">
          <dl className="metric-grid">
            <div>
              <dt>Core</dt>
              <dd>{status?.status === 'ok' ? 'Online' : status?.status ?? 'Offline'}</dd>
            </div>
            <div>
              <dt>Models</dt>
              <dd>{status?.model_count ?? models.length}</dd>
            </div>
            <div>
              <dt>GPUs</dt>
              <dd>{status?.gpu_devices.length ?? 0}</dd>
            </div>
            <div>
              <dt>Mode</dt>
              <dd>{sessionState?.selected_mode ?? activeMode}</dd>
            </div>
          </dl>
        </section>

        <section className="inspector-section">
          <div className="section-heading">
            <Brain size={18} />
            <h3>Selected Model</h3>
          </div>
          {modelSelection ? (
            <div className="lane-card">
              <strong>{modelSelection.model.display_name}</strong>
              <span>{modelSelection.model.status.replace('_', ' ')}</span>
              <p>{modelSelection.required_capabilities.join(' / ')}</p>
            </div>
          ) : (
            <div className="empty-line">No lane for {activeMode}</div>
          )}
        </section>

        <section className="inspector-section">
          <div className="section-heading">
            <Network size={18} />
            <h3>Model Lanes</h3>
          </div>
          <div className="model-list">
            {models.map((model) => (
              <article className="model-row" key={model.id}>
                <div>
                  <strong>{model.display_name}</strong>
                  <span>{model.capabilities.slice(0, 3).join(' / ')}</span>
                </div>
                <small className={`model-status ${model.status}`}>{model.status.replace('_', ' ')}</small>
              </article>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}

function ChatView({
  activeConversation,
  composer,
  handleSend,
  isSending,
  modelSelection,
  setComposer,
  showWorkspaceContext,
  setShowWorkspaceContext,
  workspaceContextFilter,
  setWorkspaceContextFilter,
  collapsedContextMessageIds,
  setCollapsedContextMessageIds,
  chatWorkspacePath,
  setChatWorkspacePath,
  chatContextPaths,
  addChatContextPath,
  removeChatContextPath,
  chatContextMatches,
  setChatContextMatches,
  activeWorkspaceFilePath,
  chatContextDiagnostics,
  chatContextPreview,
  chatContextPreviewUpdatedAt,
  isPreviewingContext,
  previewChatContext,
  chatAutoPreviewEnabled,
  setChatAutoPreviewEnabled,
  chatKnowledgeEnabled,
  setChatKnowledgeEnabled,
  chatKnowledgeQuery,
  setChatKnowledgeQuery,
  chatKnowledgeMatches,
  setChatKnowledgeMatches,
  knowledgeStatus,
  resetWorkspaceContextPreferences,
  recentArtifacts,
  onUseArtifactInChat,
}: {
  activeConversation: ConversationWithMessages | null;
  composer: string;
  handleSend: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  isSending: boolean;
  modelSelection: ModelSelection | null;
  setComposer: (value: string) => void;
  showWorkspaceContext: boolean;
  setShowWorkspaceContext: (value: boolean) => void;
  workspaceContextFilter: ContextFilter;
  setWorkspaceContextFilter: (value: ContextFilter) => void;
  collapsedContextMessageIds: Record<string, boolean>;
  setCollapsedContextMessageIds: (value: Record<string, boolean> | ((current: Record<string, boolean>) => Record<string, boolean>)) => void;
  chatWorkspacePath: string;
  setChatWorkspacePath: (value: string) => void;
  chatContextPaths: string[];
  addChatContextPath: (path: string) => void;
  removeChatContextPath: (path: string) => void;
  chatContextMatches: number;
  setChatContextMatches: (value: number) => void;
  activeWorkspaceFilePath?: string;
  chatContextDiagnostics: ChatContextDiagnostics;
  chatContextPreview: ChatContextPreview | null;
  chatContextPreviewUpdatedAt: string | null;
  isPreviewingContext: boolean;
  previewChatContext: () => Promise<void>;
  chatAutoPreviewEnabled: boolean;
  setChatAutoPreviewEnabled: (value: boolean) => void;
  chatKnowledgeEnabled: boolean;
  setChatKnowledgeEnabled: (value: boolean) => void;
  chatKnowledgeQuery: string;
  setChatKnowledgeQuery: (value: string) => void;
  chatKnowledgeMatches: number;
  setChatKnowledgeMatches: (value: number) => void;
  knowledgeStatus: KnowledgeStatus | null;
  resetWorkspaceContextPreferences: () => void;
  recentArtifacts: ArtifactRecord[];
  onUseArtifactInChat: (artifact: ArtifactRecord) => void;
}) {
  const selectedModelName = modelSelection?.model.display_name ?? 'Model lane';
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const lastMessage = activeConversation?.messages[activeConversation.messages.length - 1];
  const contextSummary = chatContextPaths.length > 0
    ? `${chatContextPaths.length} focus file${chatContextPaths.length === 1 ? '' : 's'}`
    : chatWorkspacePath.trim()
      ? 'Target file set'
      : 'Add repo context';

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: 'end' });
  }, [activeConversation?.id, activeConversation?.messages.length, lastMessage?.content, isSending]);

  function useSuggestion(prompt: string) {
    setComposer(composer.trim() ? `${composer.trim()}\n\n${prompt}` : prompt);
  }

  return (
    <>
      <details className="context-drawer rag-drawer">
        <summary>
          <span><Database size={16} /> Knowledge</span>
          <small>
            {knowledgeStatus
              ? `${knowledgeStatus.source_count} sources / ${knowledgeStatus.chunk_count} chunks`
              : 'RAG source status'}
          </small>
        </summary>
        <div className="context-drawer-content rag-drawer-content">
          <section className="rag-chat-controls" aria-label="Chat knowledge controls">
            <button
              className={chatKnowledgeEnabled ? 'mode-button active' : 'mode-button'}
              onClick={() => setChatKnowledgeEnabled(!chatKnowledgeEnabled)}
              type="button"
            >
              <span>{chatKnowledgeEnabled ? 'Knowledge On' : 'Knowledge Off'}</span>
              <small>{chatKnowledgeEnabled ? 'Use RAG in replies' : 'No source retrieval'}</small>
            </button>
            <label htmlFor="chat-knowledge-query">Search wording</label>
            <input
              id="chat-knowledge-query"
              value={chatKnowledgeQuery}
              onChange={(event) => setChatKnowledgeQuery(event.target.value)}
              placeholder="Use message text"
            />
            <label htmlFor="chat-knowledge-matches">Sources</label>
            <input
              id="chat-knowledge-matches"
              type="number"
              min={1}
              max={20}
              value={chatKnowledgeMatches}
              onChange={(event) => {
                const parsed = Number.parseInt(event.target.value, 10);
                if (!Number.isNaN(parsed)) {
                  setChatKnowledgeMatches(Math.max(1, Math.min(20, parsed)));
                }
              }}
            />
          </section>
        </div>
      </details>
      <details className="context-drawer">
        <summary>
          <span><Folder size={16} /> Repo context</span>
          <small>{contextSummary}</small>
        </summary>
        <div className="context-drawer-content">
      <section className="chat-context-controls" aria-label="Workspace context controls">
        <button
          className={showWorkspaceContext ? 'mode-button active' : 'mode-button'}
          onClick={() => setShowWorkspaceContext(!showWorkspaceContext)}
          type="button"
        >
          {showWorkspaceContext ? 'Hide Context Cards' : 'Show Context Cards'}
        </button>
        <label className="context-filter-label" htmlFor="context-filter">
          Filter
        </label>
        <select
          id="context-filter"
          value={workspaceContextFilter}
          onChange={(event) =>
            setWorkspaceContextFilter(
              event.target.value as ContextFilter,
            )
          }
        >
          <option value="all">All Context</option>
          <option value="instructions">Instructions Only</option>
          <option value="index">Index Hits Only</option>
          <option value="warnings">Warnings Only</option>
        </select>
        <button className="secondary-button" onClick={resetWorkspaceContextPreferences} type="button">
          Reset
        </button>
      </section>
      <section className="chat-context-config" aria-label="Chat workspace context configuration">
        <label htmlFor="chat-workspace-path">Target file path</label>
        <input
          id="chat-workspace-path"
          value={chatWorkspacePath}
          onChange={(event) => setChatWorkspacePath(event.target.value)}
          placeholder="apps/api/edison_core/api/routes_chat.py"
        />
        <button
          className="secondary-button"
          disabled={!activeWorkspaceFilePath}
          onClick={() => {
            setChatWorkspacePath(activeWorkspaceFilePath ?? '');
            if (activeWorkspaceFilePath) {
              addChatContextPath(activeWorkspaceFilePath);
            }
          }}
          type="button"
        >
          Use Active Code File
        </button>
        <button
          className="secondary-button"
          disabled={!chatWorkspacePath.trim()}
          onClick={() => addChatContextPath(chatWorkspacePath)}
          type="button"
        >
          Add Target To Focus
        </button>
        <label htmlFor="chat-context-matches">Index matches</label>
        <input
          id="chat-context-matches"
          type="number"
          min={1}
          max={20}
          value={chatContextMatches}
          onChange={(event) => {
            const parsed = Number.parseInt(event.target.value, 10);
            if (Number.isNaN(parsed)) {
              return;
            }
            setChatContextMatches(Math.max(1, Math.min(20, parsed)));
          }}
        />
        <label className="chat-auto-preview-toggle">
          <input
            type="checkbox"
            checked={chatAutoPreviewEnabled}
            onChange={(event) => setChatAutoPreviewEnabled(event.target.checked)}
          />
          Auto preview
        </label>
        <button className="secondary-button" onClick={() => void previewChatContext()} type="button">
          {isPreviewingContext ? 'Previewing...' : 'Preview Context'}
        </button>
      </section>
      {chatContextPaths.length > 0 && (
        <section className="chat-focus-paths" aria-label="Focused workspace files">
          <div className="section-label">Focus Files ({chatContextPaths.length})</div>
          <div className="chat-focus-path-list">
            {chatContextPaths.map((path) => (
              <button
                className={path === chatWorkspacePath ? 'chat-focus-chip active' : 'chat-focus-chip'}
                key={path}
                onClick={() => setChatWorkspacePath(path)}
                type="button"
                title="Set as target path"
              >
                <span>{path}</span>
                <strong
                  aria-label={`Remove ${path} from focus files`}
                  onClick={(event) => {
                    event.stopPropagation();
                    removeChatContextPath(path);
                  }}
                >
                  <X size={13} />
                </strong>
              </button>
            ))}
          </div>
        </section>
      )}
      <section className="chat-context-diagnostics" aria-label="Conversation context diagnostics">
        <span>Assistant turns with context: {chatContextDiagnostics.assistantTurnsWithContext}</span>
        <span>Focus files: {chatContextDiagnostics.focusPaths}</span>
        <span>Instructions: {chatContextDiagnostics.instructions}</span>
        <span>Index hits: {chatContextDiagnostics.indexMatches}</span>
        <span>Warnings: {chatContextDiagnostics.warnings}</span>
        {chatContextDiagnostics.latestTargetPath && (
          <span>Latest target: {chatContextDiagnostics.latestTargetPath}</span>
        )}
      </section>
      {chatContextPreview && (
        <section className="chat-context-preview" aria-label="Pre-send context preview">
          <div className="section-label">Context Preview</div>
          {chatContextPreviewUpdatedAt && (
            <div className="chat-context-preview-updated">Updated {chatContextPreviewUpdatedAt}</div>
          )}
          {chatContextPreview.instructionContext && (
            <div className="chat-context-preview-block">
              <strong>Instruction Files ({chatContextPreview.instructionContext.selected_files.length})</strong>
              <div className="chat-context-preview-list">
                {chatContextPreview.instructionContext.selected_files.slice(0, 6).map((file) => (
                  <span key={file.path}>{file.path}</span>
                ))}
              </div>
            </div>
          )}
          {chatContextPreview.indexMatches.length > 0 && (
            <div className="chat-context-preview-block">
              <strong>Semantic Index Hits ({chatContextPreview.indexMatches.length})</strong>
              <div className="chat-context-preview-list detailed">
                {chatContextPreview.indexMatches.slice(0, 6).map((match) => (
                  <div className="chat-context-preview-hit" key={`${match.path}-${match.line_number ?? 0}`}>
                    <div className="chat-context-preview-hit-meta">
                      <span>{match.path}{match.line_number ? `:${match.line_number}` : ''}</span>
                      <span>score {match.score.toFixed(2)}</span>
                      {match.language && <span>{match.language}</span>}
                    </div>
                    <p>{match.snippet}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {(chatContextPreview.warnings.length > 0
            || (chatContextPreview.instructionContext?.warnings.length ?? 0) > 0) && (
            <div className="chat-context-preview-block warnings">
              <strong>Preview Warnings</strong>
              <div className="chat-context-preview-list">
                {chatContextPreview.warnings.map((warning) => <span key={warning}>{warning}</span>)}
                {(chatContextPreview.instructionContext?.warnings ?? []).map((warning) => (
                  <span key={`instruction-${warning}`}>{warning}</span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
        </div>
      </details>
      <section className="chat-surface" aria-label="Conversation messages">
        {activeConversation?.messages.map((message) => {
          const parsedContext =
            message.role === 'assistant' ? parseWorkspaceContext(message.metadata.workspace_context) : null;
          const parsedKnowledge =
            message.role === 'assistant' ? parseKnowledgeContext(message.metadata.knowledge_context) : null;
          const contextCount = parsedContext && parsedContext.enabled ? contextItemCount(parsedContext) : 0;
          const knowledgeCount = parsedKnowledge && parsedKnowledge.enabled ? parsedKnowledge.matches.length : 0;
          const contextDetails = parsedContext && parsedContext.enabled
            ? contextBreakdownText(parsedContext)
            : '';
          const knowledgeDetails = parsedKnowledge && parsedKnowledge.enabled
            ? `Knowledge matches: ${knowledgeCount}${parsedKnowledge.query ? ` for "${parsedKnowledge.query}"` : ''}`
            : '';
          const isContextCollapsed = Boolean(collapsedContextMessageIds[message.id]);
          return (
            <article className={`message ${message.role}`} key={message.id}>
              <div className="message-avatar">{message.role === 'user' ? 'You' : 'AI'}</div>
              <div className="message-body">
                <div className="message-meta">
                  <span>{message.role}</span>
                  {message.model && <span>{message.model}</span>}
                  {contextCount > 0 && (
                    <span
                      className="message-context-badge"
                      title={contextDetails}
                      aria-label={contextDetails}
                    >
                      Context {contextCount}
                    </span>
                  )}
                  {knowledgeCount > 0 && (
                    <span
                      className="message-context-badge knowledge"
                      title={knowledgeDetails}
                      aria-label={knowledgeDetails}
                    >
                      Sources {knowledgeCount}
                    </span>
                  )}
                </div>
                <MessageContent content={message.content} metadata={message.metadata} />
                {message.role === 'assistant' && (
                  <>
                    <KnowledgeContextView metadata={message.metadata} />
                    <WorkspaceContextView
                      metadata={message.metadata}
                      visible={showWorkspaceContext}
                      filter={workspaceContextFilter}
                      collapsed={isContextCollapsed}
                      onToggleCollapse={() =>
                        setCollapsedContextMessageIds((current) => ({
                          ...current,
                          [message.id]: !Boolean(current[message.id]),
                        }))
                      }
                    />
                  </>
                )}
              </div>
            </article>
          );
        })}
        {!activeConversation?.messages.length && (
          <div className="empty-chat">
            <div className="empty-chat-mark"><Bot size={28} /></div>
            <h3>What should Edison help with?</h3>
            <div className="prompt-grid">
              {promptSuggestions.map((suggestion) => {
                const Icon = suggestion.icon;
                return (
                  <button
                    className="prompt-card"
                    key={suggestion.title}
                    onClick={() => useSuggestion(suggestion.prompt)}
                    type="button"
                  >
                    <Icon size={18} />
                    <span>{suggestion.title}</span>
                    <small>{suggestion.subtitle}</small>
                  </button>
                );
              })}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </section>

      {recentArtifacts.length > 0 && (
        <section className="artifact-dock" aria-label="Recent generated artifacts">
          <div className="section-label">Recent Outputs</div>
          <div className="artifact-dock-list">
            {recentArtifacts.map((artifact) => (
              <article className="artifact-card compact" key={artifact.id}>
                <div>
                  <strong>{artifact.title}</strong>
                  <span>{artifact.kind} / {artifact.mime_type ?? 'file'}</span>
                </div>
                <div className="artifact-card-actions">
                  <a className="secondary-button" href={edisonApi.artifactDownloadUrl(artifact.id)} target="_blank" rel="noreferrer">
                    Download
                  </a>
                  <button className="secondary-button" onClick={() => onUseArtifactInChat(artifact)} type="button">
                    Use In Chat
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="composer-panel" aria-label="Message composer">
        <div className="composer-meta">
          <span>{selectedModelName}</span>
          <span>{modelSelection?.model.status.replace('_', ' ') ?? 'Select a lane'}</span>
        </div>
        <form className="composer" onSubmit={(event) => void handleSend(event)}>
          <textarea
            aria-label="Message Edison"
            onChange={(event) => setComposer(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Message Edison"
            rows={3}
            value={composer}
          />
          <button disabled={!composer.trim() || isSending} title="Send message" type="submit">
            <Send size={18} />
            <span>{isSending ? 'Thinking' : 'Send'}</span>
          </button>
        </form>
      </section>
    </>
  );
}

function MessageContent({ content, metadata }: { content: string; metadata: Record<string, unknown> }) {
  const blocks = parseMessageBlocks(content);
  const artifacts = artifactsFromMetadata(metadata);
  const mediaJob = mediaJobFromMetadata(metadata);
  return (
    <div className="message-content">
      {blocks.length === 0 && artifacts.length === 0 && !mediaJob && (
        <div className="typing-indicator" aria-label="Edison is responding">
          <span />
          <span />
          <span />
        </div>
      )}
      {blocks.map((block, index) => {
        if (block.kind === 'code') {
          return (
            <pre className="message-code-block" key={`${block.kind}-${index}`}>
              {block.language && <span>{block.language}</span>}
              <code>{block.text}</code>
            </pre>
          );
        }
        if (block.kind === 'ul' || block.kind === 'ol') {
          const ListTag = block.kind;
          return (
            <ListTag className="message-list" key={`${block.kind}-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${item}-${itemIndex}`}>{renderInlineMessageText(item)}</li>
              ))}
            </ListTag>
          );
        }
        if (block.kind === 'paragraph') {
          return <p key={`${block.kind}-${index}`}>{renderInlineMessageText(block.text)}</p>;
        }
        return null;
      })}
      {mediaJob && <MediaJobInlineCard job={mediaJob} />}
      {artifacts.length > 0 && (
        <div className="message-artifacts">
          {artifacts.map((artifact) => {
            const downloadUrl = edisonApi.artifactDownloadUrl(artifact.id);
            return (
              <article className="message-artifact-card" key={artifact.id}>
                {artifact.kind === 'image' && <img alt={artifact.title} src={downloadUrl} />}
                {artifact.kind === 'video' && <video controls src={downloadUrl} />}
                {artifact.kind === 'audio' && <audio controls src={downloadUrl} />}
                <div>
                  <strong>{artifact.title}</strong>
                  <span>{artifact.kind} / {artifact.mime_type ?? 'file'}</span>
                </div>
                <a className="secondary-button" href={downloadUrl} target="_blank" rel="noreferrer">
                  Open
                </a>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MediaJobInlineCard({ job }: { job: JobRecord }) {
  const progress = jobProgress(job);
  const step = typeof job.metadata.step === 'string' ? job.metadata.step : null;
  return (
    <div className="message-job-card">
      <div>
        <strong>{job.title}</strong>
        <span>{job.backend} / {job.job_type.replace('_', ' ')}</span>
      </div>
      <span className={`job-status ${job.status}`}>{job.status.replace('_', ' ')}</span>
      {(progress !== null || step) && (
        <div className="message-job-progress">
          {progress !== null && <progress max={100} value={progress} />}
          <span>{step ?? `${progress}% complete`}</span>
        </div>
      )}
    </div>
  );
}

function KnowledgeContextView({ metadata }: { metadata: Record<string, unknown> }) {
  const context = parseKnowledgeContext(metadata.knowledge_context);
  if (!context || !context.enabled || context.matches.length === 0) {
    return null;
  }

  return (
    <details className="knowledge-context-card">
      <summary>
        <span><BookOpen size={15} /> Sources ({context.matches.length})</span>
        {context.query && <small>{context.query}</small>}
      </summary>
      <div className="knowledge-source-list">
        {context.matches.slice(0, 8).map((match, index) => (
          <article className="knowledge-source-row" key={`${match.sourceId}-${index}`}>
            <div>
              <strong>{index + 1}. {match.sourceTitle}</strong>
              <span>{match.sourceKind}{typeof match.score === 'number' ? ` / score ${match.score.toFixed(2)}` : ''}</span>
            </div>
            <p>{match.snippet}</p>
            {(match.uri || match.path) && (
              match.uri?.startsWith('http') ? (
                <a href={match.uri} target="_blank" rel="noreferrer">{match.uri}</a>
              ) : (
                <code>{match.path ?? match.uri}</code>
              )
            )}
          </article>
        ))}
      </div>
    </details>
  );
}

function WorkspaceContextView({
  metadata,
  visible,
  filter,
  collapsed,
  onToggleCollapse,
}: {
  metadata: Record<string, unknown>;
  visible: boolean;
  filter: ContextFilter;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const context = parseWorkspaceContext(metadata.workspace_context);
  if (!visible || !context || !context.enabled) {
    return null;
  }

  const showInstructions = filter === 'all' || filter === 'instructions';
  const showIndex = filter === 'all' || filter === 'index';
  const showWarnings = filter === 'all' || filter === 'warnings';
  const hasAnyVisibleSection =
    context.focusPaths.length > 0 ||
    (showInstructions && context.instructionFiles.length > 0) ||
    (showIndex && context.indexMatches.length > 0) ||
    (showWarnings && context.warnings.length > 0);
  if (!hasAnyVisibleSection && filter !== 'all') {
    return null;
  }

  const visibleCount =
    context.focusPaths.length
    + (showInstructions ? context.instructionFiles.length : 0)
    + (showIndex ? context.indexMatches.length : 0)
    + (showWarnings ? context.warnings.length : 0);

  return (
    <div className="workspace-context-card" aria-label="Workspace context used for this response">
      <div className="workspace-context-header">
        <strong>Workspace Context ({visibleCount})</strong>
        {context.mode && <span>{context.mode}</span>}
        <button className="workspace-context-toggle" onClick={onToggleCollapse} type="button">
          {collapsed ? 'Expand' : 'Collapse'}
        </button>
      </div>
      {!collapsed && (
        <>
          {context.targetPath && <div className="workspace-context-line">Target: {context.targetPath}</div>}
          {context.focusPaths.length > 0 && (
            <div className="workspace-context-group">
              <span>Focus Files ({context.focusPaths.length})</span>
              <ul>
                {context.focusPaths.slice(0, 6).map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
            </div>
          )}
          {showInstructions && context.instructionFiles.length > 0 && (
            <div className="workspace-context-group">
              <span>Instructions ({context.instructionFiles.length})</span>
              <ul>
                {context.instructionFiles.slice(0, 5).map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
            </div>
          )}
          {showIndex && context.indexMatches.length > 0 && (
            <div className="workspace-context-group">
              <span>Index Matches ({context.indexMatches.length})</span>
              <ul>
                {context.indexMatches.slice(0, 5).map((match) => (
                  <li key={`${match.path}-${match.lineNumber ?? 0}`}>
                    {match.path}
                    {match.lineNumber ? `:${match.lineNumber}` : ''}
                    {typeof match.score === 'number' ? ` (score ${match.score.toFixed(2)})` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {showWarnings && context.warnings.length > 0 && (
            <div className="workspace-context-group warnings">
              <span>Warnings</span>
              <ul>
                {context.warnings.slice(0, 3).map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function WorkbenchView({
  activeView,
  artifacts,
  fanControls,
  groupedModels,
  isMediaBusy,
  isWorkspaceBusy,
  isKnowledgeBusy,
  knowledgeNotice,
  knowledgeSearchQuery,
  knowledgeSearchResults,
  knowledgeSources,
  knowledgeStatus,
  mediaJobs,
  mediaStatus,
  models,
  onCreateMediaJob,
  onOpenCompareConversation,
  onRefreshConversations,
  onIngestKnowledgeLocal,
  onIngestKnowledgePreset,
  onIngestKnowledgeText,
  onIngestKnowledgeUrl,
  onIngestKnowledgeWikipedia,
  onOpenWorkspaceEntry,
  onKnowledgeSearch,
  onRefreshKnowledge,
  onApplyWorkspacePatch,
  onPreviewWorkspacePatch,
  onRunWorkspaceCommand,
  onAddChatContextPath,
  onRefreshMedia,
  onRefreshSystem,
  onUpdateFanControl,
  onUseArtifactInChat,
  onRefreshWorkspace,
  onWorkspaceParent,
  onWorkspaceSearch,
  sessionState,
  status,
  workspaceCommandResult,
  workspaceEntries,
  workspaceDraftContent,
  workspaceFile,
  workspacePath,
  workspacePatchPreview,
  workspaceScan,
  workspaceSearchQuery,
  workspaceSearchResults,
  workspaceSummary,
  setKnowledgeSearchQuery,
  setWorkspaceDraftContent,
  setWorkspaceSearchQuery,
}: {
  activeView: ViewId;
  artifacts: ArtifactRecord[];
  fanControls: GPUFanControlSnapshot | null;
  groupedModels: { ready: ModelProfile[]; pending: ModelProfile[] };
  isMediaBusy: boolean;
  isWorkspaceBusy: boolean;
  isKnowledgeBusy: boolean;
  knowledgeNotice: string | null;
  knowledgeSearchQuery: string;
  knowledgeSearchResults: KnowledgeSearchMatch[];
  knowledgeSources: KnowledgeSourceRecord[];
  knowledgeStatus: KnowledgeStatus | null;
  mediaJobs: JobRecord[];
  mediaStatus: MediaSystemStatus | null;
  models: ModelProfile[];
  onCreateMediaJob: (jobType: JobType, title: string, prompt: string) => Promise<void>;
  onOpenCompareConversation: (conversationId: string) => Promise<void>;
  onRefreshConversations: () => Promise<void>;
  onIngestKnowledgeLocal: (payload: { path: string; glob: string; max_files: number }) => Promise<void>;
  onIngestKnowledgePreset: (preset: 'coding-core' | 'ai-foundations') => Promise<void>;
  onIngestKnowledgeText: (payload: { title: string; text: string; uri?: string }) => Promise<void>;
  onIngestKnowledgeUrl: (payload: { url: string; title?: string }) => Promise<void>;
  onIngestKnowledgeWikipedia: (payload: { title: string; language?: string }) => Promise<void>;
  onKnowledgeSearch: (event?: FormEvent<HTMLFormElement>) => Promise<void>;
  onOpenWorkspaceEntry: (entry: WorkspaceEntry) => Promise<void>;
  onRefreshKnowledge: () => Promise<void>;
  onApplyWorkspacePatch: () => Promise<void>;
  onPreviewWorkspacePatch: () => Promise<void>;
  onRunWorkspaceCommand: (command: WorkspaceCommand) => Promise<void>;
  onAddChatContextPath: (path: string) => void;
  onRefreshMedia: () => Promise<void>;
  onRefreshSystem: () => Promise<void>;
  onUpdateFanControl: (gpuIndex: number, mode: GPUFanMode, manualSpeed: number) => Promise<void>;
  onUseArtifactInChat: (artifact: ArtifactRecord) => void;
  onRefreshWorkspace: () => Promise<void>;
  onWorkspaceParent: () => Promise<void>;
  onWorkspaceSearch: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  sessionState: SessionStateRecord | null;
  status: SystemStatus | null;
  workspaceCommandResult: WorkspaceCommandRunResult | null;
  workspaceEntries: WorkspaceEntry[];
  workspaceDraftContent: string;
  workspaceFile: WorkspaceFile | null;
  workspacePath: string;
  workspacePatchPreview: WorkspacePatchPreview | null;
  workspaceScan: WorkspaceScan | null;
  workspaceSearchQuery: string;
  workspaceSearchResults: WorkspaceSearchMatch[];
  workspaceSummary: WorkspaceSummary | null;
  setKnowledgeSearchQuery: (value: string) => void;
  setWorkspaceDraftContent: (value: string) => void;
  setWorkspaceSearchQuery: (value: string) => void;
}) {
  if (activeView === 'agent') {
    return <FeatureView icon={Waypoints} title="Agent Workspace" items={agentItems()} />;
  }
  if (activeView === 'compare') {
    return (
      <CompareView
        models={models}
        onOpenConversation={onOpenCompareConversation}
        onRefreshConversations={onRefreshConversations}
      />
    );
  }
  if (activeView === 'code') {
    return (
      <CodeWorkspaceView
        commandResult={workspaceCommandResult}
        entries={workspaceEntries}
        draftContent={workspaceDraftContent}
        file={workspaceFile}
        isBusy={isWorkspaceBusy}
        onApplyPatch={onApplyWorkspacePatch}
        onOpenEntry={onOpenWorkspaceEntry}
        onParent={onWorkspaceParent}
        onPreviewPatch={onPreviewWorkspacePatch}
        onRefresh={onRefreshWorkspace}
        onRunCommand={onRunWorkspaceCommand}
        onAddChatContextPath={onAddChatContextPath}
        onSearch={onWorkspaceSearch}
        path={workspacePath}
        patchPreview={workspacePatchPreview}
        scan={workspaceScan}
        searchQuery={workspaceSearchQuery}
        searchResults={workspaceSearchResults}
        setSearchQuery={setWorkspaceSearchQuery}
        setDraftContent={setWorkspaceDraftContent}
        summary={workspaceSummary}
      />
    );
  }
  if (activeView === 'media') {
    return (
      <MediaView
        artifacts={artifacts}
        isMediaBusy={isMediaBusy}
        jobs={mediaJobs}
        mediaStatus={mediaStatus}
        onCreateJob={onCreateMediaJob}
        onRefresh={onRefreshMedia}
        onUseArtifactInChat={onUseArtifactInChat}
      />
    );
  }
  if (activeView === 'memory') {
    return (
      <MemoryView
        isBusy={isKnowledgeBusy}
        notice={knowledgeNotice}
        onIngestLocal={onIngestKnowledgeLocal}
        onIngestPreset={onIngestKnowledgePreset}
        onIngestText={onIngestKnowledgeText}
        onIngestUrl={onIngestKnowledgeUrl}
        onIngestWikipedia={onIngestKnowledgeWikipedia}
        onRefresh={onRefreshKnowledge}
        onSearch={onKnowledgeSearch}
        searchQuery={knowledgeSearchQuery}
        searchResults={knowledgeSearchResults}
        setSearchQuery={setKnowledgeSearchQuery}
        sources={knowledgeSources}
        status={knowledgeStatus}
      />
    );
  }
  if (activeView === 'system') {
    return (
      <SystemView
        fanControls={fanControls}
        groupedModels={groupedModels}
        models={models}
        onRefresh={onRefreshSystem}
        onUpdateFanControl={onUpdateFanControl}
        status={status}
      />
    );
  }
  return <SettingsView sessionState={sessionState} status={status} />;
}

function FeatureView({ icon: Icon, title, items }: { icon: IconType; title: string; items: Array<[string, string]> }) {
  return (
    <section className="workbench-view" aria-label={title}>
      <div className="view-heading">
        <Icon size={26} />
        <h3>{title}</h3>
      </div>
      <div className="feature-grid">
        {items.map(([heading, body]) => (
          <article className="feature-card" key={heading}>
            <strong>{heading}</strong>
            <p>{body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function CompareView({
  models,
  onOpenConversation,
  onRefreshConversations,
}: {
  models: ModelProfile[];
  onOpenConversation: (conversationId: string) => Promise<void>;
  onRefreshConversations: () => Promise<void>;
}) {
  const chatModels = useMemo(
    () => models.filter((model) => model.capabilities.includes('chat')),
    [models],
  );
  const readyChatModels = useMemo(
    () => chatModels.filter((model) => model.status === 'ready'),
    [chatModels],
  );
  const [selectedModelIds, setSelectedModelIds] = useState<string[]>([]);
  const [prompt, setPrompt] = useState('');
  const [blindMode, setBlindMode] = useState(false);
  const [includeKnowledge, setIncludeKnowledge] = useState(true);
  const [runs, setRuns] = useState<CompareRun[]>([]);
  const [synthesisRun, setSynthesisRun] = useState<CompareRun | null>(null);
  const [isComparing, setIsComparing] = useState(false);
  const [isSynthesizing, setIsSynthesizing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  useEffect(() => {
    if (selectedModelIds.length > 0 || readyChatModels.length === 0) {
      return;
    }
    setSelectedModelIds(readyChatModels.slice(0, 4).map((model) => model.id));
  }, [readyChatModels, selectedModelIds.length]);

  function toggleModel(modelId: string) {
    setSelectedModelIds((current) => {
      if (current.includes(modelId)) {
        return current.filter((id) => id !== modelId);
      }
      return [...current, modelId].slice(0, 8);
    });
  }

  async function runCompare() {
    const content = prompt.trim();
    const selectedModels = selectedModelIds
      .map((modelId) => readyChatModels.find((model) => model.id === modelId))
      .filter((model): model is ModelProfile => Boolean(model));
    if (isComparing) {
      return;
    }
    if (!content) {
      setCompareError('Enter a prompt to compare.');
      return;
    }
    if (selectedModels.length === 0) {
      setCompareError('Select at least one ready chat model.');
      return;
    }

    const startedAt = Date.now();
    setCompareError(null);
    setIsComparing(true);
    setSynthesisRun(null);
    setRuns(selectedModels.map((model) => ({
      id: `${model.id}-${startedAt}`,
      modelId: model.id,
      displayName: model.display_name,
      status: 'streaming',
      content: '',
      startedAt,
    })));

    try {
      await Promise.all(selectedModels.map(async (model) => {
        let streamedContent = '';
        try {
          const response = await edisonApi.streamChatTurn({
            conversation_id: null,
            message: content,
            mode: 'chat',
            preferred_model: model.id,
            memory_enabled: true,
            include_workspace_context: false,
            include_knowledge_context: includeKnowledge,
            max_knowledge_context_matches: includeKnowledge ? 5 : 1,
          }, {
            onStart: (event) => {
              setRuns((current) => current.map((run) => (
                run.modelId === model.id ? { ...run, conversationId: event.conversation_id } : run
              )));
            },
            onToken: (delta) => {
              streamedContent += delta;
              setRuns((current) => current.map((run) => (
                run.modelId === model.id ? { ...run, content: streamedContent } : run
              )));
            },
            onError: (detail) => {
              setRuns((current) => current.map((run) => (
                run.modelId === model.id ? { ...run, status: 'error', error: detail, finishedAt: Date.now() } : run
              )));
            },
          });
          setRuns((current) => current.map((run) => (
            run.modelId === model.id
              ? {
                  ...run,
                  status: response.inference.finish_reason === 'error' ? 'error' : 'done',
                  content: response.assistant_message.content,
                  conversationId: response.conversation.id,
                  error: response.inference.finish_reason === 'error' ? response.inference.content : undefined,
                  finishedAt: Date.now(),
                }
              : run
          )));
        } catch (caught) {
          setRuns((current) => current.map((run) => (
            run.modelId === model.id
              ? {
                  ...run,
                  status: 'error',
                  error: caught instanceof Error ? caught.message : 'Compare run failed',
                  finishedAt: Date.now(),
                }
              : run
          )));
        }
      }));
      await onRefreshConversations();
    } catch (caught) {
      setCompareError(caught instanceof Error ? caught.message : 'Compare refresh failed');
    } finally {
      setIsComparing(false);
    }
  }

  async function runSynthesis() {
    const completedRuns = runs.filter((run) => run.status === 'done' && run.content.trim());
    const synthesisModel = readyChatModels.find((model) => selectedModelIds.includes(model.id)) ?? readyChatModels[0];
    if (isSynthesizing) {
      return;
    }
    if (completedRuns.length < 2) {
      setCompareError('Run at least two successful model responses before synthesizing.');
      return;
    }
    if (!synthesisModel) {
      setCompareError('No ready chat model is available for synthesis.');
      return;
    }

    const startedAt = Date.now();
    const synthesisId = `synthesis-${startedAt}`;
    const synthesisPrompt = [
      'You are Edison reviewing a side-by-side AI model comparison.',
      'Produce a concise decision report with: winner, why, notable misses, best use case for each answer, and a final merged answer when useful.',
      `Original prompt:\n${prompt.trim()}`,
      'Model responses:',
      completedRuns.map((run, index) => {
        const label = blindMode ? `Model ${index + 1}` : `${run.displayName} (${run.modelId})`;
        return `### ${label}\n${run.content.trim()}`;
      }).join('\n\n'),
    ].join('\n\n');

    let streamedContent = '';
    setCompareError(null);
    setIsSynthesizing(true);
    setSynthesisRun({
      id: synthesisId,
      modelId: synthesisModel.id,
      displayName: 'Synthesis',
      status: 'streaming',
      content: '',
      startedAt,
    });

    try {
      const response = await edisonApi.streamChatTurn({
        conversation_id: null,
        message: synthesisPrompt,
        mode: 'reasoning',
        preferred_model: synthesisModel.id,
        memory_enabled: true,
        include_workspace_context: false,
        include_knowledge_context: false,
        max_knowledge_context_matches: 1,
      }, {
        onStart: (event) => {
          setSynthesisRun((current) => (
            current?.id === synthesisId ? { ...current, conversationId: event.conversation_id } : current
          ));
        },
        onToken: (delta) => {
          streamedContent += delta;
          setSynthesisRun((current) => (
            current?.id === synthesisId ? { ...current, content: streamedContent } : current
          ));
        },
        onError: (detail) => {
          setSynthesisRun((current) => (
            current?.id === synthesisId ? { ...current, status: 'error', error: detail, finishedAt: Date.now() } : current
          ));
        },
      });
      setSynthesisRun((current) => (
        current?.id === synthesisId
          ? {
              ...current,
              status: response.inference.finish_reason === 'error' ? 'error' : 'done',
              content: response.assistant_message.content,
              conversationId: response.conversation.id,
              error: response.inference.finish_reason === 'error' ? response.inference.content : undefined,
              finishedAt: Date.now(),
            }
          : current
      ));
      await onRefreshConversations();
    } catch (caught) {
      setSynthesisRun((current) => (
        current?.id === synthesisId
          ? {
              ...current,
              status: 'error',
              error: caught instanceof Error ? caught.message : 'Synthesis failed',
              finishedAt: Date.now(),
            }
          : current
      ));
    } finally {
      setIsSynthesizing(false);
    }
  }

  const selectedCount = selectedModelIds.filter((modelId) => readyChatModels.some((model) => model.id === modelId)).length;
  const canSynthesize = runs.filter((run) => run.status === 'done' && run.content.trim()).length >= 2
    && !isComparing
    && !isSynthesizing;

  return (
    <section className="workbench-view compare-view" aria-label="Model Compare">
      <div className="view-heading">
        <Network size={26} />
        <h3>Compare</h3>
        <div className="view-actions">
          <button
            className="secondary-button icon-text-button"
            disabled={!canSynthesize}
            onClick={() => void runSynthesis()}
            type="button"
          >
            <Sparkles size={16} />
            {isSynthesizing ? 'Synthesizing' : 'Synthesize'}
          </button>
          <button
            className="secondary-button icon-text-button"
            disabled={!prompt.trim() || selectedCount === 0 || isComparing}
            onClick={() => void runCompare()}
            type="button"
          >
            <Send size={16} />
            {isComparing ? 'Running' : 'Run Compare'}
          </button>
        </div>
      </div>

      <div className="compare-shell">
        <aside className="compare-control-panel" aria-label="Compare controls">
          <label htmlFor="compare-prompt">Prompt</label>
          <textarea
            id="compare-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Ask every selected model the same question"
            rows={7}
          />
          <div className="compare-toggle-row">
            <label>
              <input
                type="checkbox"
                checked={blindMode}
                onChange={(event) => setBlindMode(event.target.checked)}
              />
              Blind labels
            </label>
            <label>
              <input
                type="checkbox"
                checked={includeKnowledge}
                onChange={(event) => setIncludeKnowledge(event.target.checked)}
              />
              Use RAG
            </label>
          </div>
          <div className="compare-model-list" aria-label="Models to compare">
            {chatModels.map((model) => {
              const isSelected = selectedModelIds.includes(model.id);
              return (
                <button
                  className={isSelected ? 'compare-model-row active' : 'compare-model-row'}
                  disabled={model.status !== 'ready'}
                  key={model.id}
                  onClick={() => toggleModel(model.id)}
                  type="button"
                >
                  <span>{model.display_name}</span>
                  <small>{model.status.replace('_', ' ')} / {model.provider}</small>
                </button>
              );
            })}
            {chatModels.length === 0 && <div className="empty-line">No chat-capable models registered.</div>}
          </div>
          {compareError && <div className="error-banner compact">{compareError}</div>}
        </aside>

        <section className="compare-results-panel" aria-label="Compare results">
          {runs.length === 0 ? (
            <div className="compare-empty">
              <Network size={30} />
              <strong>Send one prompt to multiple model lanes.</strong>
              <span>Results stream side-by-side so you can judge quality, latency, and citation behavior.</span>
            </div>
          ) : (
            <>
              {synthesisRun && (
                <article className="compare-synthesis-card">
                  <div className="compare-result-header">
                    <div>
                      <strong>Compare synthesis</strong>
                      <span>{synthesisRun.modelId}</span>
                    </div>
                    <small className={`compare-status ${synthesisRun.status}`}>{synthesisRun.status}</small>
                  </div>
                  <div className="compare-result-body">
                    {synthesisRun.content ? (
                      <MessageContent content={synthesisRun.content} metadata={{}} />
                    ) : synthesisRun.status === 'streaming' ? (
                      <div className="typing-indicator" aria-label="Synthesis is streaming">
                        <span />
                        <span />
                        <span />
                      </div>
                    ) : (
                      <p>{synthesisRun.error ?? 'No synthesis content.'}</p>
                    )}
                    {synthesisRun.error && <div className="compare-run-error">{synthesisRun.error}</div>}
                  </div>
                  <div className="compare-result-footer">
                    <span>{formatCompareDuration(synthesisRun)}</span>
                    {synthesisRun.conversationId && (
                      <button
                        className="secondary-button"
                        onClick={() => void onOpenConversation(synthesisRun.conversationId ?? '')}
                        type="button"
                      >
                        Open Chat
                      </button>
                    )}
                  </div>
                </article>
              )}
              <div className="compare-result-grid">
                {runs.map((run, index) => (
                  <article className="compare-result-card" key={run.id}>
                    <div className="compare-result-header">
                      <div>
                        <strong>{blindMode ? `Model ${index + 1}` : run.displayName}</strong>
                        {!blindMode && <span>{run.modelId}</span>}
                      </div>
                      <small className={`compare-status ${run.status}`}>{run.status}</small>
                    </div>
                    <div className="compare-result-body">
                      {run.content ? (
                        <MessageContent content={run.content} metadata={{}} />
                      ) : run.status === 'streaming' ? (
                        <div className="typing-indicator" aria-label="Model is responding">
                          <span />
                          <span />
                          <span />
                        </div>
                      ) : (
                        <p>{run.error ?? 'No response content.'}</p>
                      )}
                      {run.error && <div className="compare-run-error">{run.error}</div>}
                    </div>
                    <div className="compare-result-footer">
                      <span>{formatCompareDuration(run)}</span>
                      {run.conversationId && (
                        <button
                          className="secondary-button"
                          onClick={() => void onOpenConversation(run.conversationId ?? '')}
                          type="button"
                        >
                          Open Chat
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </section>
  );
}

function CodeWorkspaceView({
  commandResult,
  entries,
  draftContent,
  file,
  isBusy,
  onApplyPatch,
  onOpenEntry,
  onParent,
  onPreviewPatch,
  onRefresh,
  onRunCommand,
  onAddChatContextPath,
  onSearch,
  path,
  patchPreview,
  scan,
  searchQuery,
  searchResults,
  setSearchQuery,
  setDraftContent,
  summary,
}: {
  commandResult: WorkspaceCommandRunResult | null;
  entries: WorkspaceEntry[];
  draftContent: string;
  file: WorkspaceFile | null;
  isBusy: boolean;
  onApplyPatch: () => Promise<void>;
  onOpenEntry: (entry: WorkspaceEntry) => Promise<void>;
  onParent: () => Promise<void>;
  onPreviewPatch: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onRunCommand: (command: WorkspaceCommand) => Promise<void>;
  onAddChatContextPath: (path: string) => void;
  onSearch: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  path: string;
  patchPreview: WorkspacePatchPreview | null;
  scan: WorkspaceScan | null;
  searchQuery: string;
  searchResults: WorkspaceSearchMatch[];
  setSearchQuery: (value: string) => void;
  setDraftContent: (value: string) => void;
  summary: WorkspaceSummary | null;
}) {
  const topLanguages = Object.entries(summary?.languages ?? {}).slice(0, 3);
  const commandPreview = scan?.commands.slice(0, 6) ?? [];
  const entrypointPreview = scan?.entrypoints.slice(0, 5) ?? [];
  const configPreview = scan?.config_files.slice(0, 6) ?? [];
  const draftChanged = Boolean(file && draftContent !== file.content);

  return (
    <section className="workbench-view code-view" aria-label="Code Space">
      <div className="view-heading">
        <Code2 size={26} />
        <h3>Code Space</h3>
        <button className="secondary-button icon-text-button" disabled={isBusy} onClick={() => void onRefresh()} type="button">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <div className="code-overview-row">
        <article className="workspace-metric-card">
          <strong>{summary?.file_count ?? 0}</strong>
          <span>Files</span>
        </article>
        <article className="workspace-metric-card">
          <strong>{summary?.directory_count ?? 0}</strong>
          <span>Folders</span>
        </article>
        <article className="workspace-metric-card wide">
          <strong>{scan?.stacks.join(' / ') || summary?.package_managers.join(' / ') || 'No package marker'}</strong>
          <span>Stack</span>
        </article>
        <article className="workspace-metric-card wide">
          <strong>{topLanguages.map(([name]) => name).join(' / ') || 'No language scan'}</strong>
          <span>Languages</span>
        </article>
      </div>

      <div className="repo-intelligence-grid">
        <article className="intelligence-card">
          <div className="section-heading">
            <FileCode2 size={18} />
            <h3>Entry Points</h3>
          </div>
          <div className="intelligence-list">
            {entrypointPreview.map((entrypoint) => (
              <div className="intelligence-row" key={entrypoint.path}>
                <strong>{entrypoint.kind}</strong>
                <span>{entrypoint.path}</span>
              </div>
            ))}
            {entrypointPreview.length === 0 && <div className="empty-line">No entrypoints</div>}
          </div>
        </article>
        <article className="intelligence-card">
          <div className="section-heading">
            <Activity size={18} />
            <h3>Commands</h3>
          </div>
          <div className="intelligence-list">
            {commandPreview.map((command) => (
              <div className="command-row" key={`${command.cwd}-${command.command}`}>
                <div>
                  <strong>{command.name}</strong>
                  <span>{command.cwd}</span>
                  <code>{command.command}</code>
                </div>
                <button className="secondary-button" disabled={isBusy} onClick={() => void onRunCommand(command)} type="button">
                  Run approved
                </button>
              </div>
            ))}
            {commandPreview.length === 0 && <div className="empty-line">No commands</div>}
          </div>
        </article>
        <article className="intelligence-card">
          <div className="section-heading">
            <Settings size={18} />
            <h3>Config</h3>
          </div>
          <div className="chip-list">
            {configPreview.map((configPath) => <span key={configPath}>{configPath}</span>)}
            {configPreview.length === 0 && <div className="empty-line">No config files</div>}
          </div>
        </article>
        <article className="intelligence-card">
          <div className="section-heading">
            <Waypoints size={18} />
            <h3>Agent Queue</h3>
          </div>
          <div className="intelligence-list">
            {(scan?.next_steps ?? []).slice(0, 4).map((step) => (
              <div className="intelligence-row" key={step}>
                <strong>{step}</strong>
              </div>
            ))}
            {!scan?.next_steps.length && <div className="empty-line">No queued capabilities</div>}
          </div>
        </article>
      </div>

      {commandResult && (
        <section className="command-output-panel" aria-label="Command result">
          <div className="command-output-header">
            <div>
              <span className="section-label">Command Result</span>
              <strong>{commandResult.command}</strong>
              <span>{commandResult.cwd} / {commandResult.duration_ms} ms / exit {commandResult.exit_code ?? 'timeout'}</span>
            </div>
            <small className={`job-status ${commandResult.job.status}`}>{commandResult.job.status.replace('_', ' ')}</small>
          </div>
          <div className="command-output-grid">
            <div>
              <span className="section-label">stdout</span>
              <pre><code>{commandResult.stdout || 'No output'}</code></pre>
            </div>
            <div>
              <span className="section-label">stderr</span>
              <pre><code>{commandResult.stderr || 'No errors'}</code></pre>
            </div>
          </div>
        </section>
      )}

      <div className="code-workspace-grid">
        <aside className="code-browser-panel" aria-label="Workspace files">
          <div className="code-browser-header">
            <div>
              <span className="section-label">Folder</span>
              <strong>{path || summary?.root_name || 'workspace'}</strong>
            </div>
            <button className="icon-button" disabled={!path || isBusy} onClick={() => void onParent()} title="Up one folder" type="button">
              <ChevronUp size={18} />
            </button>
          </div>
          <div className="file-list">
            {entries.map((entry) => {
              const Icon = entry.kind === 'directory' ? Folder : FileCode2;
              return (
                <button className="file-entry" key={entry.path} onClick={() => void onOpenEntry(entry)} type="button">
                  <Icon size={17} />
                  <div>
                    <strong>{entry.name}</strong>
                    <span>{entry.kind === 'directory' ? 'Folder' : entry.language ?? formatBytes(entry.size_bytes)}</span>
                  </div>
                </button>
              );
            })}
            {entries.length === 0 && <div className="empty-line">No files</div>}
          </div>
        </aside>

        <article className="code-preview-panel" aria-label="File preview">
          {file ? (
            <>
              <div className="code-preview-header">
                <div>
                  <strong>{file.path}</strong>
                  <span>{file.language ?? 'Text'} / {formatBytes(file.size_bytes)}{file.truncated ? ' / truncated' : ''}</span>
                </div>
                <div className="patch-action-row">
                  <button
                    className="secondary-button"
                    onClick={() => onAddChatContextPath(file.path)}
                    type="button"
                  >
                    Add To Chat Focus
                  </button>
                  <button
                    className="secondary-button"
                    disabled={!draftChanged || isBusy}
                    onClick={() => void onPreviewPatch()}
                    type="button"
                  >
                    Preview diff
                  </button>
                  <button
                    className="apply-button"
                    disabled={!patchPreview || !draftChanged || isBusy}
                    onClick={() => void onApplyPatch()}
                    type="button"
                  >
                    Apply reviewed patch
                  </button>
                </div>
              </div>
              <textarea
                aria-label={`Edit ${file.path}`}
                className="code-editor"
                onChange={(event) => setDraftContent(event.target.value)}
                spellCheck={false}
                value={draftContent}
              />
            </>
          ) : (
            <div className="empty-preview">
              <FileCode2 size={30} />
              <strong>{summary?.root_path ?? 'Workspace not loaded'}</strong>
            </div>
          )}
        </article>
      </div>

      {patchPreview && (
        <section className="diff-review-panel" aria-label="Patch review">
          <div className="diff-review-header">
            <div>
              <span className="section-label">Patch Review</span>
              <strong>{patchPreview.path}</strong>
            </div>
            <div className="diff-stats">
              <span>+{patchPreview.additions}</span>
              <span>-{patchPreview.deletions}</span>
            </div>
          </div>
          {patchPreview.risk_flags.length > 0 && (
            <div className="risk-list">
              {patchPreview.risk_flags.map((flag) => <span key={flag}>{flag.replace(/_/g, ' ')}</span>)}
            </div>
          )}
          <pre className="diff-preview"><code>{patchPreview.diff || 'No changes'}</code></pre>
        </section>
      )}

      <section className="workspace-search-panel" aria-label="Workspace search">
        <form className="workspace-search-form" onSubmit={(event) => void onSearch(event)}>
          <input
            aria-label="Search workspace"
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search files and code"
            value={searchQuery}
          />
          <button className="secondary-button icon-text-button" disabled={!searchQuery.trim() || isBusy} type="submit">
            <Search size={16} />
            Search
          </button>
        </form>
        <div className="search-results">
          {searchResults.slice(0, 12).map((result) => (
            <button
              className="search-result-row"
              key={`${result.path}-${result.line_number ?? 'file'}`}
              onClick={() => {
                onAddChatContextPath(result.path);
                void onOpenEntry({ path: result.path, name: result.name, kind: 'file', language: result.language });
              }}
              type="button"
            >
              <FileCode2 size={16} />
              <div>
                <strong>{result.path}{result.line_number ? `:${result.line_number}` : ''}</strong>
                <span>{result.line_text ?? result.language ?? 'File match'}</span>
              </div>
            </button>
          ))}
          {searchQuery && searchResults.length === 0 && <div className="empty-line">No matches</div>}
        </div>
      </section>
    </section>
  );
}

function MemoryView({
  isBusy,
  notice,
  onIngestLocal,
  onIngestPreset,
  onIngestText,
  onIngestUrl,
  onIngestWikipedia,
  onRefresh,
  onSearch,
  searchQuery,
  searchResults,
  setSearchQuery,
  sources,
  status,
}: {
  isBusy: boolean;
  notice: string | null;
  onIngestLocal: (payload: { path: string; glob: string; max_files: number }) => Promise<void>;
  onIngestPreset: (preset: 'coding-core' | 'ai-foundations') => Promise<void>;
  onIngestText: (payload: { title: string; text: string; uri?: string }) => Promise<void>;
  onIngestUrl: (payload: { url: string; title?: string }) => Promise<void>;
  onIngestWikipedia: (payload: { title: string; language?: string }) => Promise<void>;
  onRefresh: () => Promise<void>;
  onSearch: (event?: FormEvent<HTMLFormElement>) => Promise<void>;
  searchQuery: string;
  searchResults: KnowledgeSearchMatch[];
  setSearchQuery: (value: string) => void;
  sources: KnowledgeSourceRecord[];
  status: KnowledgeStatus | null;
}) {
  const [url, setUrl] = useState('');
  const [urlTitle, setUrlTitle] = useState('');
  const [wikiTitle, setWikiTitle] = useState('');
  const [wikiLanguage, setWikiLanguage] = useState('en');
  const [localPath, setLocalPath] = useState('.');
  const [localGlob, setLocalGlob] = useState('**/*.md');
  const [localMaxFiles, setLocalMaxFiles] = useState(200);
  const [textTitle, setTextTitle] = useState('');
  const [textUri, setTextUri] = useState('');
  const [textBody, setTextBody] = useState('');

  return (
    <section className="workbench-view memory-view" aria-label="Memory Center">
      <div className="view-heading">
        <Brain size={26} />
        <h3>Memory Center</h3>
        <button className="secondary-button icon-text-button" disabled={isBusy} onClick={() => void onRefresh()} type="button">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <div className="memory-metric-row">
        <article className="workspace-metric-card">
          <strong>{status?.source_count ?? 0}</strong>
          <span>Sources</span>
        </article>
        <article className="workspace-metric-card">
          <strong>{status?.chunk_count ?? 0}</strong>
          <span>Chunks</span>
        </article>
        <article className="workspace-metric-card wide">
          <strong>{status?.latest_ingest_at ? formatDateTime(status.latest_ingest_at) : 'No imports yet'}</strong>
          <span>Latest Import</span>
        </article>
        <article className="workspace-metric-card wide">
          <strong>{status?.service ?? 'knowledge-base'}</strong>
          <span>Retrieval Service</span>
        </article>
      </div>

      {notice && <div className="memory-notice">{notice}</div>}

      <div className="memory-grid">
        <section className="memory-panel search-panel" aria-label="Search knowledge">
          <div className="section-heading">
            <Search size={18} />
            <h3>Search RAG</h3>
          </div>
          <form className="memory-search-form" onSubmit={(event) => void onSearch(event)}>
            <input
              aria-label="Search knowledge base"
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search knowledge sources"
              value={searchQuery}
            />
            <button className="secondary-button icon-text-button" disabled={!searchQuery.trim() || isBusy} type="submit">
              <Search size={16} />
              Search
            </button>
          </form>
          <div className="knowledge-results">
            {searchResults.map((result, index) => (
              <article className="knowledge-result" key={`${result.source_id}-${index}`}>
                <div>
                  <strong>{result.source_title}</strong>
                  <span>{result.source_kind} / score {result.score.toFixed(2)}</span>
                </div>
                <p>{result.snippet}</p>
                {(result.uri || result.path) && (
                  result.uri?.startsWith('http') ? (
                    <a href={result.uri} target="_blank" rel="noreferrer">{result.uri}</a>
                  ) : (
                    <code>{result.path ?? result.uri}</code>
                  )
                )}
              </article>
            ))}
            {searchQuery && searchResults.length === 0 && <div className="empty-line">No knowledge matches</div>}
          </div>
        </section>

        <section className="memory-panel import-panel" aria-label="Import knowledge">
          <div className="section-heading">
            <Upload size={18} />
            <h3>Import Sources</h3>
          </div>

          <form
            className="memory-import-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (!url.trim()) {
                return;
              }
              void onIngestUrl({ url: url.trim(), title: urlTitle.trim() || undefined }).then(() => {
                setUrl('');
                setUrlTitle('');
              });
            }}
          >
            <label htmlFor="knowledge-url">URL</label>
            <input id="knowledge-url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/doc" />
            <input value={urlTitle} onChange={(event) => setUrlTitle(event.target.value)} placeholder="Optional title" />
            <button className="secondary-button icon-text-button" disabled={!url.trim() || isBusy} type="submit">
              <Link2 size={16} />
              Import URL
            </button>
          </form>

          <form
            className="memory-import-form two-column"
            onSubmit={(event) => {
              event.preventDefault();
              if (!wikiTitle.trim()) {
                return;
              }
              void onIngestWikipedia({ title: wikiTitle.trim(), language: wikiLanguage.trim() || 'en' }).then(() => {
                setWikiTitle('');
              });
            }}
          >
            <label htmlFor="knowledge-wiki">Wikipedia</label>
            <input id="knowledge-wiki" value={wikiTitle} onChange={(event) => setWikiTitle(event.target.value)} placeholder="Large language model" />
            <input value={wikiLanguage} onChange={(event) => setWikiLanguage(event.target.value)} placeholder="en" />
            <button className="secondary-button icon-text-button" disabled={!wikiTitle.trim() || isBusy} type="submit">
              <Globe2 size={16} />
              Import Wiki
            </button>
          </form>

          <form
            className="memory-import-form two-column"
            onSubmit={(event) => {
              event.preventDefault();
              if (!localPath.trim()) {
                return;
              }
              void onIngestLocal({ path: localPath.trim(), glob: localGlob.trim() || '**/*', max_files: localMaxFiles });
            }}
          >
            <label htmlFor="knowledge-local">Local Files</label>
            <input id="knowledge-local" value={localPath} onChange={(event) => setLocalPath(event.target.value)} placeholder="docs" />
            <input value={localGlob} onChange={(event) => setLocalGlob(event.target.value)} placeholder="**/*.md" />
            <input
              aria-label="Maximum local files"
              min={1}
              max={2000}
              type="number"
              value={localMaxFiles}
              onChange={(event) => {
                const parsed = Number.parseInt(event.target.value, 10);
                if (!Number.isNaN(parsed)) {
                  setLocalMaxFiles(Math.max(1, Math.min(2000, parsed)));
                }
              }}
            />
            <button className="secondary-button icon-text-button" disabled={!localPath.trim() || isBusy} type="submit">
              <Folder size={16} />
              Index Files
            </button>
          </form>

          <form
            className="memory-import-form text-import"
            onSubmit={(event) => {
              event.preventDefault();
              if (!textTitle.trim() || !textBody.trim()) {
                return;
              }
              void onIngestText({ title: textTitle.trim(), text: textBody, uri: textUri.trim() || undefined }).then(() => {
                setTextTitle('');
                setTextUri('');
                setTextBody('');
              });
            }}
          >
            <label htmlFor="knowledge-text-title">Text Note</label>
            <input id="knowledge-text-title" value={textTitle} onChange={(event) => setTextTitle(event.target.value)} placeholder="Source title" />
            <input value={textUri} onChange={(event) => setTextUri(event.target.value)} placeholder="Optional URI" />
            <textarea value={textBody} onChange={(event) => setTextBody(event.target.value)} placeholder="Paste notes, docs, or reference text" rows={5} />
            <button className="secondary-button icon-text-button" disabled={!textTitle.trim() || !textBody.trim() || isBusy} type="submit">
              <FileText size={16} />
              Save Text
            </button>
          </form>

          <div className="preset-row">
            <button className="secondary-button" disabled={isBusy} onClick={() => void onIngestPreset('ai-foundations')} type="button">
              AI Foundations
            </button>
            <button className="secondary-button" disabled={isBusy} onClick={() => void onIngestPreset('coding-core')} type="button">
              Coding Core
            </button>
          </div>
        </section>
      </div>

      <section className="memory-panel source-library" aria-label="Knowledge source library">
        <div className="section-heading">
          <Database size={18} />
          <h3>Source Library</h3>
        </div>
        <div className="source-table">
          {sources.map((source) => (
            <article className="source-row" key={source.id}>
              <div>
                <strong>{source.title}</strong>
                <span>{source.kind} / {source.chunk_count} chunks / {formatDateTime(source.updated_at)}</span>
              </div>
              {(source.uri || typeof source.metadata.path === 'string') && (
                <code>{source.uri ?? String(source.metadata.path)}</code>
              )}
            </article>
          ))}
          {sources.length === 0 && <div className="empty-line">No sources imported yet</div>}
        </div>
      </section>
    </section>
  );
}

function MediaView({
  artifacts,
  isMediaBusy,
  jobs,
  mediaStatus,
  onCreateJob,
  onRefresh,
  onUseArtifactInChat,
}: {
  artifacts: ArtifactRecord[];
  isMediaBusy: boolean;
  jobs: JobRecord[];
  mediaStatus: MediaSystemStatus | null;
  onCreateJob: (jobType: JobType, title: string, prompt: string) => Promise<void>;
  onRefresh: () => Promise<void>;
  onUseArtifactInChat: (artifact: ArtifactRecord) => void;
}) {
  const backendCards = [
    {
      label: 'ComfyUI',
      status: mediaStatus?.comfyui.status ?? 'offline',
      detail: mediaStatus?.comfyui.detail ?? 'Media backend status has not loaded yet.',
      meta: mediaStatus?.comfyui.base_url ?? 'No backend URL',
    },
    {
      label: 'InvokeAI',
      status: mediaStatus?.invokeai.status ?? 'offline',
      detail: mediaStatus?.invokeai.detail ?? 'InvokeAI has not been checked yet.',
      meta: mediaStatus?.invokeai.base_url ?? 'No backend URL',
    },
    {
      label: 'WAN 2.2',
      status: mediaStatus?.wan22.status ?? 'offline',
      detail: mediaStatus?.wan22.detail ?? 'WAN 2.2 has not been checked yet.',
      meta: mediaStatus?.wan22.base_url ?? 'No backend URL',
    },
    {
      label: 'Modly',
      status: mediaStatus?.modly.status ?? 'offline',
      detail: mediaStatus?.modly.detail ?? 'Modly has not been checked yet.',
      meta: mediaStatus?.modly.base_url ?? 'No backend URL',
    },
  ];

  return (
    <section className="workbench-view" aria-label="Media Studio">
      <div className="view-heading">
        <GalleryHorizontalEnd size={26} />
        <h3>Media Studio</h3>
        <button className="secondary-button" onClick={() => void onRefresh()} type="button">Refresh</button>
      </div>
      <div className="media-status-row">
        {backendCards.map((backend) => (
          <article className="media-status-card" key={backend.label}>
            <strong>{backend.label}</strong>
            <span className={`backend-status ${backend.status}`}>
              {backend.status.replace('_', ' ')}
            </span>
            <p>{backend.detail}</p>
            <span>{backend.meta}</span>
          </article>
        ))}
        <article className="media-status-card">
          <strong>Queue</strong>
          <p>{mediaStatus?.comfyui.queue_running ?? 0} running / {mediaStatus?.comfyui.queue_pending ?? 0} pending</p>
          <span>{mediaStatus?.comfyui.base_url ?? 'No backend URL'}</span>
        </article>
      </div>
      <div className="strategy-grid">
        {mediaPlan.map((item) => {
          const Icon = item.icon;
          return (
            <article className="strategy-card" key={item.title}>
              <Icon size={24} />
              <strong>{item.title}</strong>
              <p>{item.stack}</p>
              <span>{item.lane}</span>
              <button
                className="secondary-button"
                disabled={isMediaBusy}
                onClick={() => void onCreateJob(item.jobType, item.title, item.stack)}
                type="button"
              >
                Check backend
              </button>
            </article>
          );
        })}
      </div>
      <div className="job-list-panel">
        <div className="section-heading">
          <Activity size={18} />
          <h3>Generation Jobs</h3>
        </div>
        <div className="job-list">
          {jobs.slice(0, 8).map((job) => (
            <article className="job-row" key={job.id}>
              <div>
                <strong>{job.title}</strong>
                <span>{job.job_type} / {job.backend}</span>
              </div>
              <small className={`job-status ${job.status}`}>{job.status.replace('_', ' ')}</small>
            </article>
          ))}
          {jobs.length === 0 && <div className="empty-line">No media jobs</div>}
        </div>
      </div>
      <div className="job-list-panel">
        <div className="section-heading">
          <Image size={18} />
          <h3>Artifacts</h3>
        </div>
        <div className="artifact-gallery">
          {artifacts.slice(0, 8).map((artifact) => {
            const downloadUrl = edisonApi.artifactDownloadUrl(artifact.id);
            const isVisual = artifact.kind === 'image';
            return (
              <article className="artifact-card" key={artifact.id}>
                {isVisual && <img alt={artifact.title} src={downloadUrl} />}
                <div className="artifact-card-meta">
                  <strong>{artifact.title}</strong>
                  <span>{artifact.kind} / {artifact.mime_type ?? 'file'}</span>
                  <small>{artifact.path}</small>
                </div>
                <div className="artifact-card-actions">
                  <a className="secondary-button" href={downloadUrl} target="_blank" rel="noreferrer">
                    Download
                  </a>
                  <button className="secondary-button" onClick={() => onUseArtifactInChat(artifact)} type="button">
                    Use In Chat
                  </button>
                </div>
              </article>
            );
          })}
          {artifacts.length === 0 && <div className="empty-line">No generated artifacts yet</div>}
        </div>
      </div>
    </section>
  );
}

function SystemView({
  fanControls,
  groupedModels,
  models,
  onRefresh,
  onUpdateFanControl,
  status,
}: {
  fanControls: GPUFanControlSnapshot | null;
  groupedModels: { ready: ModelProfile[]; pending: ModelProfile[] };
  models: ModelProfile[];
  onRefresh: () => Promise<void>;
  onUpdateFanControl: (gpuIndex: number, mode: GPUFanMode, manualSpeed: number) => Promise<void>;
  status: SystemStatus | null;
}) {
  return (
    <section className="workbench-view" aria-label="System Status">
      <div className="view-heading">
        <Server size={26} />
        <h3>System Status</h3>
        <button className="secondary-button icon-text-button" onClick={() => void onRefresh()} type="button">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>
      <dl className="wide-metric-grid">
        <div>
          <dt>API</dt>
          <dd>{status?.status ?? 'offline'}</dd>
        </div>
        <div>
          <dt>Configured Models</dt>
          <dd>{groupedModels.ready.length}</dd>
        </div>
        <div>
          <dt>Pending Profiles</dt>
          <dd>{groupedModels.pending.length}</dd>
        </div>
        <div>
          <dt>GPU Devices</dt>
          <dd>{status?.gpu_devices.length ?? 0}</dd>
        </div>
      </dl>
      <section className="fan-control-panel" aria-label="Multi GPU fan control">
        <div className="section-heading">
          <Fan size={18} />
          <h3>GPU Fan Control</h3>
        </div>
        <div className="fan-control-meta">
          <span>Backend: {fanControls?.backend ?? 'monitor'}</span>
          <span>{fanControls?.hardware_control_enabled ? 'Hardware writes enabled' : 'Monitor mode'}</span>
        </div>
        <div className="fan-controller-grid">
          {(fanControls?.controllers ?? []).map((controller) => (
            <FanControlCard
              controller={controller}
              key={controller.gpu.index}
              onUpdate={onUpdateFanControl}
            />
          ))}
          {(fanControls?.controllers.length ?? 0) === 0 && (
            <div className="empty-line">No NVIDIA GPUs detected by nvidia-smi.</div>
          )}
        </div>
      </section>
      <div className="feature-grid compact">
        {models.map((model) => (
          <article className="feature-card" key={model.id}>
            <strong>{model.display_name}</strong>
            <p>{model.capabilities.join(' / ')}</p>
            <span className={`model-status ${model.status}`}>{model.status.replace('_', ' ')}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function FanControlCard({
  controller,
  onUpdate,
}: {
  controller: GPUFanControlSnapshot['controllers'][number];
  onUpdate: (gpuIndex: number, mode: GPUFanMode, manualSpeed: number) => Promise<void>;
}) {
  const [mode, setMode] = useState<GPUFanMode>(controller.policy.mode);
  const [manualSpeed, setManualSpeed] = useState(controller.policy.manual_speed_percent);
  const fanSpeed = controller.gpu.fan_speed_percent ?? controller.target_speed_percent ?? 0;
  const targetSpeed = controller.target_speed_percent ?? manualSpeed;
  const gaugeStyle = { '--fan-speed': `${Math.max(0, Math.min(100, targetSpeed))}%` } as CSSProperties;

  useEffect(() => {
    setMode(controller.policy.mode);
    setManualSpeed(controller.policy.manual_speed_percent);
  }, [controller.policy.manual_speed_percent, controller.policy.mode]);

  return (
    <article className="fan-controller-card">
      <div className="fan-card-header">
        <div>
          <span className="section-label">GPU {controller.gpu.index}</span>
          <strong>{controller.gpu.name}</strong>
        </div>
        <small className={controller.applied ? 'fan-apply-state applied' : 'fan-apply-state'}>
          {controller.applied ? 'Applied' : 'Staged'}
        </small>
      </div>

      <div className="fan-gauge-row">
        <div className="fan-gauge" style={gaugeStyle} aria-label={`Target fan speed ${targetSpeed}%`}>
          <Fan size={34} />
          <strong>{targetSpeed}%</strong>
          <span>Target</span>
        </div>
        <dl className="fan-telemetry">
          <div>
            <dt>Temp</dt>
            <dd>{formatMaybeNumber(controller.gpu.temperature_c, 'C')}</dd>
          </div>
          <div>
            <dt>Fan</dt>
            <dd>{formatMaybeNumber(fanSpeed, '%')}</dd>
          </div>
          <div>
            <dt>Load</dt>
            <dd>{formatMaybeNumber(controller.gpu.utilization_percent, '%')}</dd>
          </div>
          <div>
            <dt>Power</dt>
            <dd>{formatMaybeNumber(controller.gpu.power_draw_watts, 'W')}</dd>
          </div>
        </dl>
      </div>

      <div className="fan-mode-row" role="group" aria-label={`GPU ${controller.gpu.index} fan mode`}>
        {(['auto', 'manual', 'curve'] as GPUFanMode[]).map((nextMode) => (
          <button
            className={mode === nextMode ? 'mode-button active' : 'mode-button'}
            key={nextMode}
            onClick={() => setMode(nextMode)}
            type="button"
          >
            {nextMode}
          </button>
        ))}
      </div>

      <label className="fan-slider-label" htmlFor={`gpu-${controller.gpu.index}-fan-speed`}>
        Manual speed
      </label>
      <input
        id={`gpu-${controller.gpu.index}-fan-speed`}
        max={100}
        min={20}
        onChange={(event) => setManualSpeed(Number(event.target.value))}
        type="range"
        value={manualSpeed}
      />

      <div className="fan-curve-preview" aria-label="Fan curve preview">
        {controller.policy.curve.map((point) => (
          <span
            key={`${point.temperature_c}-${point.speed_percent}`}
            style={{ height: `${Math.max(12, point.speed_percent)}%` }}
            title={`${point.temperature_c}C / ${point.speed_percent}%`}
          />
        ))}
      </div>

      <div className="fan-card-actions">
        <button
          className="apply-button"
          onClick={() => void onUpdate(controller.gpu.index, mode, manualSpeed)}
          type="button"
        >
          Apply
        </button>
        <span>{controller.detail}</span>
      </div>
    </article>
  );
}

function SettingsView({ sessionState, status }: { sessionState: SessionStateRecord | null; status: SystemStatus | null }) {
  return (
    <section className="workbench-view" aria-label="Settings">
      <div className="view-heading">
        <Settings size={26} />
        <h3>Settings</h3>
      </div>
      <div className="settings-stack">
        <article className="settings-panel">
          <div className="section-heading">
            <Brain size={18} />
            <h3>Model Plan</h3>
          </div>
          <dl className="settings-list">
            {modelPlan.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </article>
        <article className="settings-panel">
          <div className="section-heading">
            <Globe2 size={18} />
            <h3>Remote Access</h3>
          </div>
          <dl className="settings-list">
            <div>
              <dt>Network</dt>
              <dd>Tailscale private tailnet for anywhere access without exposing public ports.</dd>
            </div>
            <div>
              <dt>Host</dt>
              <dd>Run EDISON on the primary AI PC, advertise it as a tailnet service, and keep auth in Tailscale.</dd>
            </div>
            <div>
              <dt>Current Session</dt>
              <dd>{sessionState?.session_id ?? 'local-workbench'} on {status?.environment ?? 'local'}.</dd>
            </div>
          </dl>
        </article>
      </div>
    </section>
  );
}

function agentItems(): Array<[string, string]> {
  return [
    ['Run State', 'Received, planned, awaiting approval, executing, verifying, completed, failed.'],
    ['Approvals', 'Destructive file, shell, network, and account actions pause for confirmation.'],
    ['Events', 'Every tool call gets status, elapsed time, result metadata, and artifact links.'],
    ['Swarm Ready', 'Specialist roles can plug into the same run/event/checkpoint model.'],
  ];
}

function memoryItems(): Array<[string, string]> {
  return [
    ['User Memory', 'Stable preferences, recurring projects, environment facts, and writing style.'],
    ['Project Memory', 'Goals, decisions, files, artifacts, current TODOs, and last active context.'],
    ['Semantic Recall', 'Embeddings-backed retrieval for chats, docs, project notes, and artifacts.'],
    ['Controls', 'Inspect, edit, disable, expire, or delete memories with source visibility.'],
  ];
}

type MessageBlock =
  | { kind: 'paragraph'; text: string }
  | { kind: 'code'; text: string; language: string }
  | { kind: 'ul' | 'ol'; items: string[] };

function appendDraftChatTurn(
  current: ConversationWithMessages | null,
  mode: ChatMode,
  userContent: string,
  userId: string,
  assistantId: string,
): ConversationWithMessages {
  const now = new Date().toISOString();
  const userMessage: MessageRecord = {
    id: userId,
    conversation_id: current?.id ?? 'draft-conversation',
    role: 'user',
    content: userContent,
    metadata: { streamed: true, draft: true },
    created_at: now,
  };
  const assistantMessage: MessageRecord = {
    id: assistantId,
    conversation_id: current?.id ?? 'draft-conversation',
    role: 'assistant',
    content: '',
    metadata: { streamed: true, draft: true },
    created_at: now,
  };
  if (current) {
    return { ...current, messages: [...current.messages, userMessage, assistantMessage], updated_at: now };
  }
  return {
    id: 'draft-conversation',
    title: conversationTitle(userContent),
    mode,
    memory_enabled: true,
    created_at: now,
    updated_at: now,
    messages: [userMessage, assistantMessage],
  };
}

function replaceDraftMessage(
  current: ConversationWithMessages | null,
  draftId: string,
  realMessage: MessageRecord,
  conversationId: string,
) {
  if (!current) {
    return current;
  }
  return {
    ...current,
    id: conversationId,
    messages: current.messages.map((message) => (
      message.id === draftId ? realMessage : { ...message, conversation_id: conversationId }
    )),
  };
}

function updateDraftAssistantMessage(
  current: ConversationWithMessages | null,
  assistantId: string,
  content: string,
) {
  if (!current) {
    return current;
  }
  return {
    ...current,
    messages: current.messages.map((message) => (
      message.id === assistantId ? { ...message, content } : message
    )),
  };
}

function parseMessageBlocks(content: string): MessageBlock[] {
  const blocks: MessageBlock[] = [];
  const codeFencePattern = /```([a-zA-Z0-9_-]*)?\n?([\s\S]*?)```/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = codeFencePattern.exec(content)) !== null) {
    pushTextBlocks(content.slice(cursor, match.index), blocks);
    blocks.push({ kind: 'code', language: match[1] ?? '', text: match[2] ?? '' });
    cursor = match.index + match[0].length;
  }
  pushTextBlocks(content.slice(cursor), blocks);
  if (blocks.length === 0 && content.trim()) {
    blocks.push({ kind: 'paragraph', text: content.trim() });
  }
  return blocks;
}

function pushTextBlocks(text: string, blocks: MessageBlock[]) {
  text.split(/\n{2,}/).forEach((part) => {
    const trimmed = part.trim();
    if (!trimmed) {
      return;
    }
    const lines = trimmed.split(/\n/).map((line) => line.trim()).filter(Boolean);
    if (lines.every((line) => /^[-*]\s+/.test(line))) {
      blocks.push({ kind: 'ul', items: lines.map((line) => line.replace(/^[-*]\s+/, '')) });
      return;
    }
    if (lines.every((line) => /^\d+[.)]\s+/.test(line))) {
      blocks.push({ kind: 'ol', items: lines.map((line) => line.replace(/^\d+[.)]\s+/, '')) });
      return;
    }
    blocks.push({ kind: 'paragraph', text: trimmed });
  });
}

function renderInlineMessageText(text: string) {
  return text.split(/(`[^`]+`)/g).map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>;
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function artifactsFromMetadata(metadata: Record<string, unknown>): ArtifactRecord[] {
  const rawArtifacts = metadata.artifacts;
  if (!Array.isArray(rawArtifacts)) {
    return [];
  }
  return rawArtifacts.flatMap((item) => {
    if (!item || typeof item !== 'object') {
      return [];
    }
    const candidate = item as Partial<ArtifactRecord>;
    if (!candidate.id || !candidate.title || !candidate.kind) {
      return [];
    }
    return [{
      id: String(candidate.id),
      title: String(candidate.title),
      kind: candidate.kind,
      path: String(candidate.path ?? ''),
      mime_type: candidate.mime_type ?? null,
      source_job_id: candidate.source_job_id ?? null,
      metadata: candidate.metadata ?? {},
      created_at: String(candidate.created_at ?? ''),
    } as ArtifactRecord];
  });
}

function mediaJobFromMetadata(metadata: Record<string, unknown>): JobRecord | null {
  const rawJob = metadata.media_job;
  if (!rawJob || typeof rawJob !== 'object') {
    return null;
  }
  const candidate = rawJob as Partial<JobRecord>;
  if (!candidate.id || !candidate.title || !candidate.job_type || !candidate.status) {
    return null;
  }
  return {
    id: String(candidate.id),
    job_type: candidate.job_type,
    status: candidate.status,
    title: String(candidate.title),
    prompt: candidate.prompt ?? null,
    backend: String(candidate.backend ?? 'media'),
    source_artifact_id: candidate.source_artifact_id ?? null,
    result_artifact_id: candidate.result_artifact_id ?? null,
    metadata: candidate.metadata ?? {},
    created_at: String(candidate.created_at ?? ''),
    updated_at: String(candidate.updated_at ?? ''),
  } as JobRecord;
}

function updateMediaStatusMessage(
  current: ConversationWithMessages | null,
  messageId: string,
  job: JobRecord,
): ConversationWithMessages | null {
  if (!current) {
    return current;
  }
  return {
    ...current,
    messages: current.messages.map((message) => (
      message.id === messageId
        ? {
            ...message,
            content: mediaJobStatusLine(job),
            metadata: {
              ...message.metadata,
              media_job: job,
            },
          }
        : message
    )),
  };
}

function latestImageArtifactFromConversation(conversation: ConversationWithMessages | null): ArtifactRecord | null {
  const messages = conversation?.messages ?? [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const image = artifactsFromMetadata(messages[index].metadata).find((artifact) => artifact.kind === 'image');
    if (image) {
      return image;
    }
  }
  return null;
}

function inferMediaJobType(content: string): JobType {
  const lowered = content.toLowerCase();
  if (/\b(video|animation|movie|clip|timelapse|wan)\b/.test(lowered)) {
    return 'video';
  }
  if (/\b(3d|mesh|model|glb|obj|stl|sculpt)\b/.test(lowered)) {
    return 'mesh';
  }
  if (/\b(audio|music|song|voice|sound)\b/.test(lowered)) {
    return 'audio';
  }
  return 'image';
}

function mediaJobTitle(content: string, jobType: JobType) {
  return `${jobType.replace('_', ' ')}: ${conversationTitle(content)}`;
}

function mediaJobStatusLine(job: JobRecord) {
  const progress = jobProgress(job);
  const step = typeof job.metadata.step === 'string' ? job.metadata.step : null;
  if (job.status === 'setup_required') {
    return `${job.backend} needs setup before I can generate that ${job.job_type} result. I created the job and kept it visible in Media Studio.`;
  }
  if (job.status === 'complete') {
    return `Done. I generated the ${job.job_type} result.`;
  }
  if (job.status === 'error') {
    return mediaJobFailureLine(job);
  }
  const progressText = progress !== null ? ` (${progress}%)` : '';
  const stepText = step ? ` ${step}` : '';
  return `Working on a ${job.job_type.replace('_', ' ')} job with ${job.backend}.${progressText}${stepText} I will add the result here when it finishes.`;
}

function mediaJobFailureLine(job: JobRecord) {
  const detail = typeof job.metadata.error === 'string'
    ? job.metadata.error.split('\n')[0]
    : 'The backend returned an error before producing an artifact.';
  return `${job.backend} could not finish that ${job.job_type.replace('_', ' ')} job. ${detail}`;
}

function jobProgress(job: JobRecord): number | null {
  const value = job.metadata.progress;
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.max(0, Math.min(100, Math.round(value)));
  }
  return null;
}

function conversationTitle(message: string) {
  const title = message.trim().replace(/\s+/g, ' ');
  return title.length > 56 ? `${title.slice(0, 53)}...` : title || 'New conversation';
}

function sleep(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function viewTitle(view: ViewId, activeConversation: ConversationWithMessages | null) {
  if (view === 'chat') {
    return activeConversation?.title ?? 'New conversation';
  }
  return navigation.find((item) => item.id === view)?.label ?? 'Workbench';
}

function formatBytes(size: number | null | undefined) {
  if (!size) {
    return '0 B';
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatMaybeNumber(value: number | null | undefined, unit: string) {
  if (value === null || value === undefined) {
    return '--';
  }
  return `${Math.round(value)}${unit}`;
}

function formatCompareDuration(run: CompareRun) {
  if (!run.finishedAt) {
    return run.status === 'streaming' ? 'Streaming' : 'Not started';
  }
  return `${((run.finishedAt - run.startedAt) / 1000).toFixed(1)}s`;
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function friendlyError(error: string) {
  if (error.includes('Failed to fetch')) {
    return `Core API unavailable at ${edisonApi.apiBase || 'the current workbench origin'}`;
  }
  return error;
}

type ParsedWorkspaceContext = {
  enabled: boolean;
  mode?: string;
  targetPath?: string;
  focusPaths: string[];
  warnings: string[];
  instructionFiles: string[];
  indexMatches: Array<{ path: string; score?: number; lineNumber?: number }>;
};

type ParsedKnowledgeContext = {
  enabled: boolean;
  query?: string;
  warnings: string[];
  matches: Array<{
    sourceId: string;
    sourceTitle: string;
    sourceKind: string;
    uri?: string;
    path?: string;
    score?: number;
    snippet: string;
  }>;
};

type ChatContextPreview = {
  instructionContext: WorkspaceInstructionContext | null;
  indexMatches: WorkspaceIndexSearchMatch[];
  warnings: string[];
};

type ChatContextDiagnostics = {
  assistantTurnsWithContext: number;
  focusPaths: number;
  instructions: number;
  indexMatches: number;
  warnings: number;
  latestTargetPath?: string;
};

function parseWorkspaceContext(raw: unknown): ParsedWorkspaceContext | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const value = raw as Record<string, unknown>;
  return {
    enabled: Boolean(value.enabled),
    mode: toOptionalString(value.mode),
    targetPath: toOptionalString(value.target_path),
    focusPaths: toStringArray(value.focus_paths),
    warnings: toStringArray(value.warnings),
    instructionFiles: toStringArray(value.instruction_files),
    indexMatches: toIndexMatches(value.index_matches),
  };
}

function parseKnowledgeContext(raw: unknown): ParsedKnowledgeContext | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const value = raw as Record<string, unknown>;
  return {
    enabled: Boolean(value.enabled),
    query: toOptionalString(value.query),
    warnings: toStringArray(value.warnings),
    matches: toKnowledgeMatches(value.matches),
  };
}

function contextItemCount(context: ParsedWorkspaceContext): number {
  return context.focusPaths.length + context.instructionFiles.length + context.indexMatches.length + context.warnings.length;
}

function contextBreakdownText(context: ParsedWorkspaceContext): string {
  return `Focus: ${context.focusPaths.length} | Instructions: ${context.instructionFiles.length} | Index: ${context.indexMatches.length} | Warnings: ${context.warnings.length}`;
}

function summarizeConversationContext(conversation: ConversationWithMessages | null): ChatContextDiagnostics {
  if (!conversation) {
    return {
      assistantTurnsWithContext: 0,
      focusPaths: 0,
      instructions: 0,
      indexMatches: 0,
      warnings: 0,
    };
  }

  let assistantTurnsWithContext = 0;
  let focusPaths = 0;
  let instructions = 0;
  let indexMatches = 0;
  let warnings = 0;
  let latestTargetPath: string | undefined;

  for (const message of conversation.messages) {
    if (message.role !== 'assistant') {
      continue;
    }
    const context = parseWorkspaceContext(message.metadata.workspace_context);
    if (!context || !context.enabled) {
      continue;
    }
    assistantTurnsWithContext += 1;
    focusPaths += context.focusPaths.length;
    instructions += context.instructionFiles.length;
    indexMatches += context.indexMatches.length;
    warnings += context.warnings.length;
    if (context.targetPath) {
      latestTargetPath = context.targetPath;
    }
  }

  return {
    assistantTurnsWithContext,
    focusPaths,
    instructions,
    indexMatches,
    warnings,
    latestTargetPath,
  };
}

function readStoredBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') {
    return fallback;
  }
  const value = window.localStorage.getItem(key);
  if (value === 'true') {
    return true;
  }
  if (value === 'false') {
    return false;
  }
  return fallback;
}

function readStoredString(key: string, fallback: string): string {
  if (typeof window === 'undefined') {
    return fallback;
  }
  return window.localStorage.getItem(key) ?? fallback;
}

function readStoredStringArray(key: string, fallback: string[]): string[] {
  if (typeof window === 'undefined') {
    return fallback;
  }
  const raw = window.localStorage.getItem(key);
  if (!raw) {
    return fallback;
  }
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return fallback;
    }
    return parsed
      .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      .slice(0, 12);
  } catch {
    return fallback;
  }
}

function readStoredInt(key: string, fallback: number, min: number, max: number): number {
  const value = readStoredString(key, String(fallback));
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  return Math.max(min, Math.min(max, parsed));
}

function readStoredContextFilter(key: string, fallback: ContextFilter): ContextFilter {
  if (typeof window === 'undefined') {
    return fallback;
  }
  const value = window.localStorage.getItem(key);
  if (value === 'all' || value === 'instructions' || value === 'index' || value === 'warnings') {
    return value;
  }
  return fallback;
}

function writeStoredBoolean(key: string, value: boolean): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(key, value ? 'true' : 'false');
}

function writeStoredString(key: string, value: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(key, value);
}

function writeStoredStringArray(key: string, value: string[]): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(key, JSON.stringify(value.slice(0, 12)));
}

function readStoredCollapsedMap(key: string): Record<string, boolean> {
  if (typeof window === 'undefined') {
    return {};
  }
  const raw = window.localStorage.getItem(key);
  if (!raw) {
    return {};
  }
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') {
      return {};
    }
    const result: Record<string, boolean> = {};
    for (const [entryKey, entryValue] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof entryValue === 'boolean') {
        result[entryKey] = entryValue;
      }
    }
    return result;
  } catch {
    return {};
  }
}

function writeStoredRecord(key: string, value: Record<string, boolean>): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(key, JSON.stringify(value));
}

function removeStoredValue(key: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.removeItem(key);
}

function collapsedContextStorageKey(conversationId: string): string {
  return `${CONTEXT_COLLAPSED_STORAGE_KEY_PREFIX}:${conversationId}`;
}

function toOptionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
}

function toIndexMatches(value: unknown): Array<{ path: string; score?: number; lineNumber?: number }> {
  if (!Array.isArray(value)) {
    return [];
  }
  const matches: Array<{ path: string; score?: number; lineNumber?: number }> = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const row = item as Record<string, unknown>;
    const path = toOptionalString(row.path);
    if (!path) {
      continue;
    }
    matches.push({
      path,
      score: typeof row.score === 'number' ? row.score : undefined,
      lineNumber: typeof row.line_number === 'number' ? row.line_number : undefined,
    });
  }
  return matches;
}

function toKnowledgeMatches(value: unknown): ParsedKnowledgeContext['matches'] {
  if (!Array.isArray(value)) {
    return [];
  }
  const matches: ParsedKnowledgeContext['matches'] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const row = item as Record<string, unknown>;
    const sourceId = toOptionalString(row.source_id) ?? toOptionalString(row.sourceId);
    const sourceTitle = toOptionalString(row.source_title) ?? toOptionalString(row.sourceTitle);
    const sourceKind = toOptionalString(row.source_kind) ?? toOptionalString(row.sourceKind) ?? 'source';
    if (!sourceId || !sourceTitle) {
      continue;
    }
    matches.push({
      sourceId,
      sourceTitle,
      sourceKind,
      uri: toOptionalString(row.uri),
      path: toOptionalString(row.path),
      score: typeof row.score === 'number' ? row.score : undefined,
      snippet: toOptionalString(row.snippet) ?? '',
    });
  }
  return matches;
}
