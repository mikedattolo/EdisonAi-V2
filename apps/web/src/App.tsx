import {
  Activity,
  Bot,
  Box,
  Brain,
  BookOpen,
  CalendarDays,
  Camera,
  CheckSquare2,
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
  Zap,
} from 'lucide-react';
import { CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

import { edisonApi } from './api';
import type {
  AgentRunRecord,
  AgentRunWithEvents,
  ArtifactRecord,
  CapabilityStatus,
  ChatMode,
  ConversationRecord,
  ConversationWithMessages,
  CameraFrameAnalysisResponse,
  CameraVisionStatus,
  DocumentRecord,
  GPUFanControlSnapshot,
  GPUFanMode,
  HardwareControlCenter,
  HardwareStatus,
  JobRecord,
  JobType,
  KnowledgePreset,
  KnowledgeSearchMatch,
  KnowledgeSourceRecord,
  KnowledgeStatus,
  LocalIntegrationRecord,
  MediaSystemStatus,
  MediaGenerationMode,
  MediaGenerationModeRecord,
  MessageRecord,
  ModelProfile,
  ModelSelection,
  OrganizerItemRecord,
  OrganizerKind,
  OrganizerStatus,
  SessionStateRecord,
  SearchCompareResponse,
  SearchProvider,
  SystemStatus,
  RuntimeSettingsRecord,
  ToyBoxManagerStatus,
  WorkspaceCommand,
  WorkspaceCommandRunResult,
  WorkspaceEntry,
  WorkspaceFile,
  WorkspaceIndexSearchMatch,
  WorkspaceInstructionContext,
  WorkspacePatchPreview,
  WorkspaceRootRecord,
  WorkspaceScan,
  WorkspaceSearchMatch,
  WorkspaceSummary,
} from './types';

const SESSION_ID = 'local-workbench';

type ViewId =
  | 'chat'
  | 'agent'
  | 'compare'
  | 'research'
  | 'organizer'
  | 'documents'
  | 'search'
  | 'code'
  | 'media'
  | 'gallery'
  | 'memory'
  | 'system'
  | 'settings';
type IconType = typeof MessageSquare;
type ContextFilter = 'all' | 'instructions' | 'index' | 'warnings';
type CompareStatus = 'idle' | 'streaming' | 'done' | 'error';
type ResearchDepth = 'scan' | 'brief' | 'deep';

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

const navigation: Array<{ id: ViewId; label: string; icon: IconType }> = [
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'research', label: 'Research', icon: BookOpen },
  { id: 'organizer', label: 'Organizer', icon: CheckSquare2 },
  { id: 'documents', label: 'Docs', icon: FileText },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'code', label: 'Code Space', icon: Code2 },
  { id: 'media', label: 'Media', icon: GalleryHorizontalEnd },
  { id: 'gallery', label: 'Gallery', icon: Image },
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

const researchDepthOptions: Array<{ value: ResearchDepth; label: string; instruction: string }> = [
  {
    value: 'scan',
    label: 'Scan',
    instruction: 'Return a fast orientation with the strongest facts, uncertainties, and next checks.',
  },
  {
    value: 'brief',
    label: 'Brief',
    instruction: 'Return a concise research brief with claims, source notes, risks, and recommendations.',
  },
  {
    value: 'deep',
    label: 'Deep',
    instruction: 'Return a structured deep research report with source-backed findings, gaps, and action steps.',
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
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [capabilityStatus, setCapabilityStatus] = useState<CapabilityStatus | null>(null);
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [modelSelection, setModelSelection] = useState<ModelSelection | null>(null);
  const [sessionState, setSessionState] = useState<SessionStateRecord | null>(null);
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [mediaStatus, setMediaStatus] = useState<MediaSystemStatus | null>(null);
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettingsRecord | null>(null);
  const [fanControls, setFanControls] = useState<GPUFanControlSnapshot | null>(null);
  const [hardwareStatus, setHardwareStatus] = useState<HardwareStatus | null>(null);
  const [hardwareControlCenter, setHardwareControlCenter] = useState<HardwareControlCenter | null>(null);
  const [cameraVisionStatus, setCameraVisionStatus] = useState<CameraVisionStatus | null>(null);
  const [cameraAnalysis, setCameraAnalysis] = useState<CameraFrameAnalysisResponse | null>(null);
  const [agentRuns, setAgentRuns] = useState<AgentRunRecord[]>([]);
  const [activeAgentRun, setActiveAgentRun] = useState<AgentRunWithEvents | null>(null);
  const [mediaModes, setMediaModes] = useState<MediaGenerationModeRecord[]>([]);
  const [toyBoxStatus, setToyBoxStatus] = useState<ToyBoxManagerStatus | null>(null);
  const [mediaJobs, setMediaJobs] = useState<JobRecord[]>([]);
  const [mediaArtifacts, setMediaArtifacts] = useState<ArtifactRecord[]>([]);
  const [workspaceSummary, setWorkspaceSummary] = useState<WorkspaceSummary | null>(null);
  const [workspaceScan, setWorkspaceScan] = useState<WorkspaceScan | null>(null);
  const [workspaceRoots, setWorkspaceRoots] = useState<WorkspaceRootRecord[]>([]);
  const [activeWorkspaceRootId, setActiveWorkspaceRootId] = useState('app');
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
  const [activeMode, setActiveMode] = useState<ChatMode>('auto');
  const [agentModeEnabled, setAgentModeEnabled] = useState(false);
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
  const [isCameraBusy, setIsCameraBusy] = useState(false);
  const [isCameraFeedPaused, setIsCameraFeedPaused] = useState(false);
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
    if (activeView === 'media' || activeView === 'gallery') {
      void refreshMediaSurface();
    }
    if (activeView === 'settings') {
      void refreshSettingsSurface();
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

  const hardwareSummary = useMemo(() => {
    const hailo = hardwareStatus?.accelerators.find((accelerator) => accelerator.kind === 'hailo8');
    const readyCameras = hardwareStatus?.cameras.filter((cameraDevice) => cameraDevice.status === 'ready').length ?? 0;
    return {
      hailoLabel: hailo ? hailo.status.replace('_', ' ') : 'not checked',
      hailoReady: hailo?.status === 'ready',
      readyCameras,
    };
  }, [hardwareStatus]);

  const chatContextDiagnostics = useMemo(
    () => summarizeConversationContext(activeConversation),
    [activeConversation],
  );

  useEffect(() => {
    if (!chatAutoPreviewEnabled || activeView !== 'chat') {
      return;
    }
    const hasWorkspaceFocus = Boolean(chatWorkspacePath.trim() || workspaceFile?.path || chatContextPaths.length);
    if (!agentModeEnabled && !hasWorkspaceFocus && !['coding', 'agent', 'swarm'].includes(activeMode)) {
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
    agentModeEnabled,
    chatWorkspacePath,
    chatContextPaths.length,
    chatContextMatches,
    composer,
    workspaceFile?.path,
  ]);

  async function bootstrap() {
    try {
      setError(null);
      const [
        nextStatus,
        nextCapabilities,
        nextFanControls,
        nextHardwareStatus,
        nextHardwareControlCenter,
        nextAgentRuns,
        nextModels,
        nextConversations,
        nextSession,
        nextKnowledgeStatus,
        nextKnowledgeSources,
        nextRuntimeSettings,
      ] = await Promise.all([
        edisonApi.getStatus(),
        edisonApi.getCapabilities(),
        edisonApi.getFanControls(),
        edisonApi.getHardwareStatus(),
        edisonApi.getHardwareControlCenter(),
        edisonApi.listAgentRuns(),
        edisonApi.listModels(),
        edisonApi.listConversations(),
        edisonApi.getSession(SESSION_ID),
        edisonApi.getKnowledgeStatus(),
        edisonApi.listKnowledgeSources(50),
        edisonApi.getRuntimeSettings(),
      ]);
      setStatus(nextStatus);
      setCapabilityStatus(nextCapabilities);
      setFanControls(nextFanControls);
      setHardwareStatus(nextHardwareStatus);
      setHardwareControlCenter(nextHardwareControlCenter);
      setAgentRuns(nextAgentRuns);
      if (nextAgentRuns[0]) {
        setActiveAgentRun(await edisonApi.getAgentRun(nextAgentRuns[0].id));
      }
      setModels(nextModels);
      setConversations(nextConversations);
      setSessionState(nextSession);
      setKnowledgeStatus(nextKnowledgeStatus);
      setKnowledgeSources(nextKnowledgeSources);
      setRuntimeSettings(nextRuntimeSettings);
      setActiveMode(nextSession.selected_mode ?? 'auto');
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
    setActiveMode('auto');
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
      if (isMediaGenerationPrompt(content)) {
        await handleMediaChatSend(content);
        return;
      }

      const workspaceTargetPath = chatWorkspacePath.trim() || workspaceFile?.path;
      const hasWorkspaceFocus = Boolean(workspaceTargetPath || chatContextPaths.length > 0);
      const payload = {
        conversation_id: activeConversation?.id ?? null,
        message: content,
        mode: 'auto' as ChatMode,
        preferred_model: modelSelection?.model.id ?? null,
        agent_enabled: agentModeEnabled,
        memory_enabled: true,
        workspace_path: workspaceTargetPath,
        workspace_context_paths: chatContextPaths,
        include_workspace_context: agentModeEnabled || hasWorkspaceFocus,
        max_workspace_context_matches: chatContextMatches,
        include_knowledge_context: chatKnowledgeEnabled,
        knowledge_query: chatKnowledgeQuery.trim() || undefined,
        max_knowledge_context_matches: chatKnowledgeMatches,
        include_personal_context: true,
        max_personal_context_items: 8,
      };
      const draftUserId = `draft-user-${Date.now()}`;
      const draftAssistantId = `draft-assistant-${Date.now()}`;
      let streamedContent = '';
      setActiveConversation((current) =>
        appendDraftChatTurn(current, agentModeEnabled ? 'agent' : 'auto', content, draftUserId, draftAssistantId),
      );
      setComposer('');

      const response = await edisonApi.streamChatTurn(payload, {
        onStart: (start) => {
          setModelSelection(start.model_selection);
          if (start.agent_run) {
            setActiveAgentRun(start.agent_run);
            void refreshAgentRuns(start.agent_run.id);
          }
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
      setActiveMode(response.model_selection.mode);
      setConversations(await edisonApi.listConversations());
      const runId = agentRunIdFromConversation(response.conversation);
      if (runId) {
        await refreshAgentRuns(runId);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Message failed');
    } finally {
      setIsSending(false);
    }
  }

  async function handleMediaChatSend(content: string) {
    const generationMode = inferMediaGenerationMode(content);
    if (generationMode) {
      const conversation = await ensureChatConversation(content, 'media');
      await edisonApi.addMessage(conversation.id, {
        role: 'user',
        content,
        metadata: { mode: 'media', source: 'chat-media-request', generation_mode: generationMode },
      });
      const job = await edisonApi.generateMedia({
        mode: generationMode,
        prompt: content,
        metadata: {
          source: 'chat',
          conversation_id: conversation.id,
          deliver_to_chat: true,
          generation_mode: generationMode,
          width: 1024,
          height: 1024,
          steps: 30,
          cfg: 6.5,
          sampler_name: 'dpmpp_2m',
          scheduler: 'karras',
          enhance_prompt: true,
        },
      });
      const statusMessage = await edisonApi.addMessage(conversation.id, {
        role: 'assistant',
        content: mediaJobStatusLine(job),
        model: job.backend,
        metadata: {
          delivery_type: 'media_job_status',
          generation_mode: generationMode,
          media_job: job,
        },
      });
      setComposer('');
      setActiveConversation(await edisonApi.getConversation(conversation.id));
      setConversations(await edisonApi.listConversations());
      await refreshMediaSurface();
      if (job.status === 'complete' && job.result_artifact_id) {
        await edisonApi.deliverMediaJob(job.id, conversation.id);
        setActiveConversation(await edisonApi.getConversation(conversation.id));
        await refreshMediaSurface();
        return;
      }
      if (['queued', 'loading', 'generating', 'encoding'].includes(job.status)) {
        void pollMediaJobForChat(job.id, conversation.id, statusMessage.id);
      }
      return;
    }

    const jobType = inferMediaJobType(content);
    let sourceArtifact = jobType === 'mesh' ? latestImageArtifactFromConversation(activeConversation) : null;
    const conversation = await ensureChatConversation(content, 'media');
    await edisonApi.addMessage(conversation.id, {
      role: 'user',
      content,
      metadata: { mode: 'media', source: 'chat-media-request' },
    });
    if (jobType === 'mesh' && !sourceArtifact) {
      const prepMessage = await edisonApi.addMessage(conversation.id, {
        role: 'assistant',
        content: 'I am creating a source image first, then I will send it to Modly for a 3D mesh.',
        model: 'comfyui',
        metadata: { delivery_type: 'media_job_status', backend: 'comfyui', stage: 'mesh_source_image' },
      });
      setComposer('');
      setActiveConversation(await edisonApi.getConversation(conversation.id));
      const imageJob = await edisonApi.createMediaJob({
        job_type: 'image',
        title: `mesh source: ${conversationTitle(content)}`,
        prompt: `${content}. Single clear subject, product render, centered object, neutral background, full object visible for image-to-3D reconstruction.`,
        metadata: {
          source: 'chat-mesh-source',
          conversation_id: conversation.id,
          deliver_to_chat: false,
          width: 1024,
          height: 1024,
          steps: 30,
          cfg: 6.5,
          sampler_name: 'dpmpp_2m',
          scheduler: 'karras',
          enhance_prompt: true,
        },
      });
      setActiveConversation((current) => updateMediaStatusMessage(current, prepMessage.id, imageJob));
      const completedImageJob = await waitForMediaJobCompletion(imageJob.id, conversation.id, prepMessage.id);
      if (completedImageJob.status !== 'complete' || !completedImageJob.result_artifact_id) {
        await refreshMediaSurface();
        return;
      }
      const artifacts = await edisonApi.listArtifacts(80);
      sourceArtifact = artifacts.find((artifact) => artifact.id === completedImageJob.result_artifact_id) ?? null;
      if (!sourceArtifact) {
        await edisonApi.addMessage(conversation.id, {
          role: 'assistant',
          content: 'I generated the source image, but could not find the saved artifact to pass into Modly.',
          model: 'modly',
          metadata: { delivery_type: 'media_job_error', media_job: completedImageJob },
        });
        setActiveConversation(await edisonApi.getConversation(conversation.id));
        await refreshMediaSurface();
        return;
      }
    }
    if (jobType === 'mesh' && !sourceArtifact) {
      await edisonApi.addMessage(conversation.id, {
        role: 'assistant',
        content: 'Modly needs a source image before it can build a mesh, and I could not prepare one for this request.',
        model: 'modly',
        metadata: { delivery_type: 'media_job_error', backend: 'modly' },
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

  async function waitForMediaJobCompletion(
    jobId: string,
    conversationId: string,
    statusMessageId?: string,
  ): Promise<JobRecord> {
    let latest = await edisonApi.syncMediaJob(jobId);
    for (let attempt = 0; attempt < 120; attempt += 1) {
      if (statusMessageId) {
        setActiveConversation((current) => updateMediaStatusMessage(current, statusMessageId, latest));
      }
      if (latest.status === 'complete' || ['error', 'cancelled', 'setup_required'].includes(latest.status)) {
        if (['error', 'cancelled', 'setup_required'].includes(latest.status)) {
          await edisonApi.addMessage(conversationId, {
            role: 'assistant',
            content: mediaJobFailureLine(latest),
            model: latest.backend,
            metadata: {
              delivery_type: 'media_job_error',
              media_job: latest,
            },
          });
        }
        return latest;
      }
      await sleep(2500);
      latest = await edisonApi.syncMediaJob(jobId);
    }
    return latest;
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

      const [nextMediaStatus, nextMediaModes, nextToyBoxStatus, nextMediaJobs, nextArtifacts] = await Promise.all([
        edisonApi.getMediaStatus(),
        edisonApi.listMediaModes(),
        edisonApi.getToyBoxStatus(),
        edisonApi.listJobs(),
        edisonApi.listArtifacts(),
      ]);
      setMediaStatus(nextMediaStatus);
      setMediaModes(nextMediaModes);
      setToyBoxStatus(nextToyBoxStatus);
      setMediaJobs(nextMediaJobs.filter((job) => ['image', 'image_edit', 'video', 'mesh', 'audio', 'document', 'code'].includes(job.job_type)));
      setMediaArtifacts(nextArtifacts.filter((artifact) => ['image', 'video', 'mesh', 'audio', 'document', 'code', 'data'].includes(artifact.kind)));
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

  async function refreshAgentRuns(selectedRunId?: string | null) {
    try {
      const runs = await edisonApi.listAgentRuns();
      setAgentRuns(runs);
      const runId = selectedRunId ?? activeAgentRun?.id ?? runs[0]?.id;
      if (runId) {
        setActiveAgentRun(await edisonApi.getAgentRun(runId));
      } else {
        setActiveAgentRun(null);
      }
    } catch {
      setAgentRuns([]);
      setActiveAgentRun(null);
    }
  }

  async function refreshSystemSurface() {
    try {
      const [
        nextStatus,
        nextCapabilities,
        nextFanControls,
        nextHardwareStatus,
        nextHardwareControlCenter,
        nextVisionStatus,
      ] = await Promise.all([
        edisonApi.getStatus(),
        edisonApi.getCapabilities(),
        edisonApi.getFanControls(),
        edisonApi.getHardwareStatus(),
        edisonApi.getHardwareControlCenter(),
        edisonApi.getCameraVisionStatus(),
      ]);
      setStatus(nextStatus);
      setCapabilityStatus(nextCapabilities);
      setFanControls(nextFanControls);
      setHardwareStatus(nextHardwareStatus);
      setHardwareControlCenter(nextHardwareControlCenter);
      setCameraVisionStatus(nextVisionStatus);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'System status failed');
    }
  }

  async function refreshSettingsSurface() {
    try {
      const [nextRuntimeSettings, nextMediaStatus, nextToyBoxStatus, nextHardwareStatus] = await Promise.all([
        edisonApi.getRuntimeSettings(),
        edisonApi.getMediaStatus(),
        edisonApi.getToyBoxStatus(),
        edisonApi.getHardwareStatus(),
      ]);
      setRuntimeSettings(nextRuntimeSettings);
      setMediaStatus(nextMediaStatus);
      setToyBoxStatus(nextToyBoxStatus);
      setHardwareStatus(nextHardwareStatus);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Settings failed to load');
    }
  }

  async function saveRuntimeSettings(payload: Parameters<typeof edisonApi.updateRuntimeSettings>[0]) {
    setError(null);
    try {
      const saved = await edisonApi.updateRuntimeSettings(payload);
      setRuntimeSettings(saved);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Settings failed to save');
    }
  }

  async function captureCameraSnapshot(devicePath?: string | null) {
    setIsCameraBusy(true);
    setIsCameraFeedPaused(true);
    setError(null);
    try {
      await sleep(1200);
      await edisonApi.captureCameraSnapshot({
        device_path: devicePath ?? null,
        width: 1280,
        height: 720,
        input_format: 'mjpeg',
        title: 'Brio camera snapshot',
      });
      const [nextHardwareStatus, nextArtifacts] = await Promise.all([
        edisonApi.getHardwareStatus(),
        edisonApi.listArtifacts(24),
      ]);
      setHardwareStatus(nextHardwareStatus);
      setCameraVisionStatus(await edisonApi.getCameraVisionStatus(devicePath ?? undefined));
      setMediaArtifacts(nextArtifacts);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Camera snapshot failed');
    } finally {
      setIsCameraFeedPaused(false);
      setIsCameraBusy(false);
    }
  }

  async function analyzeCameraFrame(devicePath?: string | null) {
    setIsCameraBusy(true);
    setIsCameraFeedPaused(true);
    setError(null);
    try {
      await sleep(1200);
      const analysis = await edisonApi.analyzeCameraFrame({
        device_path: devicePath ?? null,
        width: 1280,
        height: 720,
        input_format: 'mjpeg',
        title: 'Brio camera AI frame',
        prompt: 'Analyze this Edison camera frame in under 90 words. Start with one scene sentence, then list the most important objects and one useful next action.',
      });
      setCameraAnalysis(analysis);
      const [nextHardwareStatus, nextVisionStatus, nextArtifacts] = await Promise.all([
        edisonApi.getHardwareStatus(),
        edisonApi.getCameraVisionStatus(devicePath ?? undefined),
        edisonApi.listArtifacts(24),
      ]);
      setHardwareStatus(nextHardwareStatus);
      setCameraVisionStatus(nextVisionStatus);
      setMediaArtifacts(nextArtifacts);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Camera analysis failed');
    } finally {
      setIsCameraFeedPaused(false);
      setIsCameraBusy(false);
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
      const [nextStatus, nextControlCenter] = await Promise.all([
        edisonApi.getStatus(),
        edisonApi.getHardwareControlCenter(),
      ]);
      setStatus(nextStatus);
      setHardwareControlCenter(nextControlCenter);
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

  async function createMediaGeneration(mode: MediaGenerationMode, prompt: string, referenceFile?: File | null) {
    setIsMediaBusy(true);
    setError(null);
    try {
      const referenceArtifact = referenceFile ? await edisonApi.uploadArtifact(referenceFile) : null;
      await edisonApi.generateMedia({
        mode,
        prompt,
        reference_artifact_id: referenceArtifact?.id ?? null,
        metadata: {
          source: 'media-studio',
          reference_filename: referenceFile?.name,
        },
      });
      await refreshMediaSurface();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Media generation failed');
    } finally {
      setIsMediaBusy(false);
    }
  }

  async function refreshWorkspaceSurface(path = workspacePath, rootId = activeWorkspaceRootId) {
    setIsWorkspaceBusy(true);
    setError(null);
    try {
      const [nextRoots, nextSummary, nextEntries] = await Promise.all([
        edisonApi.listWorkspaceRoots(),
        edisonApi.getWorkspaceSummary(rootId),
        edisonApi.listWorkspaceFiles(path, rootId),
      ]);
      const nextScan = await edisonApi.getWorkspaceScan(rootId);
      setWorkspaceRoots(nextRoots);
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

  async function selectWorkspaceRoot(rootId: string) {
    setActiveWorkspaceRootId(rootId);
    setWorkspacePath('');
    setWorkspaceFile(null);
    setWorkspaceDraftContent('');
    setWorkspacePatchPreview(null);
    setWorkspaceCommandResult(null);
    setWorkspaceSearchResults([]);
    await refreshWorkspaceSurface('', rootId);
  }

  async function createWorkspaceProject(name: string, prompt: string) {
    if (!name.trim() || !prompt.trim()) {
      return;
    }
    setIsWorkspaceBusy(true);
    setError(null);
    try {
      const project = await edisonApi.createWorkspaceProject({
        name: name.trim(),
        prompt: prompt.trim(),
        initialize_git: true,
      });
      await selectWorkspaceRoot(project.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Project creation failed');
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
      const file = await edisonApi.getWorkspaceFile(entry.path, activeWorkspaceRootId);
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
      const preview = await edisonApi.previewWorkspacePatch(
        {
          path: workspaceFile.path,
          proposed_content: workspaceDraftContent,
        },
        activeWorkspaceRootId,
      );
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
      const result = await edisonApi.applyWorkspacePatch(
        {
          path: workspaceFile.path,
          proposed_content: workspaceDraftContent,
          expected_sha256: workspacePatchPreview.current_sha256,
          approved: true,
        },
        activeWorkspaceRootId,
      );
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
      const result = await edisonApi.runWorkspaceCommand(
        {
          command: command.command,
          cwd: command.cwd,
          timeout_seconds: 120,
          approved: true,
        },
        activeWorkspaceRootId,
      );
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
      const results = await edisonApi.searchWorkspace({ query, max_results: 80 }, activeWorkspaceRootId);
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

  async function ingestKnowledgePreset(preset: KnowledgePreset) {
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
    <div className="app-shell">
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
            <span className={hardwareSummary.hailoReady ? 'status-pill ok' : 'status-pill'}>
              <Zap size={15} /> Hailo {hardwareSummary.hailoLabel}
            </span>
            <span className={hardwareSummary.readyCameras > 0 ? 'status-pill ok' : 'status-pill'}>
              <Camera size={15} /> {hardwareSummary.readyCameras} cameras
            </span>
            <span className="status-pill"><Fan size={15} /> {fanControls?.controllers.length ?? 0} fan controls</span>
          </div>
        </header>

        {error && <div className="error-banner">{friendlyError(error)}</div>}

        {activeView === 'chat' ? (
          <ChatView
            activeConversation={activeConversation}
            activeAgentRun={activeAgentRun}
            agentRuns={agentRuns}
            composer={composer}
            handleSend={handleSend}
            isSending={isSending}
            agentModeEnabled={agentModeEnabled}
            modelSelection={modelSelection}
            setComposer={setComposer}
            setAgentModeEnabled={setAgentModeEnabled}
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
            onSelectAgentRun={async (runId) => {
              setActiveAgentRun(await edisonApi.getAgentRun(runId));
              await refreshAgentRuns(runId);
            }}
          />
        ) : (
          <WorkbenchView
            activeView={activeView}
            groupedModels={groupedModels}
            fanControls={fanControls}
            hardwareControlCenter={hardwareControlCenter}
            hardwareStatus={hardwareStatus}
            cameraVisionStatus={cameraVisionStatus}
            cameraAnalysis={cameraAnalysis}
            artifacts={mediaArtifacts}
            capabilityStatus={capabilityStatus}
            isCameraBusy={isCameraBusy}
            isCameraFeedPaused={isCameraFeedPaused}
            isMediaBusy={isMediaBusy}
            isWorkspaceBusy={isWorkspaceBusy}
            isKnowledgeBusy={isKnowledgeBusy}
            knowledgeNotice={knowledgeNotice}
            knowledgeSearchQuery={knowledgeSearchQuery}
            knowledgeSearchResults={knowledgeSearchResults}
            knowledgeSources={knowledgeSources}
            knowledgeStatus={knowledgeStatus}
            mediaJobs={mediaJobs}
            mediaModes={mediaModes}
            mediaStatus={mediaStatus}
            models={models}
            runtimeSettings={runtimeSettings}
            toyBoxStatus={toyBoxStatus}
            activeWorkspaceRootId={activeWorkspaceRootId}
            onCreateMediaJob={createMediaReadinessJob}
            onCreateMediaGeneration={createMediaGeneration}
            onCreateWorkspaceProject={createWorkspaceProject}
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
            onSaveRuntimeSettings={saveRuntimeSettings}
            onCaptureCameraSnapshot={captureCameraSnapshot}
            onAnalyzeCameraFrame={analyzeCameraFrame}
            onUpdateFanControl={updateFanControl}
            onUseArtifactInChat={useArtifactInChat}
            onRefreshWorkspace={() => refreshWorkspaceSurface(workspacePath)}
            onKnowledgeSearch={handleKnowledgeSearch}
            onWorkspaceParent={openWorkspaceParent}
            onWorkspaceSearch={handleWorkspaceSearch}
            onSelectWorkspaceRoot={selectWorkspaceRoot}
            sessionState={sessionState}
            status={status}
            workspaceCommandResult={workspaceCommandResult}
            workspaceEntries={workspaceEntries}
            workspaceDraftContent={workspaceDraftContent}
            workspaceFile={workspaceFile}
            workspacePath={workspacePath}
            workspacePatchPreview={workspacePatchPreview}
            workspaceRoots={workspaceRoots}
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
    </div>
  );
}

function ChatView({
  activeConversation,
  activeAgentRun,
  agentModeEnabled,
  agentRuns,
  composer,
  handleSend,
  isSending,
  modelSelection,
  setComposer,
  setAgentModeEnabled,
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
  onSelectAgentRun,
}: {
  activeConversation: ConversationWithMessages | null;
  activeAgentRun: AgentRunWithEvents | null;
  agentModeEnabled: boolean;
  agentRuns: AgentRunRecord[];
  composer: string;
  handleSend: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  isSending: boolean;
  modelSelection: ModelSelection | null;
  setComposer: (value: string) => void;
  setAgentModeEnabled: (value: boolean) => void;
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
  onSelectAgentRun: (runId: string) => Promise<void>;
}) {
  const selectedModelName = modelSelection?.model.display_name ?? 'Model lane';
  const intentLabel = modelSelection?.mode
    ? `Intent ${modelSelection.mode.replace('_', ' ')}`
    : 'Intent auto';
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
      <AgentRunDock
        activeRun={activeAgentRun}
        runs={agentRuns}
        onSelectRun={onSelectAgentRun}
      />
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
                <ArtifactPreview artifact={artifact} url={edisonApi.artifactDownloadUrl(artifact.id)} />
                <div>
                  <strong>{artifact.title}</strong>
                  <span>{artifact.kind} / {artifact.mime_type ?? 'file'}</span>
                </div>
                <div className="artifact-card-actions">
                  <button className="secondary-button" onClick={() => onUseArtifactInChat(artifact)} type="button">
                    View In Chat
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="composer-panel" aria-label="Message composer">
        <div className="composer-meta">
          <span>{intentLabel}</span>
          <span>{selectedModelName}</span>
          <span>{modelSelection?.model.status.replace('_', ' ') ?? 'Select a lane'}</span>
          <button
            className={agentModeEnabled ? 'composer-toggle active' : 'composer-toggle'}
            onClick={() => setAgentModeEnabled(!agentModeEnabled)}
            title="Let Edison plan and use tool-capable agent workflows"
            type="button"
          >
            <Waypoints size={14} />
            <span>Agent</span>
          </button>
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

function AgentRunDock({
  activeRun,
  runs,
  onSelectRun,
}: {
  activeRun: AgentRunWithEvents | null;
  runs: AgentRunRecord[];
  onSelectRun: (runId: string) => Promise<void>;
}) {
  const visibleRuns = runs.slice(0, 4);
  return (
    <section className="agent-run-dock" aria-label="Agent run dashboard">
      <div className="agent-run-dock-header">
        <div>
          <span className="section-label">Agent runs</span>
          <strong>{activeRun?.title ?? 'No tracked run selected'}</strong>
        </div>
        <span className={`run-status ${activeRun?.status ?? 'queued'}`}>
          {activeRun ? formatRunStatus(activeRun.status) : `${runs.length} total`}
        </span>
      </div>
      <div className="agent-run-dock-grid">
        <div className="agent-run-list">
          {visibleRuns.map((run) => (
            <button
              className={activeRun?.id === run.id ? 'agent-run-list-item active' : 'agent-run-list-item'}
              key={run.id}
              onClick={() => void onSelectRun(run.id)}
              type="button"
            >
              <span>{run.title}</span>
              <small>{formatRunStatus(run.status)} / {run.progress_percent}%</small>
            </button>
          ))}
          {visibleRuns.length === 0 && (
            <div className="empty-line">Toggle Agent in the composer to start a tracked run.</div>
          )}
        </div>
        <div className="agent-run-detail">
          {activeRun ? (
            <>
              <div className="run-progress-line">
                <progress max={100} value={activeRun.progress_percent} />
                <span>{activeRun.current_step ?? 'Working'}</span>
              </div>
              <div className="agent-run-events">
                {activeRun.events.slice(-5).map((event) => (
                  <article className={`agent-run-event ${event.kind}`} key={event.id}>
                    <div>
                      <span>{event.kind.replace('_', ' ')}</span>
                      <small>{formatDateTime(event.created_at)}</small>
                    </div>
                    <strong>{event.title}</strong>
                    {event.body && <p>{event.body}</p>}
                  </article>
                ))}
              </div>
            </>
          ) : (
            <div className="agent-run-empty">
              <Waypoints size={20} />
              <span>Agent run timelines will appear here.</span>
            </div>
          )}
        </div>
      </div>
    </section>
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
          {artifacts.map((artifact) => <MediaArtifactInlineCard artifact={artifact} key={artifact.id} />)}
        </div>
      )}
    </div>
  );
}

function MediaArtifactInlineCard({ artifact }: { artifact: ArtifactRecord }) {
  const downloadUrl = edisonApi.artifactDownloadUrl(artifact.id);
  return (
    <article className={`message-artifact-card ${artifact.kind}`}>
      <ArtifactPreview artifact={artifact} url={downloadUrl} />
      <div className="message-artifact-meta">
        <span className="section-label">{artifact.kind}</span>
        <strong>{artifact.title}</strong>
        <span>{artifact.mime_type ?? 'generated file'}</span>
      </div>
      <div className="message-artifact-actions">
        <a className="secondary-button" href={downloadUrl} target="_blank" rel="noreferrer">
          Open
        </a>
        <a className="secondary-button" download href={downloadUrl}>
          Download
        </a>
      </div>
    </article>
  );
}

function ArtifactPreview({ artifact, url }: { artifact: ArtifactRecord; url: string }) {
  if (artifact.kind === 'image') {
    return <img alt={artifact.title} className="artifact-preview-media" src={url} />;
  }
  if (artifact.kind === 'video') {
    return <video className="artifact-preview-media" controls preload="metadata" src={url} />;
  }
  if (artifact.kind === 'audio') {
    return (
      <div className="artifact-audio-preview">
        <Activity size={22} />
        <audio controls src={url} />
      </div>
    );
  }
  if (artifact.kind === 'mesh') {
    return <MeshArtifactViewer title={artifact.title} url={url} />;
  }
  return (
    <div className="artifact-file-preview">
      <FileText size={24} />
      <span>{artifact.kind}</span>
    </div>
  );
}

function MeshArtifactViewer({ title, url }: { title: string; url: string }) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [viewerState, setViewerState] = useState('Loading 3D preview');

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) {
      return undefined;
    }
    const mountElement = mount;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf7f8f7);
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0.35, 3.1);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    mountElement.innerHTML = '';
    mountElement.appendChild(renderer.domElement);

    const keyLight = new THREE.DirectionalLight(0xffffff, 2.8);
    keyLight.position.set(3, 4, 4);
    scene.add(keyLight);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8da19b, 1.8));

    const grid = new THREE.GridHelper(3, 12, 0xc9d2cf, 0xe2e7e4);
    grid.position.y = -0.82;
    scene.add(grid);

    let modelRoot: THREE.Object3D | null = null;
    let frameId = 0;
    const loader = new GLTFLoader();

    function resize() {
      const width = Math.max(260, mountElement.clientWidth);
      const height = Math.max(220, mountElement.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mountElement);
    resize();

    loader.load(
      url,
      (gltf) => {
        modelRoot = gltf.scene;
        const bounds = new THREE.Box3().setFromObject(modelRoot);
        const size = new THREE.Vector3();
        const center = new THREE.Vector3();
        bounds.getSize(size);
        bounds.getCenter(center);
        const largestAxis = Math.max(size.x, size.y, size.z) || 1;
        modelRoot.position.sub(center);
        modelRoot.scale.setScalar(1.7 / largestAxis);
        scene.add(modelRoot);
        setViewerState('Drag-free orbit preview');
      },
      undefined,
      () => setViewerState('3D preview could not load'),
    );

    const animate = () => {
      frameId = window.requestAnimationFrame(animate);
      if (modelRoot) {
        modelRoot.rotation.y += 0.008;
      }
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      window.cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      scene.traverse((object) => {
        const mesh = object as THREE.Mesh;
        mesh.geometry?.dispose();
        const material = mesh.material;
        if (Array.isArray(material)) {
          material.forEach((item) => item.dispose());
        } else {
          material?.dispose();
        }
      });
      renderer.dispose();
      if (renderer.domElement.parentNode === mountElement) {
        mountElement.removeChild(renderer.domElement);
      }
    };
  }, [url]);

  return (
    <div className="mesh-artifact-viewer" aria-label={`3D preview of ${title}`}>
      <div ref={mountRef} />
      <span>{viewerState}</span>
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
  activeWorkspaceRootId,
  activeView,
  artifacts,
  capabilityStatus,
  fanControls,
  groupedModels,
  hardwareControlCenter,
  hardwareStatus,
  cameraVisionStatus,
  cameraAnalysis,
  isCameraBusy,
  isCameraFeedPaused,
  isMediaBusy,
  isWorkspaceBusy,
  isKnowledgeBusy,
  knowledgeNotice,
  knowledgeSearchQuery,
  knowledgeSearchResults,
  knowledgeSources,
  knowledgeStatus,
  mediaJobs,
  mediaModes,
  mediaStatus,
  models,
  runtimeSettings,
  toyBoxStatus,
  onCreateWorkspaceProject,
  onCreateMediaJob,
  onCreateMediaGeneration,
  onCaptureCameraSnapshot,
  onAnalyzeCameraFrame,
  onOpenCompareConversation,
  onRefreshConversations,
  onSaveRuntimeSettings,
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
  onSelectWorkspaceRoot,
  sessionState,
  status,
  workspaceCommandResult,
  workspaceEntries,
  workspaceDraftContent,
  workspaceFile,
  workspacePath,
  workspacePatchPreview,
  workspaceRoots,
  workspaceScan,
  workspaceSearchQuery,
  workspaceSearchResults,
  workspaceSummary,
  setKnowledgeSearchQuery,
  setWorkspaceDraftContent,
  setWorkspaceSearchQuery,
}: {
  activeWorkspaceRootId: string;
  activeView: ViewId;
  artifacts: ArtifactRecord[];
  capabilityStatus: CapabilityStatus | null;
  fanControls: GPUFanControlSnapshot | null;
  groupedModels: { ready: ModelProfile[]; pending: ModelProfile[] };
  hardwareControlCenter: HardwareControlCenter | null;
  hardwareStatus: HardwareStatus | null;
  cameraVisionStatus: CameraVisionStatus | null;
  cameraAnalysis: CameraFrameAnalysisResponse | null;
  isCameraBusy: boolean;
  isCameraFeedPaused: boolean;
  isMediaBusy: boolean;
  isWorkspaceBusy: boolean;
  isKnowledgeBusy: boolean;
  knowledgeNotice: string | null;
  knowledgeSearchQuery: string;
  knowledgeSearchResults: KnowledgeSearchMatch[];
  knowledgeSources: KnowledgeSourceRecord[];
  knowledgeStatus: KnowledgeStatus | null;
  mediaJobs: JobRecord[];
  mediaModes: MediaGenerationModeRecord[];
  mediaStatus: MediaSystemStatus | null;
  models: ModelProfile[];
  runtimeSettings: RuntimeSettingsRecord | null;
  toyBoxStatus: ToyBoxManagerStatus | null;
  onCreateWorkspaceProject: (name: string, prompt: string) => Promise<void>;
  onCreateMediaJob: (jobType: JobType, title: string, prompt: string) => Promise<void>;
  onCreateMediaGeneration: (mode: MediaGenerationMode, prompt: string, referenceFile?: File | null) => Promise<void>;
  onCaptureCameraSnapshot: (devicePath?: string | null) => Promise<void>;
  onAnalyzeCameraFrame: (devicePath?: string | null) => Promise<void>;
  onOpenCompareConversation: (conversationId: string) => Promise<void>;
  onRefreshConversations: () => Promise<void>;
  onSaveRuntimeSettings: (payload: Parameters<typeof edisonApi.updateRuntimeSettings>[0]) => Promise<void>;
  onIngestKnowledgeLocal: (payload: { path: string; glob: string; max_files: number }) => Promise<void>;
  onIngestKnowledgePreset: (preset: KnowledgePreset) => Promise<void>;
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
  onSelectWorkspaceRoot: (rootId: string) => Promise<void>;
  sessionState: SessionStateRecord | null;
  status: SystemStatus | null;
  workspaceCommandResult: WorkspaceCommandRunResult | null;
  workspaceEntries: WorkspaceEntry[];
  workspaceDraftContent: string;
  workspaceFile: WorkspaceFile | null;
  workspacePath: string;
  workspacePatchPreview: WorkspacePatchPreview | null;
  workspaceRoots: WorkspaceRootRecord[];
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
  if (activeView === 'research') {
    return (
      <ResearchView
        models={models}
        onOpenConversation={onOpenCompareConversation}
        onRefreshConversations={onRefreshConversations}
      />
    );
  }
  if (activeView === 'organizer') {
    return <OrganizerView />;
  }
  if (activeView === 'documents') {
    return <DocumentsView />;
  }
  if (activeView === 'search') {
    return <SearchCompareView />;
  }
  if (activeView === 'code') {
    return (
      <CodeWorkspaceView
        activeRootId={activeWorkspaceRootId}
        commandResult={workspaceCommandResult}
        entries={workspaceEntries}
        draftContent={workspaceDraftContent}
        file={workspaceFile}
        isBusy={isWorkspaceBusy}
        onApplyPatch={onApplyWorkspacePatch}
        onCreateProject={onCreateWorkspaceProject}
        onOpenEntry={onOpenWorkspaceEntry}
        onParent={onWorkspaceParent}
        onPreviewPatch={onPreviewWorkspacePatch}
        onRefresh={onRefreshWorkspace}
        onRunCommand={onRunWorkspaceCommand}
        onAddChatContextPath={onAddChatContextPath}
        onSearch={onWorkspaceSearch}
        onSelectRoot={onSelectWorkspaceRoot}
        path={workspacePath}
        patchPreview={workspacePatchPreview}
        roots={workspaceRoots}
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
        modes={mediaModes}
        mediaStatus={mediaStatus}
        toyBoxStatus={toyBoxStatus}
        onCreateJob={onCreateMediaJob}
        onCreateGeneration={onCreateMediaGeneration}
        onRefresh={onRefreshMedia}
        onUseArtifactInChat={onUseArtifactInChat}
      />
    );
  }
  if (activeView === 'gallery') {
    return (
      <GalleryView
        artifacts={artifacts}
        jobs={mediaJobs}
        onRefresh={onRefreshMedia}
        onUseArtifactInChat={onUseArtifactInChat}
        runtimeSettings={runtimeSettings}
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
        capabilityStatus={capabilityStatus}
        groupedModels={groupedModels}
        hardwareControlCenter={hardwareControlCenter}
        hardwareStatus={hardwareStatus}
        cameraVisionStatus={cameraVisionStatus}
        cameraAnalysis={cameraAnalysis}
        isCameraBusy={isCameraBusy}
        isCameraFeedPaused={isCameraFeedPaused}
        models={models}
        onCaptureCameraSnapshot={onCaptureCameraSnapshot}
        onAnalyzeCameraFrame={onAnalyzeCameraFrame}
        onRefresh={onRefreshSystem}
        onUpdateFanControl={onUpdateFanControl}
        status={status}
      />
    );
  }
  return (
    <SettingsView
      fanControls={fanControls}
      hardwareStatus={hardwareStatus}
      mediaStatus={mediaStatus}
      runtimeSettings={runtimeSettings}
      sessionState={sessionState}
      status={status}
      toyBoxStatus={toyBoxStatus}
      onSave={onSaveRuntimeSettings}
      workspaceRoots={workspaceRoots}
    />
  );
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

function ResearchView({
  models,
  onOpenConversation,
  onRefreshConversations,
}: {
  models: ModelProfile[];
  onOpenConversation: (conversationId: string) => Promise<void>;
  onRefreshConversations: () => Promise<void>;
}) {
  const readyChatModels = useMemo(
    () => models.filter((model) => model.status === 'ready' && model.capabilities.includes('chat')),
    [models],
  );
  const preferredModel = useMemo(
    () => readyChatModels.find((model) => model.capabilities.includes('reasoning')) ?? readyChatModels[0],
    [readyChatModels],
  );
  const [topic, setTopic] = useState('');
  const [depth, setDepth] = useState<ResearchDepth>('deep');
  const [includeKnowledge, setIncludeKnowledge] = useState(true);
  const [sourceLimit, setSourceLimit] = useState(8);
  const [run, setRun] = useState<CompareRun | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runResearch() {
    const trimmedTopic = topic.trim();
    if (isRunning) {
      return;
    }
    if (!trimmedTopic) {
      setError('Enter a research topic.');
      return;
    }
    if (!preferredModel) {
      setError('No ready chat model is available for research.');
      return;
    }

    const startedAt = Date.now();
    const runId = `research-${startedAt}`;
    let streamedContent = '';
    setError(null);
    setIsRunning(true);
    setRun({
      id: runId,
      modelId: preferredModel.id,
      displayName: preferredModel.display_name,
      status: 'streaming',
      content: '',
      startedAt,
    });

    try {
      const response = await edisonApi.streamChatTurn({
        conversation_id: null,
        message: buildResearchPrompt(trimmedTopic, depth, includeKnowledge, sourceLimit),
        mode: 'reasoning',
        preferred_model: preferredModel.id,
        memory_enabled: true,
        include_workspace_context: false,
        include_knowledge_context: includeKnowledge,
        knowledge_query: trimmedTopic,
        max_knowledge_context_matches: includeKnowledge ? sourceLimit : 1,
      }, {
        onStart: (event) => {
          setRun((current) => (
            current?.id === runId ? { ...current, conversationId: event.conversation_id } : current
          ));
        },
        onToken: (delta) => {
          streamedContent += delta;
          setRun((current) => (
            current?.id === runId ? { ...current, content: streamedContent } : current
          ));
        },
        onError: (detail) => {
          setRun((current) => (
            current?.id === runId ? { ...current, status: 'error', error: detail, finishedAt: Date.now() } : current
          ));
        },
      });
      setRun((current) => (
        current?.id === runId
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
      const detail = caught instanceof Error ? caught.message : 'Research run failed';
      setError(detail);
      setRun((current) => (
        current?.id === runId ? { ...current, status: 'error', error: detail, finishedAt: Date.now() } : current
      ));
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <section className="workbench-view research-view" aria-label="Research">
      <div className="view-heading">
        <BookOpen size={26} />
        <h3>Research</h3>
        <div className="view-actions">
          <button
            className="secondary-button icon-text-button"
            disabled={!topic.trim() || isRunning}
            onClick={() => void runResearch()}
            type="button"
          >
            <Send size={16} />
            {isRunning ? 'Researching' : 'Run Research'}
          </button>
        </div>
      </div>

      <div className="research-shell">
        <aside className="research-control-panel" aria-label="Research controls">
          <label htmlFor="research-topic">Topic</label>
          <textarea
            id="research-topic"
            onChange={(event) => setTopic(event.target.value)}
            placeholder="Research a product, repo, hardware plan, paper, or implementation question"
            rows={6}
            value={topic}
          />
          <div className="research-depth-row" aria-label="Research depth">
            {researchDepthOptions.map((option) => (
              <button
                className={depth === option.value ? 'active' : ''}
                key={option.value}
                onClick={() => setDepth(option.value)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="research-toggle-row">
            <label>
              <input
                checked={includeKnowledge}
                onChange={(event) => setIncludeKnowledge(event.target.checked)}
                type="checkbox"
              />
              Use RAG
            </label>
          </div>
          <label htmlFor="research-source-limit">Source matches: {sourceLimit}</label>
          <input
            id="research-source-limit"
            max={12}
            min={3}
            onChange={(event) => setSourceLimit(Number(event.target.value))}
            type="range"
            value={sourceLimit}
          />
          <div className="research-model-line">
            <span>Model</span>
            <strong>{preferredModel?.display_name ?? 'No ready chat model'}</strong>
          </div>
          {error && <div className="error-banner compact">{error}</div>}
        </aside>

        <section className="research-results-panel" aria-label="Research report">
          {!run ? (
            <div className="research-empty">
              <BookOpen size={30} />
              <strong>Turn a question into a source-aware report.</strong>
              <span>Edison uses the local knowledge index when enabled and saves each research run as a chat.</span>
            </div>
          ) : (
            <article className="research-report-card">
              <div className="compare-result-header">
                <div>
                  <strong>{run.displayName}</strong>
                  <span>{run.modelId}</span>
                </div>
                <small className={`compare-status ${run.status}`}>{run.status}</small>
              </div>
              <div className="compare-result-body">
                {run.content ? (
                  <MessageContent content={run.content} metadata={{}} />
                ) : run.status === 'streaming' ? (
                  <div className="typing-indicator" aria-label="Research is streaming">
                    <span />
                    <span />
                    <span />
                  </div>
                ) : (
                  <p>{run.error ?? 'No research output.'}</p>
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
          )}
        </section>
      </div>
    </section>
  );
}

function OrganizerView() {
  const [kind, setKind] = useState<OrganizerKind>('task');
  const [items, setItems] = useState<OrganizerItemRecord[]>([]);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [dueAt, setDueAt] = useState('');
  const [tags, setTags] = useState('');
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refreshItems(nextKind = kind) {
    setItems(await edisonApi.listOrganizerItems({ kind: nextKind, limit: 100 }));
  }

  useEffect(() => {
    refreshItems().catch((caught) => setError(caught instanceof Error ? caught.message : 'Organizer failed'));
  }, [kind]);

  async function createItem() {
    if (!title.trim() || isBusy) {
      return;
    }
    setIsBusy(true);
    setError(null);
    try {
      await edisonApi.createOrganizerItem({
        kind,
        title: title.trim(),
        body: body.trim(),
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
        tags: parseTagInput(tags),
      });
      setTitle('');
      setBody('');
      setDueAt('');
      setTags('');
      await refreshItems();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Create failed');
    } finally {
      setIsBusy(false);
    }
  }

  async function setItemStatus(item: OrganizerItemRecord, status: OrganizerStatus) {
    setError(null);
    try {
      await edisonApi.updateOrganizerItem(item.id, { status });
      await refreshItems();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Update failed');
    }
  }

  async function deleteItem(item: OrganizerItemRecord) {
    setError(null);
    try {
      await edisonApi.deleteOrganizerItem(item.id);
      await refreshItems();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Delete failed');
    }
  }

  const activeItems = items.filter((item) => item.status === 'active');
  const completedItems = items.filter((item) => item.status !== 'active');

  return (
    <section className="workbench-view organizer-view" aria-label="Organizer">
      <div className="view-heading">
        <CheckSquare2 size={26} />
        <h3>Organizer</h3>
        <div className="view-actions">
          <button
            className="secondary-button icon-text-button"
            disabled={!title.trim() || isBusy}
            onClick={() => void createItem()}
            type="button"
          >
            <Send size={16} />
            Add
          </button>
        </div>
      </div>

      <div className="personal-shell">
        <aside className="personal-control-panel" aria-label="Organizer controls">
          <div className="personal-tabs" aria-label="Organizer type">
            {(['task', 'note', 'calendar'] as OrganizerKind[]).map((option) => (
              <button
                className={kind === option ? 'active' : ''}
                key={option}
                onClick={() => setKind(option)}
                type="button"
              >
                {option === 'calendar' ? 'Calendar' : option === 'task' ? 'Tasks' : 'Notes'}
              </button>
            ))}
          </div>
          <label htmlFor="organizer-title">Title</label>
          <input
            id="organizer-title"
            onChange={(event) => setTitle(event.target.value)}
            placeholder={kind === 'calendar' ? 'Meeting, deadline, reminder' : 'New item'}
            value={title}
          />
          <label htmlFor="organizer-body">Details</label>
          <textarea
            id="organizer-body"
            onChange={(event) => setBody(event.target.value)}
            placeholder="Notes, context, links, or acceptance criteria"
            rows={7}
            value={body}
          />
          <label htmlFor="organizer-due">Due or scheduled</label>
          <input
            id="organizer-due"
            onChange={(event) => setDueAt(event.target.value)}
            type="datetime-local"
            value={dueAt}
          />
          <label htmlFor="organizer-tags">Tags</label>
          <input
            id="organizer-tags"
            onChange={(event) => setTags(event.target.value)}
            placeholder="comma,separated,tags"
            value={tags}
          />
          {error && <div className="error-banner compact">{error}</div>}
        </aside>

        <section className="personal-results-panel" aria-label="Organizer items">
          {items.length === 0 ? (
            <div className="personal-empty">
              <CalendarDays size={30} />
              <strong>No {kind} items yet.</strong>
              <span>Create items here so Edison can keep working context outside a single chat.</span>
            </div>
          ) : (
            <>
              <div className="personal-list-section">
                <h4>Active</h4>
                <div className="personal-card-list">
                  {activeItems.map((item) => (
                    <OrganizerItemCard
                      item={item}
                      key={item.id}
                      onArchive={() => void setItemStatus(item, 'archived')}
                      onComplete={() => void setItemStatus(item, 'done')}
                      onDelete={() => void deleteItem(item)}
                    />
                  ))}
                  {activeItems.length === 0 && <span className="empty-line">Nothing active.</span>}
                </div>
              </div>
              <div className="personal-list-section">
                <h4>Closed</h4>
                <div className="personal-card-list">
                  {completedItems.map((item) => (
                    <OrganizerItemCard
                      item={item}
                      key={item.id}
                      onArchive={() => void setItemStatus(item, 'archived')}
                      onComplete={() => void setItemStatus(item, 'active')}
                      onDelete={() => void deleteItem(item)}
                    />
                  ))}
                  {completedItems.length === 0 && <span className="empty-line">No closed items.</span>}
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </section>
  );
}

function OrganizerItemCard({
  item,
  onArchive,
  onComplete,
  onDelete,
}: {
  item: OrganizerItemRecord;
  onArchive: () => void;
  onComplete: () => void;
  onDelete: () => void;
}) {
  return (
    <article className="personal-card">
      <div>
        <strong>{item.title}</strong>
        <span>{item.due_at ? formatDateTime(item.due_at) : item.kind}</span>
      </div>
      {item.body && <p>{item.body}</p>}
      {item.tags.length > 0 && <small>{item.tags.join(' / ')}</small>}
      <div className="personal-card-actions">
        <button className="secondary-button" onClick={onComplete} type="button">
          {item.status === 'active' ? 'Done' : 'Reopen'}
        </button>
        <button className="secondary-button" onClick={onArchive} type="button">
          Archive
        </button>
        <button className="secondary-button" onClick={onDelete} type="button">
          Delete
        </button>
      </div>
    </article>
  );
}

function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [tags, setTags] = useState('');
  const [isBusy, setIsBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeDocument = documents.find((document) => document.id === activeId) ?? null;

  async function refreshDocuments(nextActiveId = activeId) {
    const loaded = await edisonApi.listDocuments(100);
    setDocuments(loaded);
    const selected = loaded.find((document) => document.id === nextActiveId) ?? loaded[0] ?? null;
    setActiveId(selected?.id ?? null);
    setTitle(selected?.title ?? '');
    setContent(selected?.content ?? '');
    setTags(selected?.tags.join(', ') ?? '');
  }

  useEffect(() => {
    refreshDocuments().catch((caught) => setError(caught instanceof Error ? caught.message : 'Documents failed'));
  }, []);

  async function createDocument() {
    setIsBusy(true);
    setError(null);
    setMessage(null);
    try {
      const created = await edisonApi.createDocument({
        title: 'Untitled document',
        content: '',
        format: 'markdown',
        tags: [],
      });
      await refreshDocuments(created.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Create failed');
    } finally {
      setIsBusy(false);
    }
  }

  async function saveDocument() {
    if (!activeDocument || !title.trim()) {
      return;
    }
    setIsBusy(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await edisonApi.updateDocument(activeDocument.id, {
        title: title.trim(),
        content,
        tags: parseTagInput(tags),
      });
      setMessage('Saved');
      await refreshDocuments(saved.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Save failed');
    } finally {
      setIsBusy(false);
    }
  }

  async function ingestDocument() {
    if (!activeDocument) {
      return;
    }
    setIsBusy(true);
    setError(null);
    setMessage(null);
    try {
      const source = await edisonApi.ingestDocument(activeDocument.id);
      setMessage(`Indexed ${source.chunk_count} knowledge chunks`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Ingest failed');
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <section className="workbench-view documents-view" aria-label="Documents">
      <div className="view-heading">
        <FileText size={26} />
        <h3>Docs</h3>
        <div className="view-actions">
          <button className="secondary-button icon-text-button" onClick={() => void createDocument()} type="button">
            <FileText size={16} />
            New
          </button>
          <button
            className="secondary-button icon-text-button"
            disabled={!activeDocument || !title.trim() || isBusy}
            onClick={() => void saveDocument()}
            type="button"
          >
            <Upload size={16} />
            Save
          </button>
          <button
            className="secondary-button icon-text-button"
            disabled={!activeDocument || isBusy}
            onClick={() => void ingestDocument()}
            type="button"
          >
            <Database size={16} />
            Index
          </button>
        </div>
      </div>

      <div className="documents-shell">
        <aside className="documents-list" aria-label="Saved documents">
          {documents.map((document) => (
            <button
              className={document.id === activeId ? 'active' : ''}
              key={document.id}
              onClick={() => {
                setActiveId(document.id);
                setTitle(document.title);
                setContent(document.content);
                setTags(document.tags.join(', '));
              }}
              type="button"
            >
              <strong>{document.title}</strong>
              <span>{formatDateTime(document.updated_at)}</span>
            </button>
          ))}
          {documents.length === 0 && <span className="empty-line">No documents yet.</span>}
        </aside>

        <section className="document-editor-panel" aria-label="Document editor">
          <label htmlFor="document-title">Title</label>
          <input
            id="document-title"
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Document title"
            value={title}
          />
          <label htmlFor="document-tags">Tags</label>
          <input
            id="document-tags"
            onChange={(event) => setTags(event.target.value)}
            placeholder="research,report,project"
            value={tags}
          />
          <label htmlFor="document-content">Content</label>
          <textarea
            id="document-content"
            onChange={(event) => setContent(event.target.value)}
            placeholder="Draft, edit, and save Markdown or plain text"
            value={content}
          />
          {message && <div className="success-banner compact">{message}</div>}
          {error && <div className="error-banner compact">{error}</div>}
        </section>
      </div>
    </section>
  );
}

function SearchCompareView() {
  const [query, setQuery] = useState('');
  const [providers, setProviders] = useState<SearchProvider[]>(['knowledge', 'workspace', 'documents']);
  const [response, setResponse] = useState<SearchCompareResponse | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleProvider(provider: SearchProvider) {
    setProviders((current) => (
      current.includes(provider)
        ? current.filter((candidate) => candidate !== provider)
        : [...current, provider]
    ));
  }

  async function runSearch() {
    if (!query.trim() || providers.length === 0 || isBusy) {
      return;
    }
    setIsBusy(true);
    setError(null);
    try {
      setResponse(await edisonApi.compareSearch({ query: query.trim(), providers, max_results: 5 }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Search failed');
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <section className="workbench-view search-compare-view" aria-label="Search Compare">
      <div className="view-heading">
        <Search size={26} />
        <h3>Search</h3>
        <div className="view-actions">
          <button
            className="secondary-button icon-text-button"
            disabled={!query.trim() || providers.length === 0 || isBusy}
            onClick={() => void runSearch()}
            type="button"
          >
            <Search size={16} />
            Compare
          </button>
        </div>
      </div>

      <div className="search-compare-shell">
        <aside className="personal-control-panel" aria-label="Search controls">
          <label htmlFor="search-query">Query</label>
          <textarea
            id="search-query"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Compare what Edison knows, what is in the workspace, and what is in saved documents"
            rows={5}
            value={query}
          />
          <div className="search-provider-list">
            {(['knowledge', 'workspace', 'documents'] as SearchProvider[]).map((provider) => (
              <label key={provider}>
                <input
                  checked={providers.includes(provider)}
                  onChange={() => toggleProvider(provider)}
                  type="checkbox"
                />
                {provider}
              </label>
            ))}
          </div>
          {response?.best_provider && <div className="success-banner compact">Best hit count: {response.best_provider}</div>}
          {error && <div className="error-banner compact">{error}</div>}
        </aside>

        <section className="search-results-grid" aria-label="Compared results">
          {providers.map((provider) => {
            const results = response?.results[provider] ?? [];
            return (
              <article className="search-provider-card" key={provider}>
                <div className="search-provider-header">
                  <strong>{provider}</strong>
                  <span>{response?.provider_counts[provider] ?? 0} hits</span>
                </div>
                <div className="search-provider-results">
                  {results.map((result, index) => (
                    <div className="search-result-card" key={`${provider}-${index}-${result.title}`}>
                      <strong>{result.title}</strong>
                      <span>{result.subtitle ?? result.path ?? result.uri ?? provider}</span>
                      <p>{result.snippet}</p>
                      <small>Score {result.score.toFixed(2)}</small>
                    </div>
                  ))}
                  {results.length === 0 && <span className="empty-line">No results yet.</span>}
                </div>
              </article>
            );
          })}
        </section>
      </div>
    </section>
  );
}

function CodeWorkspaceView({
  activeRootId,
  commandResult,
  entries,
  draftContent,
  file,
  isBusy,
  onApplyPatch,
  onCreateProject,
  onOpenEntry,
  onParent,
  onPreviewPatch,
  onRefresh,
  onRunCommand,
  onAddChatContextPath,
  onSearch,
  onSelectRoot,
  path,
  patchPreview,
  roots,
  scan,
  searchQuery,
  searchResults,
  setSearchQuery,
  setDraftContent,
  summary,
}: {
  activeRootId: string;
  commandResult: WorkspaceCommandRunResult | null;
  entries: WorkspaceEntry[];
  draftContent: string;
  file: WorkspaceFile | null;
  isBusy: boolean;
  onApplyPatch: () => Promise<void>;
  onCreateProject: (name: string, prompt: string) => Promise<void>;
  onOpenEntry: (entry: WorkspaceEntry) => Promise<void>;
  onParent: () => Promise<void>;
  onPreviewPatch: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onRunCommand: (command: WorkspaceCommand) => Promise<void>;
  onAddChatContextPath: (path: string) => void;
  onSearch: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onSelectRoot: (rootId: string) => Promise<void>;
  path: string;
  patchPreview: WorkspacePatchPreview | null;
  roots: WorkspaceRootRecord[];
  scan: WorkspaceScan | null;
  searchQuery: string;
  searchResults: WorkspaceSearchMatch[];
  setSearchQuery: (value: string) => void;
  setDraftContent: (value: string) => void;
  summary: WorkspaceSummary | null;
}) {
  const [projectName, setProjectName] = useState('');
  const [projectPrompt, setProjectPrompt] = useState('');
  const topLanguages = Object.entries(summary?.languages ?? {}).slice(0, 3);
  const commandPreview = scan?.commands.slice(0, 6) ?? [];
  const entrypointPreview = scan?.entrypoints.slice(0, 5) ?? [];
  const configPreview = scan?.config_files.slice(0, 6) ?? [];
  const draftChanged = Boolean(file && draftContent !== file.content);
  const activeRoot = roots.find((root) => root.id === activeRootId);

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreateProject(projectName, projectPrompt);
    setProjectName('');
    setProjectPrompt('');
  }

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

      <section className="workspace-root-panel" aria-label="Code Space projects">
        <div className="workspace-root-controls">
          <label htmlFor="workspace-root">Code Space</label>
          <select
            disabled={isBusy}
            id="workspace-root"
            onChange={(event) => void onSelectRoot(event.target.value)}
            value={activeRootId}
          >
            {(roots.length ? roots : [{ id: 'app', name: 'Edison App', path: summary?.root_path ?? '', kind: 'app' as const }]).map((root) => (
              <option key={root.id} value={root.id}>
                {root.name} ({root.kind})
              </option>
            ))}
          </select>
          <span>{activeRoot?.path ?? summary?.root_path ?? 'Workspace root'}</span>
        </div>
        <form className="workspace-project-form" onSubmit={(event) => void handleCreateProject(event)}>
          <input
            aria-label="New project name"
            onChange={(event) => setProjectName(event.target.value)}
            placeholder="New repo name"
            value={projectName}
          />
          <input
            aria-label="New project brief"
            onChange={(event) => setProjectPrompt(event.target.value)}
            placeholder="What should Edison build here?"
            value={projectPrompt}
          />
          <button className="secondary-button icon-text-button" disabled={isBusy || !projectName.trim() || !projectPrompt.trim()} type="submit">
            <Folder size={16} />
            Create
          </button>
        </form>
      </section>

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
  onIngestPreset: (preset: KnowledgePreset) => Promise<void>;
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
  const presetButtons: Array<{ preset: KnowledgePreset; label: string }> = [
    { preset: 'ai-foundations', label: 'AI Foundations' },
    { preset: 'coding-core', label: 'Coding Core' },
    { preset: 'edison-ops', label: 'Edison Ops' },
    { preset: 'odysseus-features', label: 'Odysseus Map' },
    { preset: 'mcp-agents', label: 'MCP Agents' },
    { preset: 'local-ai-hardware', label: 'Local Hardware' },
  ];

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
            {presetButtons.map((button) => (
              <button
                className="secondary-button"
                disabled={isBusy}
                key={button.preset}
                onClick={() => void onIngestPreset(button.preset)}
                type="button"
              >
                {button.label}
              </button>
            ))}
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
  modes,
  mediaStatus,
  toyBoxStatus,
  onCreateJob,
  onCreateGeneration,
  onRefresh,
  onUseArtifactInChat,
}: {
  artifacts: ArtifactRecord[];
  isMediaBusy: boolean;
  jobs: JobRecord[];
  modes: MediaGenerationModeRecord[];
  mediaStatus: MediaSystemStatus | null;
  toyBoxStatus: ToyBoxManagerStatus | null;
  onCreateJob: (jobType: JobType, title: string, prompt: string) => Promise<void>;
  onCreateGeneration: (mode: MediaGenerationMode, prompt: string, referenceFile?: File | null) => Promise<void>;
  onRefresh: () => Promise<void>;
  onUseArtifactInChat: (artifact: ArtifactRecord) => void;
}) {
  const [activePanel, setActivePanel] = useState<'generate' | 'minecraft' | 'toybox' | 'outputs'>('generate');
  const modeOptions = modes.length ? modes : fallbackMediaModes();
  const [selectedMode, setSelectedMode] = useState<MediaGenerationMode>('image');
  const [mediaPrompt, setMediaPrompt] = useState('');
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const activeMode = modeOptions.find((mode) => mode.id === selectedMode) ?? modeOptions[0];
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
  const minecraftModes = modeOptions.filter((mode) => mode.group === 'minecraft');
  const toyboxPages = toyboxManagerPages();
  const toyboxLaneCards = toyBoxStatus?.lanes.length
    ? toyBoxStatus.lanes.map((lane) => ({
        id: lane.id,
        title: lane.title,
        description: lane.description,
        lanes: lane.connected_integrations,
        status: lane.status,
        icon: toyboxIconForLane(lane.id),
      }))
    : toyboxPages.map((page) => ({ ...page, id: page.title, status: undefined as string | undefined }));

  function useMode(mode: MediaGenerationMode) {
    setSelectedMode(mode);
    setActivePanel('generate');
  }

  async function submitGeneration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const prompt = mediaPrompt.trim();
    if (!prompt || isMediaBusy || !activeMode) {
      return;
    }
    await onCreateGeneration(activeMode.id, prompt, referenceFile);
    setMediaPrompt('');
    setReferenceFile(null);
  }

  return (
    <section className="workbench-view" aria-label="Media Studio">
      <div className="view-heading">
        <GalleryHorizontalEnd size={26} />
        <h3>Media Studio</h3>
        <button className="secondary-button" onClick={() => void onRefresh()} type="button">Refresh</button>
      </div>
      <div className="media-panel-tabs" role="tablist" aria-label="Media Studio sections">
        {[
          ['generate', 'Generate'],
          ['minecraft', 'Minecraft AI Suite'],
          ['toybox', 'ToyBox3D Farm'],
          ['outputs', 'Outputs'],
        ].map(([panelId, label]) => (
          <button
            className={activePanel === panelId ? 'mode-button active' : 'mode-button'}
            key={panelId}
            onClick={() => setActivePanel(panelId as typeof activePanel)}
            type="button"
          >
            {label}
          </button>
        ))}
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
      {activePanel === 'generate' && (
        <>
          <section className="media-generator-panel" aria-label="Generation mode prompt">
            <div className="media-mode-grid">
              {modeOptions.map((mode) => (
                <button
                  className={selectedMode === mode.id ? 'media-mode-card active' : 'media-mode-card'}
                  key={mode.id}
                  onClick={() => setSelectedMode(mode.id)}
                  type="button"
                >
                  <span>{mode.group}</span>
                  <strong>{mode.label}</strong>
                  <small>{mode.output_hint}</small>
                </button>
              ))}
            </div>
            <form className="media-generate-form" onSubmit={(event) => void submitGeneration(event)}>
              <div>
                <span className="section-label">Selected mode</span>
                <strong>{activeMode?.label ?? 'Image'}</strong>
                <p>{activeMode?.description}</p>
              </div>
              <textarea
                aria-label="Generation prompt"
                onChange={(event) => setMediaPrompt(event.target.value)}
                placeholder={activeMode?.prompt_hint ?? 'Describe what Edison should generate'}
                rows={5}
                value={mediaPrompt}
              />
              <div className="reference-upload-row">
                <label htmlFor="media-reference-upload">Reference image</label>
                <input
                  accept="image/*"
                  disabled={!activeMode?.reference_supported}
                  id="media-reference-upload"
                  onChange={(event) => setReferenceFile(event.target.files?.[0] ?? null)}
                  type="file"
                />
                <span>{referenceFile ? referenceFile.name : activeMode?.reference_supported ? 'Optional' : 'Not used for this mode'}</span>
              </div>
              <button className="apply-button icon-text-button" disabled={!mediaPrompt.trim() || isMediaBusy} type="submit">
                <Send size={16} />
                {isMediaBusy ? 'Generating' : 'Generate'}
              </button>
            </form>
          </section>
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
        </>
      )}
      {activePanel === 'minecraft' && (
        <section className="minecraft-suite-panel" aria-label="Minecraft AI Suite">
          <div className="section-heading">
            <Box size={18} />
            <h3>Minecraft AI Suite</h3>
          </div>
          <div className="suite-intro-grid">
            <article>
              <span className="section-label">Target</span>
              <strong>Minecraft 1.7.10</strong>
              <p>Textures, models, worlds, structures, and texture-pack specs are tracked as media jobs and artifacts.</p>
            </article>
            <article>
              <span className="section-label">Tool Handoff</span>
              <strong>Blockbench + resource packs</strong>
              <p>Detected workstation Blockbench folders can become model/export targets once Edison has an MCP bridge.</p>
            </article>
          </div>
          <div className="minecraft-workflow-grid">
            {minecraftModes.map((mode) => (
              <article className="workflow-card" key={mode.id}>
                <div>
                  <strong>{mode.label}</strong>
                  <span>{mode.output_hint}</span>
                </div>
                <p>{mode.description}</p>
                <button className="secondary-button" onClick={() => useMode(mode.id)} type="button">
                  Use Mode
                </button>
              </article>
            ))}
          </div>
        </section>
      )}
      {activePanel === 'toybox' && (
        <section className="toybox-manager-panel" aria-label="ToyBox3D Store and Print Farm Manager">
          <div className="section-heading">
            <Server size={18} />
            <h3>ToyBox3D Store & Print Farm</h3>
          </div>
          {toyBoxStatus && <p className="panel-copy">{toyBoxStatus.detail}</p>}
          <div className="toybox-flow-grid">
            {toyboxLaneCards.map((page) => {
              const Icon = page.icon;
              return (
                <article className="toybox-page-card" key={page.id ?? page.title}>
                  <Icon size={20} />
                  <div>
                    <strong>{page.title}</strong>
                    <p>{page.description}</p>
                  </div>
                  <div className="chip-list">
                    {page.status && <span>{page.status}</span>}
                    {page.lanes.map((lane) => <span key={lane}>{lane}</span>)}
                  </div>
                </article>
              );
            })}
          </div>
          <div className="toybox-ops-grid">
            <article className="toybox-architecture-panel">
              <div>
                <span className="section-label">Desktop tool control</span>
                <strong>Fusion, slicers, labels, files</strong>
              </div>
              <ol>
                <li>Edison asks a PC-side MCP bridge to run an allowlisted task.</li>
                <li>The bridge can launch Fusion scripts, Blockbench exports, slicers, or label printing.</li>
                <li>Generated STL/STEP/G-code/label artifacts are returned to Edison for chat and ToyBox tracking.</li>
              </ol>
            </article>
            <article className="toybox-architecture-panel">
              <div>
                <span className="section-label">Order automation</span>
                <strong>Shopify to printer queue</strong>
              </div>
              <ol>
                <li>Shopify webhook or poller creates a production job from an unfulfilled order.</li>
                <li>SKU mapping chooses model, color, material, slicer profile, printer, and camera monitor.</li>
                <li>Label printing and customer tracking are handled after QA and packing.</li>
              </ol>
            </article>
          </div>
          {toyBoxStatus && (
            <div className="toybox-live-grid">
              <section className="job-list-panel">
                <div className="section-heading">
                  <Box size={18} />
                  <h3>CAD, Printers & Labels</h3>
                </div>
                <div className="toybox-device-list">
                  {toyBoxStatus.printers.map((printer) => (
                    <article className="toybox-device-row" key={printer.id}>
                      <div>
                        <strong>{printer.name}</strong>
                        <span>{printer.detail}</span>
                      </div>
                      <span className={`backend-status ${statusClassName(printer.status)}`}>{printer.status}</span>
                    </article>
                  ))}
                </div>
              </section>
              <section className="job-list-panel">
                <div className="section-heading">
                  <Zap size={18} />
                  <h3>Notifications</h3>
                </div>
                <div className="toybox-device-list">
                  {toyBoxStatus.notification_channels.map((channel) => (
                    <article className="toybox-device-row" key={channel.id}>
                      <div>
                        <strong>{channel.name}</strong>
                        <span>{channel.detail}</span>
                        <small>{channel.setup_hint}</small>
                      </div>
                      <span className={`backend-status ${statusClassName(channel.status)}`}>{channel.status}</span>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          )}
          <div className="toybox-architecture-panel">
            <div>
              <span className="section-label">Production path</span>
              <strong>Shopify order to printed shipment</strong>
            </div>
            <ol>
              <li>Poll scoped Shopify orders and match SKUs to printable products.</li>
              <li>Select model, filament/color, slicer profile, printer, and camera monitor.</li>
              <li>Queue print jobs, track production state, then create a Dymo shipping-label task.</li>
              <li>Attach proof photos and final artifact records back to the order.</li>
            </ol>
          </div>
        </section>
      )}
      {activePanel === 'outputs' && (
        <MediaOutputsPanel
          artifacts={artifacts}
          jobs={jobs}
          onUseArtifactInChat={onUseArtifactInChat}
        />
      )}
    </section>
  );
}

function MediaOutputsPanel({
  artifacts,
  jobs,
  onUseArtifactInChat,
}: {
  artifacts: ArtifactRecord[];
  jobs: JobRecord[];
  onUseArtifactInChat: (artifact: ArtifactRecord) => void;
}) {
  return (
    <div className="media-output-grid">
      <div className="job-list-panel">
        <div className="section-heading">
          <Activity size={18} />
          <h3>Generation Jobs</h3>
        </div>
        <div className="job-list">
          {jobs.slice(0, 12).map((job) => (
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
          {artifacts.slice(0, 12).map((artifact) => {
            const downloadUrl = edisonApi.artifactDownloadUrl(artifact.id);
            return (
              <article className="artifact-card" key={artifact.id}>
                <ArtifactPreview artifact={artifact} url={downloadUrl} />
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
    </div>
  );
}

function GalleryView({
  artifacts,
  jobs,
  onRefresh,
  onUseArtifactInChat,
  runtimeSettings,
}: {
  artifacts: ArtifactRecord[];
  jobs: JobRecord[];
  onRefresh: () => Promise<void>;
  onUseArtifactInChat: (artifact: ArtifactRecord) => void;
  runtimeSettings: RuntimeSettingsRecord | null;
}) {
  const defaultFilter = typeof runtimeSettings?.gallery.default_filter === 'string'
    ? runtimeSettings.gallery.default_filter
    : 'all';
  const [filter, setFilter] = useState(defaultFilter);
  const [query, setQuery] = useState('');
  useEffect(() => {
    setFilter(defaultFilter);
  }, [defaultFilter]);

  const visibleArtifacts = artifacts.filter((artifact) => {
    const haystack = `${artifact.title} ${artifact.kind} ${artifact.mime_type ?? ''} ${artifact.path}`.toLowerCase();
    const matchesQuery = !query.trim() || haystack.includes(query.trim().toLowerCase());
    if (!matchesQuery) {
      return false;
    }
    if (filter === 'all') {
      return true;
    }
    if (filter === 'docs') {
      return ['document', 'code', 'data'].includes(artifact.kind);
    }
    return artifact.kind === filter;
  });
  const filters = [
    ['all', 'All'],
    ['image', 'Images'],
    ['video', 'Video'],
    ['mesh', '3D'],
    ['audio', 'Audio'],
    ['docs', 'Specs'],
  ];

  return (
    <section className="workbench-view gallery-view" aria-label="Gallery">
      <div className="view-heading">
        <Image size={26} />
        <h3>Gallery</h3>
        <button className="secondary-button" onClick={() => void onRefresh()} type="button">Refresh</button>
      </div>
      <div className="gallery-toolbar">
        <div className="media-panel-tabs" role="tablist" aria-label="Gallery filters">
          {filters.map(([id, label]) => (
            <button
              className={filter === id ? 'mode-button active' : 'mode-button'}
              key={id}
              onClick={() => setFilter(id)}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
        <label>
          <span className="section-label">Search</span>
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find generated images, models, videos, specs..."
            type="search"
            value={query}
          />
        </label>
      </div>
      <div className="wide-metric-grid gallery-metrics">
        <div><dt>Artifacts</dt><dd>{artifacts.length}</dd></div>
        <div><dt>Images</dt><dd>{artifacts.filter((artifact) => artifact.kind === 'image').length}</dd></div>
        <div><dt>3D / Video</dt><dd>{artifacts.filter((artifact) => ['mesh', 'video'].includes(artifact.kind)).length}</dd></div>
        <div><dt>Jobs</dt><dd>{jobs.length}</dd></div>
      </div>
      <div className="gallery-shell">
        <div className="gallery-card-grid">
          {visibleArtifacts.map((artifact) => {
            const downloadUrl = edisonApi.artifactDownloadUrl(artifact.id);
            return (
              <article className={`artifact-card gallery-artifact-card ${artifact.kind}`} key={artifact.id}>
                <ArtifactPreview artifact={artifact} url={downloadUrl} />
                <div className="artifact-card-meta">
                  <strong>{artifact.title}</strong>
                  <span>{artifact.kind} / {artifact.mime_type ?? 'file'}</span>
                  <small>{new Date(artifact.created_at).toLocaleString()}</small>
                </div>
                <div className="artifact-card-actions">
                  <button className="secondary-button" onClick={() => onUseArtifactInChat(artifact)} type="button">Use in chat</button>
                  <a className="secondary-button" href={downloadUrl} rel="noreferrer" target="_blank">Open</a>
                </div>
              </article>
            );
          })}
          {visibleArtifacts.length === 0 && <div className="empty-line">No generated media matches this view yet.</div>}
        </div>
        <aside className="gallery-job-rail">
          <div className="section-heading">
            <Activity size={18} />
            <h3>Recent Generation Jobs</h3>
          </div>
          <div className="job-list">
            {jobs.slice(0, 10).map((job) => (
              <article className="job-row" key={job.id}>
                <div>
                  <strong>{job.title}</strong>
                  <span>{job.job_type} / {job.backend}</span>
                </div>
                <span className={`job-status ${job.status}`}>{job.status}</span>
              </article>
            ))}
            {jobs.length === 0 && <div className="empty-line">No generation jobs yet.</div>}
          </div>
        </aside>
      </div>
    </section>
  );
}

function fallbackMediaModes(): MediaGenerationModeRecord[] {
  return [
    ['image', 'Image', 'core', 'image', 'comfyui', 'General Edison image generation.', true, 'Image artifact', 'Describe the image.'],
    ['minecraft_texture', 'Minecraft Texture', 'minecraft', 'image', 'comfyui', 'Pixel-art texture concepts for Minecraft 1.7.10.', true, 'Texture image', 'Describe the block/item texture.'],
    ['minecraft_model', 'Minecraft Model', 'minecraft', 'code', 'minecraft-suite', 'Blockbench-ready model specifications.', true, 'Model specification', 'Describe the model.'],
    ['minecraft_world', 'Minecraft World', 'minecraft', 'code', 'minecraft-suite', 'World-generation design specs.', false, 'World spec', 'Describe the world.'],
    ['minecraft_structure', 'Minecraft Structure', 'minecraft', 'code', 'minecraft-suite', 'Structure build specs.', true, 'Structure spec', 'Describe the structure.'],
    ['minecraft_texture_pack', 'Minecraft Texture Pack', 'minecraft', 'code', 'minecraft-suite', 'Texture-pack production plan.', true, 'Texture pack spec', 'Describe the texture pack.'],
    ['product_render', 'Product Render', 'commerce', 'image', 'comfyui', 'Clean product shots for ToyBox3D listings.', true, 'Product image', 'Describe the product render.'],
    ['social_media_content', 'Social Media Content', 'social', 'document', 'media-planner', 'Social post copy and creative direction.', true, 'Campaign spec', 'Describe the post or campaign.'],
  ].map(([id, label, group, jobType, backend, description, referenceSupported, outputHint, promptHint]) => ({
    id: id as MediaGenerationMode,
    label: String(label),
    group: group as MediaGenerationModeRecord['group'],
    job_type: jobType as JobType,
    backend: String(backend),
    description: String(description),
    reference_supported: Boolean(referenceSupported),
    output_hint: String(outputHint),
    prompt_hint: String(promptHint),
    metadata: {},
  }));
}

function toyboxManagerPages(): Array<{ title: string; description: string; lanes: string[]; icon: IconType }> {
  return [
    {
      title: 'Shopify Orders',
      description: 'Order intake, fulfillment status, item colors, shipping state, and proof-photo attachments.',
      lanes: ['orders', 'fulfillment', 'webhooks'],
      icon: Database,
    },
    {
      title: 'Product-to-Print Mappings',
      description: 'SKU to model file, slicer profile, filament/color, printer family, and packaging rules.',
      lanes: ['sku', 'model', 'color'],
      icon: Box,
    },
    {
      title: 'Print Queue',
      description: 'Prioritized production queue with printer assignment, retry state, ETA, and order linkage.',
      lanes: ['queue', 'eta', 'assignment'],
      icon: Activity,
    },
    {
      title: 'Printer Management',
      description: 'Printer profiles, camera feeds, bed state, material slots, maintenance, and availability.',
      lanes: ['printers', 'camera', 'filament'],
      icon: Server,
    },
    {
      title: 'Production Tracking',
      description: 'Started, printing, cooling, QA, packed, label printed, shipped, and exception states.',
      lanes: ['qa', 'packing', 'shipping'],
      icon: CheckSquare2,
    },
    {
      title: 'Dymo Label Station',
      description: 'Shipping-label print handoff and label queue once Shopify shipping scopes are connected.',
      lanes: ['labels', 'tracking', 'handoff'],
      icon: FileText,
    },
  ];
}

function toyboxIconForLane(laneId: string): IconType {
  if (laneId.includes('shopify')) {
    return Database;
  }
  if (laneId.includes('mapping')) {
    return Box;
  }
  if (laneId.includes('queue') || laneId.includes('tracking')) {
    return Activity;
  }
  if (laneId.includes('label')) {
    return FileText;
  }
  if (laneId.includes('notification')) {
    return Zap;
  }
  return Server;
}

function SystemView({
  cameraAnalysis,
  cameraVisionStatus,
  capabilityStatus,
  fanControls,
  groupedModels,
  hardwareControlCenter,
  hardwareStatus,
  isCameraBusy,
  isCameraFeedPaused,
  models,
  onCaptureCameraSnapshot,
  onAnalyzeCameraFrame,
  onRefresh,
  onUpdateFanControl,
  status,
}: {
  cameraAnalysis: CameraFrameAnalysisResponse | null;
  cameraVisionStatus: CameraVisionStatus | null;
  capabilityStatus: CapabilityStatus | null;
  fanControls: GPUFanControlSnapshot | null;
  groupedModels: { ready: ModelProfile[]; pending: ModelProfile[] };
  hardwareControlCenter: HardwareControlCenter | null;
  hardwareStatus: HardwareStatus | null;
  isCameraBusy: boolean;
  isCameraFeedPaused: boolean;
  models: ModelProfile[];
  onCaptureCameraSnapshot: (devicePath?: string | null) => Promise<void>;
  onAnalyzeCameraFrame: (devicePath?: string | null) => Promise<void>;
  onRefresh: () => Promise<void>;
  onUpdateFanControl: (gpuIndex: number, mode: GPUFanMode, manualSpeed: number) => Promise<void>;
  status: SystemStatus | null;
}) {
  const hailo = hardwareStatus?.accelerators.find((accelerator) => accelerator.kind === 'hailo8');
  const cameras = hardwareStatus?.cameras ?? [];
  const liveCamera = cameraVisionStatus?.camera ?? cameras.find((cameraDevice) => cameraDevice.capture_path);
  const liveFeedUrl = liveCamera?.capture_path && !isCameraFeedPaused
    ? edisonApi.cameraFeedUrl({ device_path: liveCamera.capture_path, width: 960, height: 540, input_format: 'mjpeg' })
    : null;

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
      <HardwareControlCenterPanel controlCenter={hardwareControlCenter} />
      <section className="capability-panel" aria-label="MCP servers and plugins">
        <div className="section-heading">
          <Waypoints size={18} />
          <h3>MCP, Plugins & Integrations</h3>
        </div>
        <div className="capability-grid">
          {(capabilityStatus?.mcp_servers ?? []).map((server) => (
            <article className="capability-card" key={server.id}>
              <div className="device-card-header">
                <div>
                  <span className="section-label">{server.transport} MCP</span>
                  <strong>{server.name}</strong>
                </div>
                <span className={`backend-status ${statusClassName(server.status)}`}>
                  {server.status}
                </span>
              </div>
              <p>{server.description}</p>
              <small>{server.detail}</small>
              <div className="chip-list">
                {server.tools.slice(0, 4).map((tool) => <span key={tool}>{tool}</span>)}
              </div>
            </article>
          ))}
          {(capabilityStatus?.plugins ?? []).map((plugin) => (
            <article className="capability-card" key={plugin.id}>
              <div className="device-card-header">
                <div>
                  <span className="section-label">{plugin.target}</span>
                  <strong>{plugin.name}</strong>
                </div>
                <span className={`backend-status ${statusClassName(plugin.status)}`}>
                  {plugin.status}
                </span>
              </div>
              <p>{plugin.description}</p>
              <small>{plugin.detail}</small>
              <div className="chip-list">
                {plugin.scopes.slice(0, 5).map((scope) => <span key={scope}>{scope}</span>)}
              </div>
            </article>
          ))}
          {(capabilityStatus?.integrations ?? []).map((integration) => (
            <IntegrationCard integration={integration} key={integration.id} />
          ))}
          {(capabilityStatus?.recommendations ?? []).slice(0, 4).map((recommendation) => (
            <article className="capability-card recommendation-card" key={recommendation.id}>
              <div className="device-card-header">
                <div>
                  <span className="section-label">{recommendation.priority} priority</span>
                  <strong>{recommendation.title}</strong>
                </div>
                <span className="backend-status setup_required">Recommended</span>
              </div>
              <p>{recommendation.detail}</p>
              <small>{recommendation.action}</small>
            </article>
          ))}
          {!capabilityStatus && <div className="empty-line">Capability registry has not loaded yet.</div>}
        </div>
      </section>
      <section className="hardware-panel" aria-label="AI accelerator and camera">
        <div className="section-heading">
          <Zap size={18} />
          <h3>AI Accelerator & Camera</h3>
        </div>
        <div className="hardware-device-grid">
          {hailo ? (
            <article className="hardware-device-card">
              <div className="device-card-header">
                <div>
                  <span className="section-label">PCIe accelerator</span>
                  <strong>{hailo.name}</strong>
                </div>
                <span className={`backend-status ${statusClassName(hailo.status)}`}>
                  {hailo.status.replace('_', ' ')}
                </span>
              </div>
              <p>{hailo.detail}</p>
              <dl className="device-meta-list">
                <div>
                  <dt>PCIe</dt>
                  <dd>{hailo.pci_address ?? 'Not detected'}</dd>
                </div>
                <div>
                  <dt>Driver</dt>
                  <dd>{hailo.driver_loaded ? 'Loaded' : 'Missing'}</dd>
                </div>
                <div>
                  <dt>Runtime</dt>
                  <dd>{hailo.runtime_available ? hailo.runtime_version ?? 'Installed' : 'Missing'}</dd>
                </div>
                <div>
                  <dt>Nodes</dt>
                  <dd>{hailo.device_nodes.length ? hailo.device_nodes.join(', ') : 'None'}</dd>
                </div>
              </dl>
            </article>
          ) : (
            <article className="hardware-device-card">
              <div className="device-card-header">
                <div>
                  <span className="section-label">PCIe accelerator</span>
                  <strong>Hailo-8 AI Accelerator</strong>
                </div>
                <span className="backend-status offline">Not checked</span>
              </div>
              <p>Hardware status has not loaded yet.</p>
            </article>
          )}

          {cameras.map((cameraDevice) => (
            <article className="hardware-device-card" key={cameraDevice.id}>
              <div className="device-card-header">
                <div>
                  <span className="section-label">USB camera</span>
                  <strong>{cameraDevice.name}</strong>
                </div>
                <span className={`backend-status ${statusClassName(cameraDevice.status)}`}>
                  {cameraDevice.status.replace('_', ' ')}
                </span>
              </div>
              <p>{cameraDevice.detail}</p>
              <dl className="device-meta-list">
                <div>
                  <dt>Capture</dt>
                  <dd>{cameraDevice.capture_path ?? 'Unavailable'}</dd>
                </div>
                <div>
                  <dt>USB ID</dt>
                  <dd>{cameraDevice.vendor_id && cameraDevice.product_id ? `${cameraDevice.vendor_id}:${cameraDevice.product_id}` : 'Unknown'}</dd>
                </div>
                <div>
                  <dt>Video Nodes</dt>
                  <dd>{cameraDevice.device_paths.join(', ') || 'None'}</dd>
                </div>
                <div>
                  <dt>Formats</dt>
                  <dd>{cameraDevice.formats.slice(0, 3).join(' / ') || 'Not listed'}</dd>
                </div>
              </dl>
              <div className="device-card-actions">
                <button
                  className="apply-button icon-text-button"
                  disabled={isCameraBusy || !cameraDevice.capture_path || cameraDevice.status !== 'ready'}
                  onClick={() => void onCaptureCameraSnapshot(cameraDevice.capture_path)}
                  type="button"
                >
                  <Camera size={16} />
                  Snapshot
                </button>
              </div>
            </article>
          ))}
          {cameras.length === 0 && (
            <article className="hardware-device-card">
              <div className="device-card-header">
                <div>
                  <span className="section-label">USB camera</span>
                  <strong>Logitech Brio</strong>
                </div>
                <span className="backend-status offline">Offline</span>
              </div>
              <p>No camera was detected by Edison.</p>
            </article>
          )}
          <article className="hardware-device-card camera-feed-card">
            <div className="device-card-header">
              <div>
                <span className="section-label">Live vision</span>
                <strong>{liveCamera?.name ?? 'Camera feed'}</strong>
              </div>
              <span className={`backend-status ${statusClassName(cameraVisionStatus?.status ?? 'offline')}`}>
                {(cameraVisionStatus?.status ?? 'offline').replace('_', ' ')}
              </span>
            </div>
            <div className="camera-feed-frame">
              {liveFeedUrl ? (
                <img alt={`${liveCamera?.name ?? 'Camera'} live feed`} src={liveFeedUrl} />
              ) : (
                <div className={`empty-preview ${isCameraFeedPaused ? 'camera-feed-paused' : ''}`}>
                  <Camera size={30} />
                  <strong>{isCameraFeedPaused ? 'Releasing camera' : 'No live feed'}</strong>
                  {isCameraFeedPaused && <span>Snapshot and vision analysis need the camera for a moment.</span>}
                </div>
              )}
              <div className="camera-feed-overlay">
                <span>{isCameraFeedPaused ? 'Capturing' : 'Live'}</span>
                <span>{liveCamera?.capture_path ?? 'No device'}</span>
              </div>
            </div>
            <div className="camera-ai-console">
              <div>
                <strong>Camera AI</strong>
                <p>{cameraVisionStatus?.detail ?? 'Vision status has not loaded yet.'}</p>
              </div>
              <div className="camera-ai-actions">
                <button
                  className="secondary-button icon-text-button"
                  disabled={isCameraBusy || !liveCamera?.capture_path}
                  onClick={() => void onCaptureCameraSnapshot(liveCamera?.capture_path)}
                  type="button"
                >
                  <Camera size={16} />
                  Snapshot
                </button>
                <button
                  className="apply-button icon-text-button"
                  disabled={isCameraBusy || !liveCamera?.capture_path}
                  onClick={() => void onAnalyzeCameraFrame(liveCamera?.capture_path)}
                  type="button"
                >
                  <Sparkles size={16} />
                  Analyze Frame
                </button>
              </div>
            </div>
            <div className="camera-ai-feature-grid">
              <div>
                <span>Scene VLM</span>
                <strong>{cameraAnalysis?.status === 'complete' ? 'Ready' : 'On demand'}</strong>
              </div>
              <div>
                <span>Object Detection</span>
                <strong>{cameraVisionStatus?.status === 'ready' ? 'Hailo ready' : 'Hailo setup'}</strong>
              </div>
              <div>
                <span>Frames</span>
                <strong>{cameraAnalysis ? 'Saved' : 'Waiting'}</strong>
              </div>
            </div>
            {cameraAnalysis && (
              <div className={`camera-analysis-card ${cameraAnalysis.status}`}>
                <div>
                  <span className="section-label">Last Analysis</span>
                  <strong>{cameraAnalysis.model_id ?? cameraAnalysis.backend ?? 'camera-ai'}</strong>
                </div>
                <p>{cameraAnalysis.summary}</p>
                <div className="chip-list">
                  {cameraAnalysis.detections.map((detection) => <span key={detection}>{detection}</span>)}
                  {cameraAnalysis.detections.length === 0 && <span>{cameraAnalysis.status.replace('_', ' ')}</span>}
                </div>
                <a className="secondary-button" href={edisonApi.artifactDownloadUrl(cameraAnalysis.artifact.id)} target="_blank" rel="noreferrer">
                  Open Frame
                </a>
              </div>
            )}
            <div className="chip-list">
              {(cameraVisionStatus?.labels ?? []).map((label) => <span key={label}>{label}</span>)}
              {!cameraVisionStatus?.labels.length && <span>{cameraVisionStatus?.backend ?? 'vision backend'}</span>}
            </div>
          </article>
        </div>
      </section>
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

function HardwareControlCenterPanel({ controlCenter }: { controlCenter: HardwareControlCenter | null }) {
  const actions = controlCenter?.actions ?? [];
  return (
    <section className="hardware-command-center" aria-label="Hardware command center">
      <div className="section-heading">
        <Cpu size={18} />
        <h3>Hardware Command Center</h3>
      </div>
      <div className="command-center-grid">
        <article className="command-center-status">
          <div>
            <span className="section-label">Machine state</span>
            <strong>{controlCenter?.overall_status.replace('_', ' ') ?? 'checking'}</strong>
          </div>
          <span className={`backend-status ${statusClassName(controlCenter?.overall_status ?? 'offline')}`}>
            {controlCenter?.overall_status ?? 'offline'}
          </span>
        </article>
        <dl className="command-center-metrics">
          <div>
            <dt>GPUs</dt>
            <dd>{controlCenter?.gpu_count ?? 0}</dd>
          </div>
          <div>
            <dt>Fan cards</dt>
            <dd>{controlCenter?.fan_controller_count ?? 0}</dd>
          </div>
          <div>
            <dt>Fan targets</dt>
            <dd>{controlCenter?.writable_fan_target_count ?? 0}</dd>
          </div>
          <div>
            <dt>Fan backend</dt>
            <dd>{controlCenter?.fan_backend ?? 'monitor'}</dd>
          </div>
          <div>
            <dt>Hailo</dt>
            <dd>{controlCenter?.hailo_status.replace('_', ' ') ?? 'not checked'}</dd>
          </div>
          <div>
            <dt>Camera</dt>
            <dd>{controlCenter?.camera_status.replace('_', ' ') ?? 'not checked'}</dd>
          </div>
        </dl>
        <div className="command-center-actions">
          {(actions.length ? actions : [{
            id: 'loading',
            title: 'Loading hardware checks',
            detail: 'Edison is waiting for the next hardware snapshot.',
            severity: 'info' as const,
            action_label: null,
            metadata: {},
          }]).map((action) => (
            <article className={`command-center-action ${action.severity}`} key={action.id}>
              <div>
                <strong>{action.title}</strong>
                <p>{action.detail}</p>
              </div>
              {action.action_label && <span>{action.action_label}</span>}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function IntegrationCard({ integration }: { integration: LocalIntegrationRecord }) {
  return (
    <article className="capability-card integration-card">
      <div className="device-card-header">
        <div>
          <span className="section-label">{integration.host} / {integration.category}</span>
          <strong>{integration.name}</strong>
        </div>
        <span className={`backend-status ${statusClassName(integration.status)}`}>
          {integration.status}
        </span>
      </div>
      <p>{integration.description}</p>
      <small>{integration.detail}</small>
      <div className="chip-list">
        {integration.detected_tools.slice(0, 5).map((tool) => <span key={tool}>{tool}</span>)}
        {integration.detected_tools.length === 0 && <span>No tools detected</span>}
      </div>
      {integration.next_steps.length > 0 && (
        <div className="integration-next-steps">
          {integration.next_steps.slice(0, 2).map((step) => <span key={step}>{step}</span>)}
        </div>
      )}
    </article>
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
          {controller.applied ? 'Applied' : 'Ready'}
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
          <div>
            <dt>Targets</dt>
            <dd>{controller.target_fan_ids.length ? controller.target_fan_ids.map((fanId) => `fan:${fanId}`).join(' ') : 'Auto'}</dd>
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

function SettingsView({
  fanControls,
  hardwareStatus,
  mediaStatus,
  runtimeSettings,
  sessionState,
  status,
  toyBoxStatus,
  onSave,
  workspaceRoots,
}: {
  fanControls: GPUFanControlSnapshot | null;
  hardwareStatus: HardwareStatus | null;
  mediaStatus: MediaSystemStatus | null;
  runtimeSettings: RuntimeSettingsRecord | null;
  sessionState: SessionStateRecord | null;
  status: SystemStatus | null;
  toyBoxStatus: ToyBoxManagerStatus | null;
  onSave: (payload: Parameters<typeof edisonApi.updateRuntimeSettings>[0]) => Promise<void>;
  workspaceRoots: WorkspaceRootRecord[];
}) {
  const [draft, setDraft] = useState<RuntimeSettingsRecord>(() => defaultRuntimeSettings());
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const hailo = hardwareStatus?.accelerators.find((accelerator) => accelerator.kind === 'hailo8');
  const cameras = hardwareStatus?.cameras ?? [];
  const mediaBackends = [
    ['ComfyUI', mediaStatus?.comfyui.status, mediaStatus?.comfyui.base_url],
    ['InvokeAI', mediaStatus?.invokeai.status, mediaStatus?.invokeai.base_url],
    ['WAN 2.2', mediaStatus?.wan22.status, mediaStatus?.wan22.base_url],
    ['Modly', mediaStatus?.modly.status, mediaStatus?.modly.base_url],
  ];
  const toyboxReady = toyBoxStatus?.lanes.filter((lane) => lane.status === 'ready').length ?? 0;
  const notificationChannels = toyBoxStatus?.notification_channels ?? [];

  useEffect(() => {
    setDraft(runtimeSettings ?? defaultRuntimeSettings());
  }, [runtimeSettings]);

  function updateSetting(section: keyof RuntimeSettingsEditableSections, key: string, value: unknown) {
    setDraft((current) => ({
      ...current,
      [section]: {
        ...current[section],
        [key]: value,
      },
    }));
    setSaveMessage(null);
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSave({
      media: draft.media,
      integrations: draft.integrations,
      toybox: draft.toybox,
      notifications: draft.notifications,
      gallery: draft.gallery,
      hardware: draft.hardware,
    });
    setSaveMessage('Saved locally. Some service-level changes may need a restart before backend workers use them.');
  }

  return (
    <section className="workbench-view" aria-label="Settings">
      <div className="view-heading">
        <Settings size={26} />
        <h3>Settings</h3>
        <button className="apply-button" form="runtime-settings-form" type="submit">Save Changes</button>
      </div>
      <form className="settings-stack settings-form" id="runtime-settings-form" onSubmit={(event) => void saveSettings(event)}>
        {saveMessage && <div className="settings-save-message">{saveMessage}</div>}
        <article className="settings-panel">
          <div className="section-heading">
            <Database size={18} />
            <h3>Storage</h3>
          </div>
          <dl className="settings-list">
            <div>
              <dt>Database</dt>
              <dd>{status?.database_path ?? 'Not loaded'}</dd>
            </div>
            {Object.entries(status?.storage_roots ?? {}).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{value}</dd>
              </div>
            ))}
            <div>
              <dt>Code Spaces</dt>
              <dd>{status?.storage_roots.projects ?? workspaceRoots.find((root) => root.kind === 'project')?.path ?? 'No project root loaded yet'}</dd>
            </div>
          </dl>
        </article>
        <article className="settings-panel settings-edit-panel">
          <div className="section-heading">
            <SlidersHorizontal size={18} />
            <h3>Media Defaults</h3>
          </div>
          <label>
            <span>Preferred mode</span>
            <select
              onChange={(event) => updateSetting('media', 'preferred_image_mode', event.target.value)}
              value={settingString(draft.media, 'preferred_image_mode', 'image')}
            >
              <option value="image">Image</option>
              <option value="minecraft_texture">Minecraft Texture</option>
              <option value="product_render">Product Render</option>
              <option value="social_media_content">Social Media Content</option>
            </select>
          </label>
          <label>
            <span>Default width</span>
            <input
              min={256}
              max={2048}
              onChange={(event) => updateSetting('media', 'default_width', Number(event.target.value))}
              type="number"
              value={settingNumber(draft.media, 'default_width', 1024)}
            />
          </label>
          <label>
            <span>Default height</span>
            <input
              min={256}
              max={2048}
              onChange={(event) => updateSetting('media', 'default_height', Number(event.target.value))}
              type="number"
              value={settingNumber(draft.media, 'default_height', 1024)}
            />
          </label>
          <label className="settings-toggle-row">
            <input
              checked={settingBoolean(draft.media, 'show_outputs_in_chat', true)}
              onChange={(event) => updateSetting('media', 'show_outputs_in_chat', event.target.checked)}
              type="checkbox"
            />
            <span>Show generated outputs directly in chat</span>
          </label>
        </article>
        <article className="settings-panel">
          <div className="section-heading">
            <GalleryHorizontalEnd size={18} />
            <h3>Media Backends</h3>
          </div>
          <dl className="settings-list">
            {mediaBackends.map(([name, backendStatus, url]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{backendStatus ?? 'not checked'} / {url ?? 'no URL'}</dd>
              </div>
            ))}
          </dl>
        </article>
        <article className="settings-panel settings-edit-panel">
          <div className="section-heading">
            <Network size={18} />
            <h3>Desktop Bridge</h3>
          </div>
          <label>
            <span>Bridge URL</span>
            <input
              onChange={(event) => updateSetting('integrations', 'desktop_bridge_url', event.target.value)}
              placeholder="http://main-pc.local:8765"
              value={settingString(draft.integrations, 'desktop_bridge_url', '')}
            />
          </label>
          {[
            ['fusion360_enabled', 'Fusion 360 CAD automation'],
            ['blockbench_enabled', 'Blockbench Minecraft assets'],
            ['slicer_bridge_enabled', 'Bambu / Orca / Cura slicer bridge'],
          ].map(([key, label]) => (
            <label className="settings-toggle-row" key={key}>
              <input
                checked={settingBoolean(draft.integrations, key, true)}
                onChange={(event) => updateSetting('integrations', key, event.target.checked)}
                type="checkbox"
              />
              <span>{label}</span>
            </label>
          ))}
          <p className="settings-hint">The bridge should run on your main PC and expose only allowlisted folders, commands, app launchers, and artifact return paths.</p>
        </article>
        <article className="settings-panel settings-edit-panel">
          <div className="section-heading">
            <Server size={18} />
            <h3>ToyBox3D / Shopify</h3>
          </div>
          <label>
            <span>Shopify store URL</span>
            <input
              onChange={(event) => updateSetting('toybox', 'shopify_store_url', event.target.value)}
              placeholder="https://your-store.myshopify.com"
              value={settingString(draft.toybox, 'shopify_store_url', '')}
            />
          </label>
          <label>
            <span>Default slicer</span>
            <select
              onChange={(event) => updateSetting('toybox', 'default_slicer', event.target.value)}
              value={settingString(draft.toybox, 'default_slicer', 'Bambu Studio')}
            >
              <option>Bambu Studio</option>
              <option>OrcaSlicer</option>
              <option>Cura</option>
            </select>
          </label>
          <label>
            <span>DYMO printer name</span>
            <input
              onChange={(event) => updateSetting('toybox', 'dymo_printer_name', event.target.value)}
              value={settingString(draft.toybox, 'dymo_printer_name', "Mike's shipping label printer")}
            />
          </label>
          <label className="settings-toggle-row">
            <input
              checked={settingBoolean(draft.toybox, 'order_polling_enabled', false)}
              onChange={(event) => updateSetting('toybox', 'order_polling_enabled', event.target.checked)}
              type="checkbox"
            />
            <span>Enable Shopify order polling when credentials are configured</span>
          </label>
          <label className="settings-toggle-row">
            <input
              checked={settingBoolean(draft.toybox, 'auto_print_labels', false)}
              onChange={(event) => updateSetting('toybox', 'auto_print_labels', event.target.checked)}
              type="checkbox"
            />
            <span>Auto-print shipping labels after QA approval</span>
          </label>
          <p className="settings-hint">{toyboxReady} ToyBox lanes are ready. Secret tokens still belong in local env/settings, not source control.</p>
        </article>
        <article className="settings-panel settings-edit-panel">
          <div className="section-heading">
            <Zap size={18} />
            <h3>Notifications</h3>
          </div>
          <label className="settings-toggle-row">
            <input
              checked={settingBoolean(draft.notifications, 'enabled', false)}
              onChange={(event) => updateSetting('notifications', 'enabled', event.target.checked)}
              type="checkbox"
            />
            <span>Enable production alerts</span>
          </label>
          <label>
            <span>Provider</span>
            <select
              onChange={(event) => updateSetting('notifications', 'provider', event.target.value)}
              value={settingString(draft.notifications, 'provider', 'ntfy')}
            >
              <option value="ntfy">ntfy</option>
              <option value="pushover">Pushover</option>
              <option value="twilio">Twilio SMS</option>
              <option value="email">Email SMTP</option>
              <option value="desktop">Desktop bridge</option>
            </select>
          </label>
          <label>
            <span>Target</span>
            <input
              onChange={(event) => updateSetting('notifications', 'target', event.target.value)}
              placeholder="topic, phone number, email, or desktop"
              value={settingString(draft.notifications, 'target', '')}
            />
          </label>
          {[
            ['notify_on_print_error', 'Print errors'],
            ['notify_on_label_error', 'Label errors'],
            ['notify_on_order_exception', 'Order exceptions'],
          ].map(([key, label]) => (
            <label className="settings-toggle-row" key={key}>
              <input
                checked={settingBoolean(draft.notifications, key, true)}
                onChange={(event) => updateSetting('notifications', key, event.target.checked)}
                type="checkbox"
              />
              <span>{label}</span>
            </label>
          ))}
          <div className="chip-list">
            {notificationChannels.map((channel) => <span key={channel.id}>{channel.name}: {channel.status}</span>)}
          </div>
        </article>
        <article className="settings-panel settings-edit-panel">
          <div className="section-heading">
            <Image size={18} />
            <h3>Gallery</h3>
          </div>
          <label>
            <span>Default filter</span>
            <select
              onChange={(event) => updateSetting('gallery', 'default_filter', event.target.value)}
              value={settingString(draft.gallery, 'default_filter', 'all')}
            >
              <option value="all">All</option>
              <option value="image">Images</option>
              <option value="video">Video</option>
              <option value="mesh">3D</option>
              <option value="docs">Specs</option>
            </select>
          </label>
          <label className="settings-toggle-row">
            <input
              checked={settingBoolean(draft.gallery, 'show_documents', true)}
              onChange={(event) => updateSetting('gallery', 'show_documents', event.target.checked)}
              type="checkbox"
            />
            <span>Show documents and specs in Gallery</span>
          </label>
          <label className="settings-toggle-row">
            <input
              checked={settingBoolean(draft.gallery, 'show_code_specs', true)}
              onChange={(event) => updateSetting('gallery', 'show_code_specs', event.target.checked)}
              type="checkbox"
            />
            <span>Show code/model specs in Gallery</span>
          </label>
        </article>
        <article className="settings-panel">
          <div className="section-heading">
            <Fan size={18} />
            <h3>Hardware Control</h3>
          </div>
          <dl className="settings-list">
            <div>
              <dt>Fan Backend</dt>
              <dd>{fanControls?.backend ?? 'monitor'} / {fanControls?.hardware_control_enabled ? 'writes enabled' : 'monitor mode'}</dd>
            </div>
            <div>
              <dt>Fan Controllers</dt>
              <dd>{fanControls?.controllers.length ?? 0}</dd>
            </div>
            <div>
              <dt>Hailo-8</dt>
              <dd>{hailo ? `${hailo.status.replace('_', ' ')} / ${hailo.pci_address ?? 'no PCIe address'}` : 'not checked'} / {settingString(draft.hardware, 'hailo_driver_action', 'mok_enrollment_required')}</dd>
            </div>
            <div>
              <dt>Cameras</dt>
              <dd>{cameras.map((cameraDevice) => `${cameraDevice.name} ${cameraDevice.capture_path ?? ''}`.trim()).join(' / ') || 'none'}</dd>
            </div>
          </dl>
          <label className="settings-toggle-row">
            <input
              checked={settingBoolean(draft.hardware, 'allow_reboot_when_confirmed', false)}
              onChange={(event) => updateSetting('hardware', 'allow_reboot_when_confirmed', event.target.checked)}
              type="checkbox"
            />
            <span>Allow Edison to reboot after explicit confirmation</span>
          </label>
        </article>
        <article className="settings-panel">
          <div className="section-heading">
            <Globe2 size={18} />
            <h3>Session</h3>
          </div>
          <dl className="settings-list">
            <div>
              <dt>Current Session</dt>
              <dd>{sessionState?.session_id ?? 'local-workbench'} on {status?.environment ?? 'local'}.</dd>
            </div>
            <div>
              <dt>Selected Mode</dt>
              <dd>{sessionState?.selected_mode ?? 'chat'}</dd>
            </div>
            <div>
              <dt>Selected Model</dt>
              <dd>{sessionState?.selected_model ?? 'auto'}</dd>
            </div>
          </dl>
        </article>
      </form>
    </section>
  );
}

type RuntimeSettingsEditableSections = Pick<
  RuntimeSettingsRecord,
  'media' | 'integrations' | 'toybox' | 'notifications' | 'gallery' | 'hardware'
>;

function defaultRuntimeSettings(): RuntimeSettingsRecord {
  return {
    service: 'runtime-settings',
    updated_at: new Date().toISOString(),
    media: {
      preferred_image_mode: 'image',
      default_width: 1024,
      default_height: 1024,
      show_outputs_in_chat: true,
    },
    integrations: {
      desktop_bridge_url: '',
      fusion360_enabled: true,
      blockbench_enabled: true,
      slicer_bridge_enabled: true,
    },
    toybox: {
      shopify_store_url: '',
      order_polling_enabled: false,
      default_slicer: 'Bambu Studio',
      dymo_printer_name: "Mike's shipping label printer",
      auto_print_labels: false,
    },
    notifications: {
      enabled: false,
      provider: 'ntfy',
      target: '',
      notify_on_print_error: true,
      notify_on_label_error: true,
      notify_on_order_exception: true,
    },
    gallery: {
      default_filter: 'all',
      show_documents: true,
      show_code_specs: true,
    },
    hardware: {
      hailo_driver_action: 'mok_enrollment_required',
      allow_reboot_when_confirmed: false,
    },
    detail: 'Runtime settings are stored locally and are not committed to the repository.',
  };
}

function settingString(section: Record<string, unknown>, key: string, fallback: string) {
  const value = section[key];
  return typeof value === 'string' ? value : fallback;
}

function settingNumber(section: Record<string, unknown>, key: string, fallback: number) {
  const value = section[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function settingBoolean(section: Record<string, unknown>, key: string, fallback: boolean) {
  const value = section[key];
  return typeof value === 'boolean' ? value : fallback;
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
  if (/\b(3d|3-d|three-dimensional|mesh|glb|obj|stl|sculpt)\b/.test(lowered)) {
    return 'mesh';
  }
  if (/\b(audio|music|song|voice|sound)\b/.test(lowered)) {
    return 'audio';
  }
  return 'image';
}

function inferMediaGenerationMode(content: string): MediaGenerationMode | null {
  const lowered = content.toLowerCase();
  const mentionsMinecraft = /\b(minecraft|mc\s*1\.7\.10|1\.7\.10|blockbench|resource\s*pack|texture\s*pack|schematic|structure|biome|worldgen)\b/.test(lowered);
  if (mentionsMinecraft) {
    if (/\b(texture\s*pack|resource\s*pack|pack)\b/.test(lowered)) {
      return 'minecraft_texture_pack';
    }
    if (/\b(world|worldgen|biome|dimension|terrain|seed)\b/.test(lowered)) {
      return 'minecraft_world';
    }
    if (/\b(structure|schematic|dungeon|village|tower|castle|building|base)\b/.test(lowered)) {
      return 'minecraft_structure';
    }
    if (/\b(model|entity|mob|blockbench|json\s*model|java\s*model)\b/.test(lowered)) {
      return 'minecraft_model';
    }
    if (/\b(texture|block|item|sprite|tileable|pixel\s*art)\b/.test(lowered)) {
      return 'minecraft_texture';
    }
    return 'minecraft_structure';
  }
  if (/\b(product\s*render|shopify\s*(image|photo|listing|thumbnail)|listing\s*(image|render)|toybox3d\s*(render|listing))\b/.test(lowered)) {
    return 'product_render';
  }
  if (/\b(social\s*media|instagram|tiktok|facebook|x post|tweet|caption|reel|shorts|campaign|ad copy)\b/.test(lowered)) {
    return 'social_media_content';
  }
  return null;
}

function isMediaGenerationPrompt(content: string): boolean {
  const lowered = content.toLowerCase();
  return /\b(generate|make|create|render|draw|design|turn|convert|animate|produce)\b/.test(lowered)
    && /\b(image|picture|photo|art|poster|video|animation|movie|clip|3d|3-d|three-dimensional|mesh|glb|obj|stl|sculpt|modly|comfy|wan|minecraft|texture|texture\s*pack|resource\s*pack|blockbench|world|structure|schematic|product\s*render|shopify\s*listing|social\s*media|caption|campaign)\b/.test(lowered);
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

function statusClassName(status: string) {
  if (['ready', 'completed', 'ok'].includes(status)) {
    return 'ready';
  }
  if ([
    'attention',
    'detected',
    'driver_missing',
    'runtime_missing',
    'permission_required',
    'planning',
    'queued',
    'running',
    'setup_required',
    'staged',
    'waiting_for_approval',
    'warning',
  ].includes(status)) {
    return 'setup_required';
  }
  return 'offline';
}

function formatRunStatus(status: AgentRunRecord['status']) {
  return status.replace(/_/g, ' ');
}

function agentRunIdFromConversation(conversation: ConversationWithMessages | null): string | null {
  const messages = conversation?.messages ?? [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const value = messages[index].metadata.agent_run_id;
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }
  return null;
}

function formatCompareDuration(run: CompareRun) {
  if (!run.finishedAt) {
    return run.status === 'streaming' ? 'Streaming' : 'Not started';
  }
  return `${((run.finishedAt - run.startedAt) / 1000).toFixed(1)}s`;
}

function buildResearchPrompt(topic: string, depth: ResearchDepth, includeKnowledge: boolean, sourceLimit: number) {
  const depthOption = researchDepthOptions.find((option) => option.value === depth) ?? researchDepthOptions[2];
  return [
    'You are Edison running a research task for the local AI workstation.',
    depthOption.instruction,
    'Use clear section headings, separate confirmed facts from assumptions, call out weak evidence, and end with concrete next actions.',
    includeKnowledge
      ? `Use the retrieved Edison knowledge context as the primary source set. Cite source titles or URLs when they are available. Use up to ${sourceLimit} retrieved matches.`
      : 'Do not rely on retrieved local knowledge. State when external verification would be needed.',
    `Research topic:\n${topic}`,
  ].join('\n\n');
}

function parseTagInput(value: string) {
  return value
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
    .slice(0, 16);
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
