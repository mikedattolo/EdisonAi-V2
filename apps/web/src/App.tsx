import {
  Activity,
  Bot,
  Box,
  Brain,
  BookOpen,
  CalendarDays,
  Download,
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
  Home,
  Image,
  Lightbulb,
  Link2,
  MessageSquare,
  Mic,
  Move,
  Network,
  Pause,
  Play,
  Printer,
  RefreshCw,
  Search,
  Send,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
  Trash2,
  Upload,
  Video,
  Waypoints,
  X,
  Zap,
} from 'lucide-react';
import { CSSProperties, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { ThreeMFLoader } from 'three/examples/jsm/loaders/3MFLoader.js';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import Editor from '@monaco-editor/react';
import './creator-lab.css';
import './code-space.css';
import './voice.css';
import './scheduled.css';
import './toybox.css';
import { edisonApi } from './api';
import type {
  AgentChangedFile,
  AgentRunRecord,
  AgentRunWithEvents,
  ArtifactRecord,
  CapabilityStatus,
  ChatImportSource,
  ChatMode,
  ConversationRecord,
  CreatorStudioAssistAction,
  CreatorLabOverview,
  CreatorLabDataset,
  CreatorWorkflowGraph,
  CreatorVlmCritique,
  CreatorTrainingJob,
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
  RealtimeContext,
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
  WorkspaceInstallResult,
  ScheduledTaskRecord,
  ScheduledTasksStatus,
  ToyBoxPrinterProfileRecord,
  ToyBoxDiscoveredPrinter,
  ToyBoxPrinterLiveStatus,
  ToyBoxRouteResult,
  ToyBoxQueueItemRecord,
  ToyBoxFileRecord,
  UserProfile,
  VoiceStatus,
  WorkspaceCopilotTaskResult,
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
  | 'creator'
  | 'gallery'
  | 'toybox'
  | 'memory'
  | 'scheduled'
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
const CHAT_QWEN_MODEL_STORAGE_KEY = 'edison-chat-qwen-model-enabled';
const QWEN_CODING_MODEL_ID = 'qwen3.6-35b-a3b-hauhaucs-coding';

const navigation: Array<{ id: ViewId; label: string; icon: IconType }> = [
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'research', label: 'Research', icon: BookOpen },
  { id: 'organizer', label: 'Organizer', icon: CheckSquare2 },
  { id: 'documents', label: 'Docs', icon: FileText },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'code', label: 'Code Space', icon: Code2 },
  { id: 'media', label: 'Media', icon: GalleryHorizontalEnd },
  { id: 'creator', label: 'Creator', icon: Sparkles },
  { id: 'gallery', label: 'Gallery', icon: Image },
  { id: 'toybox', label: 'Toy Box', icon: Box },
  { id: 'memory', label: 'Memory', icon: Brain },
  { id: 'scheduled', label: 'Scheduled', icon: CalendarDays },
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
  const [wakeWordEnabled, setWakeWordEnabled] = useState(false);
  const [voiceActive, setVoiceActive] = useState(false);
  const [autoStartVoice, setAutoStartVoice] = useState(false);
  const [brioStatus, setBrioStatus] = useState<VoiceStatus | null>(null);
  const [voiceToast, setVoiceToast] = useState<{ transcript: string; reply: string; conversationId?: string | null } | null>(null);
  const lastVoiceIdRef = useRef<number>(-1);
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
  const [workspaceCopilotResult, setWorkspaceCopilotResult] = useState<WorkspaceCopilotTaskResult | null>(null);
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
    useState<boolean>(() => readStoredBoolean(CONTEXT_VISIBILITY_STORAGE_KEY, false));
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
    useState<number>(() => readStoredInt(CHAT_KNOWLEDGE_MATCHES_STORAGE_KEY, 8, 1, 30));
  const [qwenChatModelEnabled, setQwenChatModelEnabled] =
    useState<boolean>(() => readStoredBoolean(CHAT_QWEN_MODEL_STORAGE_KEY, false));
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
    if (activeView === 'media' || activeView === 'creator' || activeView === 'gallery') {
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

  // Poll the on-box Brio voice listener: speak new answers + surface a toast.
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    async function poll() {
      try {
        const status = await edisonApi.getVoiceStatus();
        if (cancelled) return;
        setBrioStatus(status);
        if (lastVoiceIdRef.current < 0) {
          lastVoiceIdRef.current = status.event_count;
        } else {
          const voiceEvents = await edisonApi.getVoiceEvents(lastVoiceIdRef.current);
          if (!cancelled && voiceEvents.length) {
            voiceEvents.forEach((event) => {
              lastVoiceIdRef.current = Math.max(lastVoiceIdRef.current, event.id);
            });
            const latest = voiceEvents[voiceEvents.length - 1];
            setVoiceToast({ transcript: latest.transcript, reply: latest.reply, conversationId: latest.conversation_id });
            speakText(latest.reply);
          }
        }
      } catch {
        /* voice api unavailable */
      }
      if (!cancelled) {
        timer = window.setTimeout(() => void poll(), 1500);
      }
    }
    void poll();
    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, []);

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
    writeStoredBoolean(CHAT_QWEN_MODEL_STORAGE_KEY, qwenChatModelEnabled);
  }, [qwenChatModelEnabled]);

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

  const qwenChatModel = useMemo(
    () => models.find((model) => model.id === QWEN_CODING_MODEL_ID),
    [models],
  );

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

  // "Hey Edison" wake word: opens a fresh chat in voice mode. Runs only while
  // voice mode is off, so it never competes with the in-chat dictation mic.
  useWakeWord(
    wakeWordEnabled && !voiceActive,
    () => {
      startNewConversation();
      setAutoStartVoice(true);
    },
    () => {
      setAutoStartVoice(false);
    },
  );

  async function deleteConversation(conversation: ConversationRecord) {
    if (!window.confirm(`Delete chat "${conversation.title}"?`)) {
      return;
    }
    setError(null);
    try {
      await edisonApi.deleteConversation(conversation.id);
      setConversations((current) => current.filter((item) => item.id !== conversation.id));
      if (activeConversation?.id === conversation.id) {
        setActiveConversation(null);
        setComposer('');
        setActiveMode('auto');
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to delete chat');
    }
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
        preferred_model: qwenChatModelEnabled ? QWEN_CODING_MODEL_ID : null,
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

  async function deleteGalleryArtifact(artifact: ArtifactRecord) {
    if (!window.confirm(`Delete gallery item "${artifact.title}"?`)) {
      return;
    }
    setError(null);
    try {
      await edisonApi.deleteArtifact(artifact.id);
      setMediaArtifacts((current) => current.filter((item) => item.id !== artifact.id));
      setMediaJobs((current) => current.map((job) => (
        job.result_artifact_id === artifact.id
          ? { ...job, result_artifact_id: null }
          : job.source_artifact_id === artifact.id
            ? { ...job, source_artifact_id: null }
            : job
      )));
      await refreshMediaSurface();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to delete gallery item');
    }
  }

  async function deleteGalleryJob(job: JobRecord) {
    if (!window.confirm(`Delete generation job "${job.title}"?`)) {
      return;
    }
    setError(null);
    try {
      await edisonApi.deleteJob(job.id);
      setMediaJobs((current) => current.filter((item) => item.id !== job.id));
      await refreshMediaSurface();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to delete generation job');
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

  async function createMediaGeneration(
    mode: MediaGenerationMode,
    prompt: string,
    referenceFile?: File | null,
    metadata: Record<string, unknown> = {},
  ) {
    setIsMediaBusy(true);
    setError(null);
    try {
      const referenceArtifact = referenceFile ? await edisonApi.uploadArtifact(referenceFile) : null;
      await edisonApi.generateMedia({
        mode,
        prompt,
        reference_artifact_id: referenceArtifact?.id ?? null,
        metadata: {
          ...metadata,
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
    setWorkspaceCopilotResult(null);
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

  async function runWorkspaceCommand(command: WorkspaceCommand | string) {
    const commandPayload =
      typeof command === 'string'
        ? { command: command.trim(), cwd: '.', timeout_seconds: 120, approved: true }
        : { command: command.command, cwd: command.cwd, timeout_seconds: 120, approved: true };
    if (!commandPayload.command) {
      return;
    }
    setIsWorkspaceBusy(true);
    setError(null);
    try {
      const result = await edisonApi.runWorkspaceCommand(commandPayload, activeWorkspaceRootId);
      setWorkspaceCommandResult(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Command run failed');
    } finally {
      setIsWorkspaceBusy(false);
    }
  }

  async function runWorkspaceCopilotTask(instruction: string, runCommands: boolean) {
    const cleanInstruction = instruction.trim();
    if (!cleanInstruction) {
      return;
    }
    setIsWorkspaceBusy(true);
    setError(null);
    try {
      const result = await edisonApi.runWorkspaceCopilotTask(
        {
          instruction: cleanInstruction,
          target_paths: workspaceFile?.path ? [workspaceFile.path] : [],
          preferred_model: 'qwen3.6-35b-a3b-hauhaucs-coding',
          auto_apply: true,
          run_commands: runCommands,
          max_context_files: 8,
        },
        activeWorkspaceRootId,
      );
      setWorkspaceCopilotResult(result);
      const firstFile = result.changes.find((change) => change.file)?.file;
      if (firstFile) {
        setWorkspaceFile(firstFile);
        setWorkspaceDraftContent(firstFile.content);
        setWorkspacePatchPreview(null);
      }
      await refreshWorkspaceSurface(workspacePath);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Code Space Copilot task failed');
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
        {SPEECH_SUPPORTED && (
          <button
            className={wakeWordEnabled ? 'wake-word-button active' : 'wake-word-button'}
            onClick={() => setWakeWordEnabled((value) => !value)}
            title={wakeWordEnabled ? 'Listening for "Hey Edison" — click to disable' : 'Enable the "Hey Edison" wake word'}
            type="button"
          >
            <Mic size={15} />
            <span>{wakeWordEnabled ? 'Hey Edison: On' : 'Hey Edison'}</span>
            {wakeWordEnabled && <span className="wake-word-dot" />}
          </button>
        )}
        {brioStatus?.listening && (
          <div className="brio-pill" title={brioStatus.last_transcript ? `last heard: ${brioStatus.last_transcript}` : 'The Brio mic on the Edison box is listening for "hey edison"'}>
            <Mic size={13} /> Brio mic listening
          </div>
        )}
        {voiceToast && (
          <div className="voice-toast" role="status">
            <div className="voice-toast-head">
              <Mic size={14} /> Heard via Brio
              <button className="voice-toast-close" onClick={() => setVoiceToast(null)} type="button"><X size={13} /></button>
            </div>
            <div className="voice-toast-q">“{voiceToast.transcript}”</div>
            <div className="voice-toast-a">{voiceToast.reply.slice(0, 240)}</div>
            {voiceToast.conversationId && (
              <button
                className="voice-toast-open"
                onClick={() => {
                  const id = voiceToast.conversationId;
                  setVoiceToast(null);
                  if (id) void loadConversation(id);
                }}
                type="button"
              >
                Open chat
              </button>
            )}
          </div>
        )}

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
              <div
                className={conversation.id === activeConversation?.id ? 'conversation-item active' : 'conversation-item'}
                key={conversation.id}
              >
                <button
                  className="conversation-open-button"
                  onClick={() => void loadConversation(conversation.id)}
                  type="button"
                >
                  <span>{conversation.title}</span>
                  <small>{conversation.mode}</small>
                </button>
                <button
                  aria-label={`Delete chat ${conversation.title}`}
                  className="conversation-delete-button"
                  onClick={() => void deleteConversation(conversation)}
                  title="Delete chat"
                  type="button"
                >
                  <Trash2 size={14} />
                </button>
              </div>
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
            <RealtimeChip />
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
            {activeView === 'chat' && activeConversation && (
              <RememberChatButton conversationId={activeConversation.id} />
            )}
          </div>
        </header>

        {error && <div className="error-banner">{friendlyError(error)}</div>}

        {activeView === 'chat' ? (
          <ChatView
            autoStartVoice={autoStartVoice}
            onAutoVoiceConsumed={() => setAutoStartVoice(false)}
            onVoiceActiveChange={setVoiceActive}
            activeConversation={activeConversation}
            activeAgentRun={activeAgentRun}
            agentRuns={agentRuns}
            composer={composer}
            handleSend={handleSend}
            isSending={isSending}
            agentModeEnabled={agentModeEnabled}
            modelSelection={modelSelection}
            qwenChatModel={qwenChatModel}
            qwenChatModelEnabled={qwenChatModelEnabled}
            setComposer={setComposer}
            setAgentModeEnabled={setAgentModeEnabled}
            setQwenChatModelEnabled={setQwenChatModelEnabled}
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
            onExitToChat={() => setActiveView('chat')}
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
            onDeleteArtifact={deleteGalleryArtifact}
            onDeleteJob={deleteGalleryJob}
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
            workspaceCopilotResult={workspaceCopilotResult}
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
            onRunWorkspaceCopilotTask={runWorkspaceCopilotTask}
            onRunWorkspaceCommand={runWorkspaceCommand}
            onAddChatContextPath={addChatContextPath}
          />
        )}
      </main>
    </div>
  );
}

function stripForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, '. (code block omitted). ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[#*_>~|]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 700);
}

let cachedVoice: SpeechSynthesisVoice | null = null;
let voiceListenerAttached = false;

function pickJarvisVoice(): SpeechSynthesisVoice | null {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    return null;
  }
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) {
    return null;
  }
  const preferred = ['Google UK English Male', 'Microsoft Ryan', 'Microsoft George', 'Microsoft Thomas', 'Daniel', 'Arthur', 'Oliver'];
  for (const name of preferred) {
    const match = voices.find((voice) => voice.name === name) ?? voices.find((voice) => voice.name.includes(name));
    if (match) {
      return match;
    }
  }
  const gbMale = voices.find((voice) => voice.lang === 'en-GB' && /male|ryan|george|daniel|arthur|thomas|oliver/i.test(voice.name));
  if (gbMale) {
    return gbMale;
  }
  return voices.find((voice) => voice.lang === 'en-GB') ?? voices.find((voice) => voice.lang.startsWith('en')) ?? voices[0];
}

function speakText(text: string, handlers: { onStart?: () => void; onEnd?: () => void } = {}): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    return;
  }
  const clean = stripForSpeech(text);
  if (!clean) {
    return;
  }
  if (!voiceListenerAttached) {
    voiceListenerAttached = true;
    window.speechSynthesis.onvoiceschanged = () => {
      cachedVoice = pickJarvisVoice();
    };
  }
  if (!cachedVoice) {
    cachedVoice = pickJarvisVoice();
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(clean);
  if (cachedVoice) {
    utterance.voice = cachedVoice;
  }
  utterance.lang = cachedVoice?.lang ?? 'en-GB';
  utterance.rate = 1.07;
  utterance.pitch = 0.9;
  if (handlers.onStart) {
    utterance.onstart = handlers.onStart;
  }
  utterance.onend = () => handlers.onEnd?.();
  utterance.onerror = () => handlers.onEnd?.();
  window.speechSynthesis.speak(utterance);
}

function useVoice(onTranscript: (text: string) => void) {
  const [enabled, setEnabled] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const recRef = useRef<any>(null);
  const SR = typeof window !== 'undefined' ? ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition) : null;
  const sttSupported = Boolean(SR);
  const ttsSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  const startListening = useCallback(() => {
    if (!SR || recRef.current) return;
    const rec = new SR();
    rec.lang = 'en-US';
    rec.interimResults = false;
    rec.continuous = false;
    rec.onstart = () => setListening(true);
    rec.onend = () => { setListening(false); recRef.current = null; };
    rec.onerror = () => { setListening(false); recRef.current = null; };
    rec.onresult = (event: any) => {
      const text = Array.from(event.results).map((r: any) => r[0]?.transcript ?? '').join(' ').trim();
      if (text) onTranscript(text);
    };
    recRef.current = rec;
    try { rec.start(); } catch { recRef.current = null; }
  }, [SR, onTranscript]);

  const stopListening = useCallback(() => {
    try { recRef.current?.stop(); } catch { /* noop */ }
    recRef.current = null;
    setListening(false);
  }, []);

  const speak = useCallback((text: string) => {
    if (!ttsSupported) return;
    speakText(text, { onStart: () => setSpeaking(true), onEnd: () => setSpeaking(false) });
  }, [ttsSupported]);

  const cancelSpeak = useCallback(() => {
    if (ttsSupported) window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [ttsSupported]);

  return { enabled, setEnabled, listening, speaking, startListening, stopListening, speak, cancelSpeak, sttSupported, ttsSupported };
}

const SPEECH_SUPPORTED =
  typeof window !== 'undefined' && (('webkitSpeechRecognition' in window) || ('SpeechRecognition' in window));

function useWakeWord(active: boolean, onWake: () => void, onStop: () => void) {
  const onWakeRef = useRef(onWake);
  const onStopRef = useRef(onStop);
  useEffect(() => {
    onWakeRef.current = onWake;
    onStopRef.current = onStop;
  });
  useEffect(() => {
    const SR = typeof window !== 'undefined' ? ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition) : null;
    if (!active || !SR) {
      return undefined;
    }
    let stopped = false;
    let firedAt = 0;
    const rec = new SR();
    rec.lang = 'en-US';
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (event: any) => {
      const text = Array.from(event.results).map((r: any) => r[0]?.transcript ?? '').join(' ').toLowerCase();
      const now = typeof performance !== 'undefined' ? performance.now() : 0;
      if (/\bedison stop\b|\bstop edison\b/.test(text)) {
        onStopRef.current();
      } else if ((text.includes('hey edison') || text.includes('hey, edison') || text.includes('hey addison') || text.includes('a edison')) && now - firedAt > 3500) {
        firedAt = now;
        onWakeRef.current();
      }
    };
    rec.onend = () => {
      if (!stopped) {
        try { rec.start(); } catch { /* noop */ }
      }
    };
    rec.onerror = () => { /* onend handler restarts */ };
    try { rec.start(); } catch { /* noop */ }
    return () => {
      stopped = true;
      try { rec.stop(); } catch { /* noop */ }
    };
  }, [active]);
}

function VoiceAvatar({ listening, speaking }: { listening: boolean; speaking: boolean }) {
  const status = speaking ? 'Speaking…' : listening ? 'Listening…' : 'Voice ready';
  return (
    <div className="voice-avatar" aria-hidden="true">
      <div className={`voice-orb ${speaking ? 'speaking' : ''} ${listening && !speaking ? 'listening' : ''}`}>
        <div className="voice-orb-ring" />
        <div className="voice-face">
          <div className="voice-eyes"><span /><span /></div>
          <div className="voice-mouth" />
        </div>
      </div>
      <div className="voice-status">{status}</div>
    </div>
  );
}

function ChatView({
  autoStartVoice,
  onAutoVoiceConsumed,
  onVoiceActiveChange,
  activeConversation,
  activeAgentRun,
  agentModeEnabled,
  agentRuns,
  composer,
  handleSend,
  isSending,
  modelSelection,
  qwenChatModel,
  qwenChatModelEnabled,
  setComposer,
  setAgentModeEnabled,
  setQwenChatModelEnabled,
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
  autoStartVoice: boolean;
  onAutoVoiceConsumed: () => void;
  onVoiceActiveChange: (active: boolean) => void;
  activeConversation: ConversationWithMessages | null;
  activeAgentRun: AgentRunWithEvents | null;
  agentModeEnabled: boolean;
  agentRuns: AgentRunRecord[];
  composer: string;
  handleSend: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  isSending: boolean;
  modelSelection: ModelSelection | null;
  qwenChatModel?: ModelProfile;
  qwenChatModelEnabled: boolean;
  setComposer: (value: string) => void;
  setAgentModeEnabled: (value: boolean) => void;
  setQwenChatModelEnabled: (value: boolean) => void;
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
  const selectedModelName = qwenChatModelEnabled
    ? qwenChatModel?.display_name ?? 'Qwen3.6 35B A3B'
    : modelSelection?.model.display_name ?? 'Auto model lane';
  const modelRouteLabel = qwenChatModelEnabled ? 'Qwen forced' : 'Auto routing';
  const selectedModelStatus = qwenChatModelEnabled
    ? qwenChatModel?.status.replace('_', ' ') ?? 'not registered'
    : modelSelection?.model.status.replace('_', ' ') ?? 'auto';
  const qwenToggleTitle = qwenChatModelEnabled
    ? 'Use automatic Edison model routing for normal chat'
    : 'Force normal chat to use the Qwen3.6 35B GPU model';
  const intentLabel = modelSelection?.mode
    ? `Intent ${modelSelection.mode.replace('_', ' ')}`
    : 'Intent auto';
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const lastMessage = activeConversation?.messages[activeConversation.messages.length - 1];
  const composerFormRef = useRef<HTMLFormElement | null>(null);
  const lastSpokenRef = useRef<string | null>(null);
  const [voiceSubmit, setVoiceSubmit] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const voice = useVoice((text) => {
    setComposer(text);
    setVoiceSubmit(true);
  });
  const {
    enabled: voiceEnabled,
    listening: voiceListening,
    speaking: voiceSpeaking,
    startListening: voiceStart,
    stopListening: voiceStop,
    speak: voiceSpeak,
    cancelSpeak: voiceCancel,
    setEnabled: setVoiceEnabled,
    sttSupported,
  } = voice;

  function toggleVoice() {
    if (voiceEnabled) {
      setVoiceEnabled(false);
      voiceStop();
      voiceCancel();
      return;
    }
    if (typeof window !== 'undefined' && !window.isSecureContext) {
      setVoiceNote('Voice needs a secure connection. Open Edison at https://… (not http://) and accept the certificate, then click Voice again.');
      return;
    }
    setVoiceNote(null);
    // Don't read the previous reply aloud — only speak replies that arrive after this point.
    lastSpokenRef.current = lastMessage?.id ?? null;
    setVoiceEnabled(true);
    voiceStart();
  }

  // Auto-send a finished dictation, or turn voice off on a stop-word.
  useEffect(() => {
    if (!voiceSubmit) {
      return;
    }
    const lowered = composer.trim().toLowerCase();
    if (lowered === 'stop' || lowered === 'edison stop' || lowered === 'stop edison' || lowered === 'edison, stop') {
      setVoiceEnabled(false);
      voiceStop();
      voiceCancel();
      setComposer('');
      setVoiceSubmit(false);
      return;
    }
    if (composer.trim()) {
      composerFormRef.current?.requestSubmit();
      setVoiceSubmit(false);
    }
  }, [voiceSubmit, composer]);

  // Enter voice mode automatically when launched by the "Hey Edison" wake word.
  useEffect(() => {
    if (autoStartVoice && !voiceEnabled) {
      lastSpokenRef.current = lastMessage?.id ?? null;
      setVoiceEnabled(true);
      voiceStart();
      onAutoVoiceConsumed();
    }
  }, [autoStartVoice, voiceEnabled, voiceStart, onAutoVoiceConsumed]);

  // Report voice-active state up so the wake-word listener pauses while voice is on.
  useEffect(() => {
    onVoiceActiveChange(voiceEnabled);
  }, [voiceEnabled, onVoiceActiveChange]);

  // Speak new assistant replies aloud while voice mode is on.
  useEffect(() => {
    if (!voiceEnabled || isSending || !lastMessage || lastMessage.role !== 'assistant') {
      return;
    }
    if (lastSpokenRef.current === lastMessage.id) {
      return;
    }
    lastSpokenRef.current = lastMessage.id;
    voiceSpeak(lastMessage.content);
  }, [voiceEnabled, isSending, lastMessage?.id, lastMessage?.role, lastMessage?.content, voiceSpeak]);

  // Keep the mic listening between turns (hands-free loop).
  useEffect(() => {
    if (voiceEnabled && !isSending && !voiceSpeaking && !voiceListening) {
      const timer = window.setTimeout(() => voiceStart(), 500);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [voiceEnabled, isSending, voiceSpeaking, voiceListening, voiceStart]);

  // Stop microphone + speech when leaving chat.
  useEffect(() => () => { voiceStop(); voiceCancel(); }, [voiceStop, voiceCancel]);

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
              max={30}
              value={chatKnowledgeMatches}
              onChange={(event) => {
                const parsed = Number.parseInt(event.target.value, 10);
                if (!Number.isNaN(parsed)) {
                  setChatKnowledgeMatches(Math.max(1, Math.min(30, parsed)));
                }
              }}
            />
          </section>
        </div>
      </details>
      <MemoryProfileDrawer />
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
      {(agentRuns.length > 0 || activeAgentRun) && (
        <details className="context-drawer agent-run-drawer">
          <summary>
            <span><Waypoints size={16} /> Agent runs</span>
            <small>{activeAgentRun ? activeAgentRun.title : `${agentRuns.length} run${agentRuns.length === 1 ? '' : 's'}`}</small>
          </summary>
          <div className="context-drawer-content">
            <AgentRunDock
              activeRun={activeAgentRun}
              runs={agentRuns}
              onSelectRun={onSelectAgentRun}
            />
          </div>
        </details>
      )}
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

      <section className="composer-panel" aria-label="Message composer">
        <div className="composer-meta">
          <span>{intentLabel}</span>
          <span>{modelRouteLabel}</span>
          <span>{selectedModelName}</span>
          <span>{selectedModelStatus}</span>
          <button
            className={qwenChatModelEnabled ? 'composer-toggle qwen-toggle active' : 'composer-toggle qwen-toggle'}
            onClick={() => setQwenChatModelEnabled(!qwenChatModelEnabled)}
            title={qwenToggleTitle}
            type="button"
          >
            <Brain size={14} />
            <span>{qwenChatModelEnabled ? 'Qwen On' : 'Auto LLM'}</span>
          </button>
          <button
            className={agentModeEnabled ? 'composer-toggle active' : 'composer-toggle'}
            onClick={() => setAgentModeEnabled(!agentModeEnabled)}
            title="Let Edison plan and use tool-capable agent workflows"
            type="button"
          >
            <Waypoints size={14} />
            <span>Agent</span>
          </button>
          {sttSupported && (
            <button
              className={`composer-toggle voice-toggle ${voiceEnabled ? 'active' : ''} ${voiceListening ? 'listening' : ''}`}
              onClick={toggleVoice}
              title="Voice mode — talk to Edison and hear replies"
              type="button"
            >
              <Mic size={14} />
              <span>{voiceEnabled ? (voiceListening ? 'Listening' : voiceSpeaking ? 'Speaking' : 'Voice On') : 'Voice'}</span>
            </button>
          )}
        </div>
        {voiceNote && <div className="voice-note">{voiceNote}</div>}
        <form className="composer" ref={composerFormRef} onSubmit={(event) => void handleSend(event)}>
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
        {voiceEnabled && <VoiceAvatar listening={voiceListening} speaking={voiceSpeaking} />}
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
  onDeleteArtifact,
  onDeleteJob,
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
  onRunWorkspaceCopilotTask,
  onRunWorkspaceCommand,
  onAddChatContextPath,
  onExitToChat,
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
  workspaceCopilotResult,
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
  onDeleteArtifact: (artifact: ArtifactRecord) => Promise<void> | void;
  onDeleteJob: (job: JobRecord) => Promise<void> | void;
  onCreateWorkspaceProject: (name: string, prompt: string) => Promise<void>;
  onCreateMediaJob: (jobType: JobType, title: string, prompt: string) => Promise<void>;
  onCreateMediaGeneration: (mode: MediaGenerationMode, prompt: string, referenceFile?: File | null, metadata?: Record<string, unknown>) => Promise<void>;
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
  onRunWorkspaceCopilotTask: (instruction: string, runCommands: boolean) => Promise<void>;
  onRunWorkspaceCommand: (command: WorkspaceCommand | string) => Promise<void>;
  onAddChatContextPath: (path: string) => void;
  onExitToChat: () => void;
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
  workspaceCopilotResult: WorkspaceCopilotTaskResult | null;
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
        copilotResult={workspaceCopilotResult}
        entries={workspaceEntries}
        draftContent={workspaceDraftContent}
        file={workspaceFile}
        isBusy={isWorkspaceBusy}
        onApplyPatch={onApplyWorkspacePatch}
        onCreateProject={onCreateWorkspaceProject}
        onOpenEntry={onOpenWorkspaceEntry}
        onParent={onWorkspaceParent}
        onPreviewPatch={onPreviewWorkspacePatch}
        onRunCopilotTask={onRunWorkspaceCopilotTask}
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
  if (activeView === 'creator') {
    return (
      <CreatorStudioView
        artifacts={artifacts}
        isMediaBusy={isMediaBusy}
        jobs={mediaJobs}
        modes={mediaModes}
        mediaStatus={mediaStatus}
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
        onDeleteArtifact={onDeleteArtifact}
        onDeleteJob={onDeleteJob}
        onRefresh={onRefreshMedia}
        onUseArtifactInChat={onUseArtifactInChat}
        runtimeSettings={runtimeSettings}
      />
    );
  }
  if (activeView === 'scheduled') {
    return <ScheduledView />;
  }
  if (activeView === 'toybox') {
    return <ToyBoxView />;
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
      onClose={onExitToChat}
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

function CreatorLabPanel({
  creatorArtifacts,
  lastPrompt,
}: {
  creatorArtifacts: ArtifactRecord[];
  lastPrompt: string;
}) {
  const [overview, setOverview] = useState<CreatorLabOverview | null>(null);
  const [activeDataset, setActiveDataset] = useState<CreatorLabDataset | null>(null);
  const [graph, setGraph] = useState<CreatorWorkflowGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newName, setNewName] = useState('');
  const [newLora, setNewLora] = useState('sdxl');
  const [reviewPrompt, setReviewPrompt] = useState('');
  const [reviewImageId, setReviewImageId] = useState('');
  const [critique, setCritique] = useState<CreatorVlmCritique | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [autoReview, setAutoReview] = useState<CreatorVlmCritique | null>(null);
  const [trainSteps, setTrainSteps] = useState(1600);
  const [trainDim, setTrainDim] = useState(16);
  const [trainGpus, setTrainGpus] = useState<number[]>([]);
  const [jobs, setJobs] = useState<CreatorTrainingJob[]>([]);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const lastReviewedRef = useRef<string>('');

  const loadOverview = useCallback(async () => {
    try {
      const data = await edisonApi.getCreatorLabOverview();
      setOverview(data);
      setError(null);
      if (data.active_dataset_id) {
        const dataset = await edisonApi.getCreatorDataset(data.active_dataset_id).catch(() => null);
        setActiveDataset(dataset);
      } else {
        setActiveDataset(null);
      }
      const workflowId = data.active_workflow ?? data.workflows[0]?.id;
      if (workflowId) {
        const wf = await edisonApi.getCreatorWorkflowGraph(workflowId).catch(() => null);
        setGraph(wf);
      }
      if (!trainGpus.length && data.gpus.length) {
        const best = [...data.gpus].sort(
          (a, b) => (b.memory_total_mb ?? 0) - (b.memory_used_mb ?? 0) - ((a.memory_total_mb ?? 0) - (a.memory_used_mb ?? 0)),
        )[0];
        setTrainGpus(best ? [best.index] : [data.gpus[0].index]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load Creator Lab.');
    }
  }, [trainGpus.length]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  // Poll training jobs while any are active.
  useEffect(() => {
    let timer: number | undefined;
    const tick = async () => {
      const list = await edisonApi.listCreatorTrainingJobs().catch(() => [] as CreatorTrainingJob[]);
      setJobs(list);
      if (list.some((job) => job.status === 'running' || job.status === 'preparing' || job.status === 'queued')) {
        timer = window.setTimeout(() => void tick(), 5000);
      }
    };
    void tick();
    return () => {
      if (timer) window.clearTimeout(timer);
    };
  }, [overview?.root_path]);

  // Auto-review the newest creator render against the prompt (user opted in).
  useEffect(() => {
    const latest = creatorArtifacts.find((art) => art.kind === 'image' || (art.mime_type ?? '').startsWith('image'));
    if (!latest || latest.id === lastReviewedRef.current) {
      return;
    }
    lastReviewedRef.current = latest.id;
    const target = latest.path || edisonApi.artifactDownloadUrl(latest.id);
    void edisonApi
      .creatorVlmCritique({ image_url: target, prompt: lastPrompt || String(latest.metadata?.prompt ?? '') })
      .then((result) => setAutoReview(result))
      .catch(() => undefined);
  }, [creatorArtifacts, lastPrompt]);

  async function selectLora(id: string) {
    setOverview((cur) => (cur ? { ...cur, active_lora_type: id } : cur));
    await edisonApi.setCreatorSelection({ active_lora_type: id }).catch(() => undefined);
  }
  async function selectWorkflow(id: string) {
    setOverview((cur) => (cur ? { ...cur, active_workflow: id } : cur));
    const wf = await edisonApi.getCreatorWorkflowGraph(id).catch(() => null);
    setGraph(wf);
    await edisonApi.setCreatorSelection({ active_workflow: id }).catch(() => undefined);
  }
  async function selectDataset(id: string) {
    setBusy(true);
    await edisonApi.setCreatorSelection({ active_dataset_id: id }).catch(() => undefined);
    const dataset = await edisonApi.getCreatorDataset(id).catch(() => null);
    setActiveDataset(dataset);
    setReviewImageId(dataset?.images[0]?.id ?? '');
    setOverview((cur) => (cur ? { ...cur, active_dataset_id: id } : cur));
    setBusy(false);
  }
  async function createDataset() {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const dataset = await edisonApi.createCreatorDataset({ name, lora_type: newLora });
      setNewName('');
      await loadOverview();
      await selectDataset(dataset.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create dataset.');
    } finally {
      setBusy(false);
    }
  }
  async function importPhotos(files: FileList | null) {
    if (!files || !files.length || !activeDataset) return;
    setBusy(true);
    try {
      const updated = await edisonApi.uploadCreatorImages(activeDataset.id, Array.from(files));
      setActiveDataset(updated);
      if (!reviewImageId && updated.images[0]) setReviewImageId(updated.images[0].id);
      await loadOverview();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.');
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }
  async function removeImage(imageId: string) {
    if (!activeDataset) return;
    const updated = await edisonApi.deleteCreatorImage(activeDataset.id, imageId).catch(() => null);
    if (updated) setActiveDataset(updated);
  }
  async function removeDataset() {
    if (!activeDataset) return;
    await edisonApi.deleteCreatorDataset(activeDataset.id).catch(() => undefined);
    setActiveDataset(null);
    await loadOverview();
  }
  async function runReview() {
    if (!activeDataset || !reviewImageId) return;
    setReviewing(true);
    setCritique(null);
    try {
      const result = await edisonApi.creatorVlmCritique({
        dataset_id: activeDataset.id,
        image_id: reviewImageId,
        prompt: reviewPrompt.trim() || `${activeDataset.trigger_token} persona reference`,
      });
      setCritique(result);
    } catch (err) {
      setCritique({ status: 'error', notes: err instanceof Error ? err.message : 'Review failed.', suggestions: [] });
    } finally {
      setReviewing(false);
    }
  }
  function toggleTrainGpu(index: number) {
    setTrainGpus((cur) => (cur.includes(index) ? cur.filter((g) => g !== index) : [...cur, index]));
  }
  async function startTraining() {
    if (!activeDataset || !activeDataset.image_count) return;
    setBusy(true);
    setError(null);
    try {
      await edisonApi.startCreatorTraining({
        dataset_id: activeDataset.id,
        steps: trainSteps,
        network_dim: trainDim,
        gpu_ids: trainGpus,
      });
      const list = await edisonApi.listCreatorTrainingJobs().catch(() => [] as CreatorTrainingJob[]);
      setJobs(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start training.');
    } finally {
      setBusy(false);
    }
  }
  async function cancelTraining(jobId: string) {
    await edisonApi.cancelCreatorTraining(jobId).catch(() => undefined);
    const list = await edisonApi.listCreatorTrainingJobs().catch(() => [] as CreatorTrainingJob[]);
    setJobs(list);
  }

  if (!overview) {
    return (
      <section className="creator-lab-panel" aria-label="Creator Lab">
        <div className="section-heading"><Box size={18} /><h3>Creator Lab</h3></div>
        <div className="empty-line">{error ?? 'Loading datasets, LoRA types, and GPUs...'}</div>
      </section>
    );
  }

  const datasets = overview.datasets;
  const activeLora = overview.active_lora_type ?? 'sdxl';
  const activeWorkflow = overview.active_workflow ?? overview.workflows[0]?.id;
  const datasetReady = (activeDataset?.image_count ?? 0) > 0;

  return (
    <section className="creator-lab-panel" aria-label="Creator Lab">
      <div className="section-heading">
        <Box size={18} />
        <h3>Creator Lab — Datasets, LoRA &amp; Training</h3>
        <button className="secondary-button icon-text-button" onClick={() => void loadOverview()} type="button">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>
      {error && <div className="memory-inline-result error">{error}</div>}

      {/* GPU strip */}
      <div className="creator-gpu-strip">
        {overview.gpus.map((gpu) => {
          const used = gpu.memory_used_mb ?? 0;
          const total = gpu.memory_total_mb ?? 1;
          const pct = Math.min(100, Math.round((used / total) * 100));
          return (
            <article className="creator-gpu-card" key={gpu.index}>
              <div className="creator-gpu-head"><Cpu size={14} /> GPU {gpu.index} · {gpu.name.replace('NVIDIA GeForce ', '')}</div>
              <div className="creator-gpu-bar"><span style={{ width: `${pct}%` }} /></div>
              <small>{Math.round(used / 1024)}/{Math.round(total / 1024)} GB · {gpu.utilization ?? 0}% · {gpu.temperature ?? '–'}°C</small>
            </article>
          );
        })}
      </div>

      <div className="creator-lab-grid">
        {/* Left: toggles + datasets */}
        <div className="creator-lab-col">
          <div className="creator-toggle-block">
            <span className="section-label"><SlidersHorizontal size={13} /> LoRA model type</span>
            <div className="creator-mode-tabs">
              {overview.lora_types.map((lora) => (
                <button
                  className={activeLora === lora.id ? 'mode-button active' : 'mode-button'}
                  disabled={!lora.available}
                  key={lora.id}
                  onClick={() => void selectLora(lora.id)}
                  title={lora.detail ?? undefined}
                  type="button"
                >
                  {lora.label}{!lora.available && ' ·needs model'}
                </button>
              ))}
            </div>
          </div>

          <div className="creator-toggle-block">
            <span className="section-label"><Waypoints size={13} /> Workflow</span>
            <div className="creator-mode-tabs">
              {overview.workflows.map((wf) => (
                <button
                  className={activeWorkflow === wf.id ? 'mode-button active' : 'mode-button'}
                  key={wf.id}
                  onClick={() => void selectWorkflow(wf.id)}
                  title={wf.detail ?? undefined}
                  type="button"
                >
                  {wf.label}
                </button>
              ))}
            </div>
          </div>

          <div className="creator-toggle-block">
            <span className="section-label"><Database size={13} /> Datasets</span>
            <div className="creator-dataset-chips">
              {datasets.map((dataset) => (
                <button
                  className={overview.active_dataset_id === dataset.id ? 'dataset-chip active' : 'dataset-chip'}
                  key={dataset.id}
                  onClick={() => void selectDataset(dataset.id)}
                  type="button"
                >
                  {dataset.name} <span>{dataset.image_count}</span>
                </button>
              ))}
              {datasets.length === 0 && <div className="empty-line">No datasets yet — create one below.</div>}
            </div>
            <div className="creator-new-dataset">
              <input onChange={(e) => setNewName(e.target.value)} placeholder="New dataset name" value={newName} />
              <button className="secondary-button icon-text-button" disabled={!newName.trim() || busy} onClick={() => void createDataset()} type="button">
                <Database size={14} /> Create
              </button>
            </div>
          </div>

          {activeDataset && (
            <div className="creator-dataset-detail">
              <div className="creator-dataset-detail-head">
                <strong>{activeDataset.name}</strong>
                <span className="assistant-model-chip">trigger: {activeDataset.trigger_token}</span>
                <button className="icon-button" onClick={() => void removeDataset()} title="Delete dataset" type="button"><Trash2 size={14} /></button>
              </div>
              <div className="creator-image-grid">
                {activeDataset.images.map((img) => (
                  <div className="creator-image-thumb" key={img.id}>
                    <img alt={img.filename} loading="lazy" src={`${edisonApi.apiBase}${img.url}`} />
                    <button className="thumb-remove" onClick={() => void removeImage(img.id)} title="Remove" type="button"><X size={12} /></button>
                  </div>
                ))}
                <button className="creator-image-add" disabled={busy} onClick={() => fileRef.current?.click()} type="button">
                  <Upload size={18} /><span>Import photos</span>
                </button>
                <input accept="image/*" hidden multiple onChange={(e) => void importPhotos(e.target.files)} ref={fileRef} type="file" />
              </div>
            </div>
          )}
        </div>

        {/* Right: ComfyUI workflow side panel */}
        <aside className="creator-workflow-side" aria-label="ComfyUI workflow">
          <div className="section-label"><Waypoints size={13} /> ComfyUI workflow {graph ? `· ${graph.label}` : ''}</div>
          <div className="creator-node-list">
            {graph?.nodes.map((node, idx) => (
              <article className="creator-node" key={node.id}>
                <div className="creator-node-top"><span className="creator-node-idx">{idx + 1}</span><strong>{node.title}</strong></div>
                <span className="creator-node-type">{node.type}</span>
                {node.summary && <small>{node.summary}</small>}
              </article>
            ))}
            {!graph && <div className="empty-line">Select a workflow to view its graph.</div>}
          </div>
        </aside>
      </div>

      {/* VLM review */}
      <div className="creator-review-block">
        <div className="section-heading"><Sparkles size={16} /><h3>VLM Result Review</h3><span className="assistant-model-chip">{String(overview.metadata?.vision_model ?? 'qwen2.5-VL')}</span></div>
        <p className="assistant-intro">Renders are auto-scored against your prompt by the vision model. You can also test any dataset image here.</p>
        {autoReview && (
          <div className={`creator-critique ${autoReview.matches ? 'good' : 'warn'}`}>
            <strong>Latest render · {autoReview.score ?? '–'}/100 · {autoReview.verdict ?? autoReview.status}</strong>
            {autoReview.notes && <p>{autoReview.notes}</p>}
            {autoReview.suggestions.length > 0 && <ul>{autoReview.suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>}
          </div>
        )}
        {activeDataset && activeDataset.images.length > 0 && (
          <div className="creator-review-controls">
            <select onChange={(e) => setReviewImageId(e.target.value)} value={reviewImageId}>
              {activeDataset.images.map((img) => <option key={img.id} value={img.id}>{img.filename}</option>)}
            </select>
            <input onChange={(e) => setReviewPrompt(e.target.value)} placeholder="What should this image show?" value={reviewPrompt} />
            <button className="secondary-button icon-text-button" disabled={reviewing || !reviewImageId} onClick={() => void runReview()} type="button">
              <Sparkles size={14} /> {reviewing ? 'Reviewing…' : 'Test with VLM'}
            </button>
          </div>
        )}
        {critique && (
          <div className={`creator-critique ${critique.matches ? 'good' : 'warn'}`}>
            <strong>{critique.score ?? '–'}/100 · {critique.verdict ?? critique.status}</strong>
            {critique.notes && <p>{critique.notes}</p>}
            {critique.suggestions.length > 0 && <ul>{critique.suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>}
          </div>
        )}
      </div>

      {/* Training */}
      <div className="creator-training-block">
        <div className="section-heading"><Zap size={16} /><h3>LoRA Training</h3>{!overview.training_available && <span className="backend-status offline">toolchain missing</span>}</div>
        <p className="assistant-intro">
          Train an SDXL LoRA on the selected dataset across your GPUs (kohya sd-scripts). The finished LoRA is published to ComfyUI automatically.
        </p>
        <div className="creator-train-controls">
          <label>Steps<input min={100} max={20000} onChange={(e) => setTrainSteps(Number(e.target.value) || 1600)} type="number" value={trainSteps} /></label>
          <label>Network dim<input min={4} max={128} onChange={(e) => setTrainDim(Number(e.target.value) || 16)} type="number" value={trainDim} /></label>
          <div className="creator-gpu-pick">
            <span className="section-label"><Cpu size={13} /> GPUs</span>
            {overview.gpus.map((gpu) => (
              <button
                className={trainGpus.includes(gpu.index) ? 'gpu-chip active' : 'gpu-chip'}
                key={gpu.index}
                onClick={() => toggleTrainGpu(gpu.index)}
                type="button"
              >
                {gpu.index}:{gpu.name.includes('3090') ? '3090' : gpu.name.replace('NVIDIA GeForce RTX ', '')}
              </button>
            ))}
          </div>
          <button
            className="apply-button icon-text-button"
            disabled={!datasetReady || !overview.training_available || busy || !trainGpus.length}
            onClick={() => void startTraining()}
            type="button"
          >
            <Zap size={15} /> Train LoRA
          </button>
        </div>
        {!datasetReady && <small className="creator-train-hint">Select a dataset with images to enable training.</small>}
        <div className="creator-job-list">
          {jobs.map((job) => (
            <article className={`creator-job ${job.status}`} key={job.id}>
              <div className="creator-job-head">
                <strong>{job.lora_name ?? job.id}</strong>
                <span className={`backend-status ${job.status === 'completed' ? 'ready' : job.status === 'failed' ? 'offline' : 'degraded'}`}>{job.status}</span>
              </div>
              <div className="creator-job-bar"><span style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
              <small>{job.current_step}/{job.total_steps} steps · GPU {job.gpu_ids.join(',')} {job.detail ? `· ${job.detail}` : ''}</small>
              {(job.status === 'running' || job.status === 'preparing') && (
                <button className="icon-button" onClick={() => void cancelTraining(job.id)} title="Cancel" type="button"><X size={13} /> stop</button>
              )}
            </article>
          ))}
          {jobs.length === 0 && <div className="empty-line">No training runs yet.</div>}
        </div>
      </div>
    </section>
  );
}

function CreatorStudioView({
  artifacts,
  isMediaBusy,
  jobs,
  modes,
  mediaStatus,
  onCreateGeneration,
  onRefresh,
  onUseArtifactInChat,
}: {
  artifacts: ArtifactRecord[];
  isMediaBusy: boolean;
  jobs: JobRecord[];
  modes: MediaGenerationModeRecord[];
  mediaStatus: MediaSystemStatus | null;
  onCreateGeneration: (mode: MediaGenerationMode, prompt: string, referenceFile?: File | null, metadata?: Record<string, unknown>) => Promise<void>;
  onRefresh: () => Promise<void>;
  onUseArtifactInChat: (artifact: ArtifactRecord) => void;
}) {
  const modeOptions = modes.length ? modes : fallbackMediaModes();
  const creatorModes = modeOptions.filter((mode) => mode.group === 'creator');
  const safeCreatorModes = creatorModes.length ? creatorModes : fallbackMediaModes().filter((mode) => mode.group === 'creator');
  const [selectedMode, setSelectedMode] = useState<MediaGenerationMode>('creator_photo');
  const [prompt, setPrompt] = useState('');
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState('');
  const [lastGeneratedPrompt, setLastGeneratedPrompt] = useState('');
  const [assistInput, setAssistInput] = useState('');
  const [assistThread, setAssistThread] = useState<
    Array<{ role: 'user' | 'assistant'; content: string; actions?: CreatorStudioAssistAction[] }>
  >([]);
  const [assistBusy, setAssistBusy] = useState(false);
  const [assistError, setAssistError] = useState<string | null>(null);
  const activeMode = safeCreatorModes.find((mode) => mode.id === selectedMode) ?? safeCreatorModes[0];
  const creatorStatus = mediaStatus?.creator_studio;
  const datasets = creatorStatus?.datasets ?? [];
  const restrictedAssets = creatorStatus?.restricted_assets ?? [];
  const restrictedModelCount = restrictedAssets.filter((asset) => asset.kind === 'model').length;
  const creatorPlanningModel = String(creatorStatus?.metadata.planning_model ?? 'qwen3.6-35b-a3b-hauhaucs-coding');
  const activeDataset = datasets.find((dataset) => dataset.id === selectedDatasetId) ?? datasets.find((dataset) => dataset.status === 'ready') ?? datasets[0] ?? null;
  const creatorJobs = jobs.filter((job) => String(job.metadata.generation_mode ?? '').startsWith('creator_'));
  const creatorJobIds = new Set(creatorJobs.map((job) => job.id));
  const creatorArtifacts = artifacts.filter((artifact) => {
    const generationMode = String(artifact.metadata.generation_mode ?? '');
    return generationMode.startsWith('creator_') || (artifact.source_job_id ? creatorJobIds.has(artifact.source_job_id) : false);
  });
  const statusCards = [
    ['Asset Pack', creatorStatus?.status ?? 'setup_required', creatorStatus?.normalized_root ?? creatorStatus?.source_path ?? 'No creator bundle path'],
    ['Datasets', String(datasets.filter((dataset) => dataset.status === 'ready').length), `${datasets.length} detected safe dataset folder(s)`],
    ['Templates', String(creatorStatus?.workflow_templates.length ?? 0), (creatorStatus?.workflow_templates ?? []).slice(0, 2).join(', ') || 'No workflow templates found'],
    ['Restricted Assets', String(restrictedAssets.length), `${restrictedModelCount} model candidate(s), copied workflows/scripts/configs`],
    ['Assistant', 'Qwen coding', creatorPlanningModel],
    ['Backends', `${mediaStatus?.comfyui.status ?? 'offline'} / ${mediaStatus?.wan22.status ?? 'offline'}`, 'Photo via ComfyUI, video via Wan/ComfyUI'],
  ];

  async function submitCreatorGeneration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt || isMediaBusy || !activeMode) {
      return;
    }
    setLastGeneratedPrompt(trimmedPrompt);
    await onCreateGeneration(activeMode.id, trimmedPrompt, referenceFile, {
      creator_dataset_id: activeDataset?.id ?? null,
      creator_dataset_name: activeDataset?.name ?? null,
      creator_trigger_token: activeDataset?.trigger_token ?? 'creator_ai',
      safety_profile: 'sfw_virtual_creator',
      source: 'creator-studio',
      planning_model: creatorPlanningModel,
      pixelai_source_path: creatorStatus?.normalized_root ?? creatorStatus?.source_path ?? null,
    });
    setPrompt('');
    setReferenceFile(null);
  }

  async function submitCreatorAssist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = assistInput.trim();
    if (!message || assistBusy) {
      return;
    }
    const history = assistThread.map((entry) => ({ role: entry.role, content: entry.content }));
    setAssistThread((current) => [...current, { role: 'user', content: message }]);
    setAssistInput('');
    setAssistBusy(true);
    setAssistError(null);
    try {
      const result = await edisonApi.creatorStudioAssist({ message, history, preferred_model: creatorPlanningModel });
      setAssistThread((current) => [...current, { role: 'assistant', content: result.reply, actions: result.actions }]);
    } catch (error) {
      setAssistError(error instanceof Error ? error.message : 'Creator assistant request failed.');
    } finally {
      setAssistBusy(false);
    }
  }

  async function runAssistAction(action: CreatorStudioAssistAction) {
    setLastGeneratedPrompt(action.prompt);
    await onCreateGeneration(action.mode as MediaGenerationMode, action.prompt, null, {
      creator_dataset_id: activeDataset?.id ?? null,
      creator_dataset_name: activeDataset?.name ?? null,
      creator_trigger_token: activeDataset?.trigger_token ?? 'creator_ai',
      safety_profile: 'sfw_virtual_creator',
      source: 'creator-studio-assistant',
      planning_model: creatorPlanningModel,
      pixelai_source_path: creatorStatus?.normalized_root ?? creatorStatus?.source_path ?? null,
    });
  }

  return (
    <section className="workbench-view creator-studio-view" aria-label="AI Creator Studio">
      <div className="view-heading">
        <Sparkles size={26} />
        <h3>AI Creator Studio</h3>
        <button className="secondary-button icon-text-button" onClick={() => void onRefresh()} type="button">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <section className="creator-hero-panel" aria-label="Creator Studio overview">
        <div>
          <span className="section-label">Virtual creator workflow</span>
          <strong>Photoreal photos, short videos, and dataset plans for fictional AI personas</strong>
          <p>
            Uses Edison media jobs with PixelAI-style dataset/profile structure, ComfyUI photo generation, Wan video handoff,
            and Gallery/chat artifact delivery.
          </p>
        </div>
        <div className="creator-guardrail-grid">
          {(creatorStatus?.guardrails ?? [
            'AI-generated or rights-cleared fictional adult personas only',
            'No nude, pornographic, or sexually explicit output',
            'No real-person likeness, celebrity impersonation, or non-consensual datasets',
            'No minors or youth-coded creator content',
          ]).map((guardrail) => (
            <span key={guardrail}>
              <ShieldCheck size={15} />
              {guardrail}
            </span>
          ))}
        </div>
      </section>

      <div className="creator-status-grid">
        {statusCards.map(([label, value, detail]) => (
          <article className="creator-status-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{detail}</small>
          </article>
        ))}
      </div>

      <CreatorLabPanel creatorArtifacts={creatorArtifacts} lastPrompt={lastGeneratedPrompt} />

      <div className="creator-shell">
        <section className="creator-control-panel" aria-label="Creator generation controls">
          <div className="section-heading">
            <Camera size={18} />
            <h3>Generate</h3>
          </div>
          <div className="creator-mode-tabs" role="tablist" aria-label="Creator generation modes">
            {safeCreatorModes.map((mode) => (
              <button
                className={selectedMode === mode.id ? 'mode-button active' : 'mode-button'}
                key={mode.id}
                onClick={() => setSelectedMode(mode.id)}
                type="button"
              >
                {mode.label}
              </button>
            ))}
          </div>
          <form className="creator-form" onSubmit={(event) => void submitCreatorGeneration(event)}>
            <label>
              <span className="section-label">Dataset / persona</span>
              <select onChange={(event) => setSelectedDatasetId(event.target.value)} value={selectedDatasetId}>
                <option value="">Auto select safe dataset</option>
                {datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name} ({dataset.item_count} items)
                  </option>
                ))}
              </select>
            </label>
            <div className="creator-active-mode-card">
              <span className="section-label">Selected output</span>
              <strong>{activeMode?.label ?? 'Creator Photo'}</strong>
              <p>{activeMode?.description}</p>
            </div>
            <textarea
              aria-label="Creator prompt"
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={activeMode?.prompt_hint ?? 'Describe a safe virtual creator photo or video'}
              rows={6}
              value={prompt}
            />
            <div className="reference-upload-row">
              <label htmlFor="creator-reference-upload">Reference image</label>
              <input
                accept="image/*"
                disabled={!activeMode?.reference_supported}
                id="creator-reference-upload"
                onChange={(event) => setReferenceFile(event.target.files?.[0] ?? null)}
                type="file"
              />
              <span>{referenceFile ? referenceFile.name : activeMode?.reference_supported ? 'Optional persona/style reference' : 'Not used for this mode'}</span>
            </div>
            <button className="apply-button icon-text-button" disabled={!prompt.trim() || isMediaBusy} type="submit">
              <Send size={16} />
              {isMediaBusy ? 'Generating' : 'Generate'}
            </button>
          </form>
        </section>

        <section className="creator-dataset-panel" aria-label="Restricted labeled Creator assets">
          <div className="section-heading">
            <SlidersHorizontal size={18} />
            <h3>Restricted-Labeled Assets</h3>
          </div>
          <p>Non-media workflows, configs, and scripts are copied into Edison; model weights are cataloged as candidates for review.</p>
          <div className="creator-asset-list">
            {restrictedAssets.slice(0, 12).map((asset) => (
              <article className="creator-asset-row" key={asset.id}>
                <div>
                  <strong>{asset.name}</strong>
                  <span>{asset.kind} / {formatBytes(asset.size_bytes ?? null)}</span>
                  <small>{asset.copied_path ?? asset.source_path ?? 'No path recorded'}</small>
                </div>
                <small className={`backend-status ${statusClassName(asset.status)}`}>{asset.status}</small>
              </article>
            ))}
            {restrictedAssets.length === 0 && <div className="empty-line">No restricted-labeled workflow or model candidates detected yet.</div>}
          </div>
        </section>

        <section className="creator-dataset-panel" aria-label="Creator datasets">
          <div className="section-heading">
            <Database size={18} />
            <h3>Safe Datasets</h3>
          </div>
          <p>{creatorStatus?.detail ?? 'Creator Studio status has not loaded yet.'}</p>
          <div className="creator-dataset-list">
            {datasets.slice(0, 8).map((dataset) => (
              <article className="creator-dataset-row" key={dataset.id}>
                <div>
                  <strong>{dataset.name}</strong>
                  <span>{dataset.kind} / {dataset.item_count} items / {dataset.trigger_token ?? 'creator_ai'}</span>
                </div>
                <small className={`backend-status ${statusClassName(dataset.status)}`}>{dataset.status}</small>
              </article>
            ))}
            {datasets.length === 0 && <div className="empty-line">No safe creator datasets detected yet.</div>}
          </div>
        </section>
      </div>

      <section className="creator-assistant-panel" aria-label="Creator Studio assistant">
        <div className="section-heading">
          <Sparkles size={18} />
          <h3>Studio Assistant</h3>
          <span className="assistant-model-chip">{creatorPlanningModel}</span>
        </div>
        <p className="assistant-intro">
          Ask the Qwen assistant to plan personas, draft safe prompts, or set up photo / video / dataset jobs.
          It proposes actions you can run with one click, and stays within the studio guardrails.
        </p>
        <div className="creator-assistant-thread">
          {assistThread.length === 0 && (
            <div className="empty-line">
              Try: Plan a safe dataset for a fictional travel-vlogger persona and draft three photo prompts.
            </div>
          )}
          {assistThread.map((entry, index) => (
            <article className={`assistant-turn ${entry.role}`} key={index}>
              <div className="assistant-turn-role">{entry.role === 'user' ? 'You' : 'Qwen'}</div>
              <div className="assistant-turn-body">
                {entry.role === 'assistant' ? (
                  <MessageContent content={entry.content} metadata={{}} />
                ) : (
                  <p>{entry.content}</p>
                )}
                {entry.actions && entry.actions.length > 0 && (
                  <div className="assistant-action-list">
                    {entry.actions.map((action, actionIndex) => (
                      <article className="assistant-action-card" key={actionIndex}>
                        <div className="assistant-action-info">
                          <strong>{action.title}</strong>
                          <span className="assistant-action-mode">{action.mode.replace('creator_', '')}</span>
                          {action.rationale && <small>{action.rationale}</small>}
                          {action.prompt && <p className="assistant-action-prompt">{action.prompt}</p>}
                        </div>
                        <button
                          className="apply-button icon-text-button"
                          disabled={isMediaBusy}
                          onClick={() => void runAssistAction(action)}
                          type="button"
                        >
                          <Send size={14} />
                          Run
                        </button>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>
        {assistError && <div className="memory-inline-result error">{assistError}</div>}
        <form className="creator-assistant-form" onSubmit={(event) => void submitCreatorAssist(event)}>
          <textarea
            aria-label="Message the Creator Studio assistant"
            onChange={(event) => setAssistInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Ask the studio assistant to plan or generate something safe..."
            rows={3}
            value={assistInput}
          />
          <button className="apply-button icon-text-button" disabled={!assistInput.trim() || assistBusy} type="submit">
            <Send size={16} />
            {assistBusy ? 'Thinking' : 'Send'}
          </button>
        </form>
      </section>

      <MediaOutputsPanel
        artifacts={creatorArtifacts.length ? creatorArtifacts : artifacts.slice(0, 8)}
        jobs={creatorJobs.length ? creatorJobs : jobs.slice(0, 8)}
        onUseArtifactInChat={onUseArtifactInChat}
      />
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

interface AgentEntry {
  kind: 'thought' | 'action' | 'observation' | 'edit' | 'command_request' | 'command_result' | 'status' | 'error' | 'done';
  step: number;
  text?: string;
  action?: string;
  args?: Record<string, unknown>;
  path?: string;
  summary?: string;
  additions?: number;
  deletions?: number;
  diff?: string;
  stepId?: string;
  command?: string;
  cwd?: string;
  reason?: string;
  status?: string;
  exitCode?: number | null;
  stdout?: string;
  stderr?: string;
  resolved?: 'approved' | 'denied';
}

function RealtimeChip() {
  const [rt, setRt] = useState<RealtimeContext | null>(null);
  useEffect(() => {
    let active = true;
    const load = () => {
      void edisonApi
        .getRealtimeContext()
        .then((data) => {
          if (active) setRt(data);
        })
        .catch(() => {});
    };
    load();
    const timer = window.setInterval(load, 10 * 60 * 1000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  if (!rt) {
    return null;
  }
  const temp = rt.weather?.temperature_f != null ? `${Math.round(rt.weather.temperature_f)}°F` : '';
  const place = rt.location?.city || rt.location?.region || '';
  const timeShort = (rt.time?.display || '').split(', ').slice(-1)[0] || rt.time?.display || '';
  return (
    <span className="status-pill realtime-pill" title={rt.summary}>
      <CalendarDays size={15} /> {timeShort}
      {temp ? ` · ${temp}` : ''}
      {place ? ` · ${place}` : ''}
    </span>
  );
}

function RememberChatButton({ conversationId }: { conversationId: string }) {
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  async function remember() {
    setState('saving');
    try {
      await edisonApi.rememberConversation(conversationId);
      setState('saved');
    } catch {
      setState('error');
    }
    window.setTimeout(() => setState('idle'), 4000);
  }
  const label =
    state === 'saving' ? 'Saving...' : state === 'saved' ? 'Remembered' : state === 'error' ? 'Failed' : 'Remember';
  return (
    <button
      className="secondary-button icon-text-button"
      disabled={state === 'saving'}
      onClick={() => void remember()}
      title="Save this conversation to Edison's long-term memory"
      type="button"
    >
      <Brain size={15} /> {label}
    </button>
  );
}

function CodeAgentPanel({ rootId, onAfterRun }: { rootId: string; onAfterRun?: () => Promise<void> }) {
  const [task, setTask] = useState('');
  const [running, setRunning] = useState(false);
  const [autoRun, setAutoRun] = useState(false);
  const [entries, setEntries] = useState<AgentEntry[]>([]);
  const [pending, setPending] = useState<{ stepId: string; command: string; cwd: string; reason: string } | null>(null);
  const [changedFiles, setChangedFiles] = useState<AgentChangedFile[]>([]);
  const [doneInfo, setDoneInfo] = useState<{ status: string; summary: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restarting, setRestarting] = useState(false);
  const runIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const [restored, setRestored] = useState(false);
  const selfEdit = rootId === 'app';
  const storageKey = `edison.codeagent.${rootId}`;

  // Restore the last session for this Code Space so returning isn't a blank page.
  useEffect(() => {
    setRestored(false);
    try {
      const raw = window.localStorage.getItem(`edison.codeagent.${rootId}`);
      if (raw) {
        const saved = JSON.parse(raw);
        setEntries(Array.isArray(saved.entries) ? saved.entries : []);
        setChangedFiles(Array.isArray(saved.changedFiles) ? saved.changedFiles : []);
        setDoneInfo(saved.doneInfo ?? null);
        if (typeof saved.task === 'string') setTask(saved.task);
        runIdRef.current = saved.runId ?? null;
        if ((saved.entries?.length ?? 0) > 0 && !saved.doneInfo) {
          setRestored(true);
        }
      } else {
        setEntries([]);
        setChangedFiles([]);
        setDoneInfo(null);
      }
    } catch {
      /* ignore corrupt cache */
    }
  }, [rootId]);

  // Persist the running transcript so it can be picked up after navigating away.
  useEffect(() => {
    try {
      window.localStorage.setItem(
        storageKey,
        JSON.stringify({ task, entries: entries.slice(-250), changedFiles, doneInfo, runId: runIdRef.current }),
      );
    } catch {
      /* storage full or unavailable */
    }
  }, [storageKey, task, entries, changedFiles, doneInfo]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' });
  }, [entries.length, pending]);

  function append(entry: AgentEntry) {
    setEntries((prev) => [...prev, entry]);
  }

  function handleEvent(event: string, data: any) {
    switch (event) {
      case 'start':
        runIdRef.current = (data?.run_id as string) ?? null;
        append({
          kind: 'status',
          step: 0,
          text: `Working in ${data?.root_id ?? rootId}${data?.checkpoint?.head ? ` · checkpoint ${String(data.checkpoint.head).slice(0, 7)}` : ''}`,
        });
        break;
      case 'thought':
        append({ kind: 'thought', step: Number(data?.step ?? 0), text: String(data?.text ?? '') });
        break;
      case 'action':
        append({ kind: 'action', step: Number(data?.step ?? 0), action: String(data?.action ?? ''), args: (data?.args ?? {}) as Record<string, unknown> });
        break;
      case 'observation':
        append({ kind: 'observation', step: Number(data?.step ?? 0), text: String(data?.text ?? ''), path: data?.path });
        break;
      case 'file_edit':
        append({
          kind: 'edit',
          step: Number(data?.step ?? 0),
          path: String(data?.path ?? ''),
          summary: String(data?.summary ?? ''),
          additions: Number(data?.additions ?? 0),
          deletions: Number(data?.deletions ?? 0),
          diff: String(data?.diff ?? ''),
        });
        setChangedFiles((prev) => {
          const next = prev.filter((item) => item.path !== data?.path);
          next.push({ path: String(data?.path ?? ''), additions: Number(data?.additions ?? 0), deletions: Number(data?.deletions ?? 0) });
          return next;
        });
        break;
      case 'command_request': {
        const info = {
          stepId: String(data?.step_id ?? ''),
          command: String(data?.command ?? ''),
          cwd: String(data?.cwd ?? '.'),
          reason: String(data?.reason ?? ''),
        };
        setPending(info);
        append({ kind: 'command_request', step: Number(data?.step ?? 0), ...info });
        break;
      }
      case 'command_result':
        setPending(null);
        append({
          kind: 'command_result',
          step: Number(data?.step ?? 0),
          command: String(data?.command ?? ''),
          status: String(data?.status ?? ''),
          exitCode: data?.exit_code ?? null,
          stdout: String(data?.stdout ?? ''),
          stderr: String(data?.stderr ?? ''),
        });
        break;
      case 'command_skipped':
        setPending(null);
        append({ kind: 'status', step: Number(data?.step ?? 0), text: `Skipped command: ${data?.command ?? ''} (${data?.reason ?? ''})` });
        break;
      case 'status':
        append({ kind: 'status', step: Number(data?.step ?? 0), text: String(data?.message ?? '') });
        break;
      case 'error':
        setError(String(data?.detail ?? 'Agent error'));
        append({ kind: 'error', step: 0, text: String(data?.detail ?? 'Agent error') });
        break;
      case 'done':
        setDoneInfo({ status: String(data?.status ?? 'complete'), summary: String(data?.summary ?? '') });
        if (Array.isArray(data?.changed_files)) {
          setChangedFiles(
            data.changed_files.map((item: any) => ({
              path: String(item?.path ?? ''),
              additions: Number(item?.additions ?? 0),
              deletions: Number(item?.deletions ?? 0),
            })),
          );
        }
        append({ kind: 'done', step: Number(data?.steps ?? 0), status: String(data?.status ?? 'complete'), summary: String(data?.summary ?? '') });
        break;
      default:
        break;
    }
  }

  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = task.trim();
    if (!trimmed || running) {
      return;
    }
    setRunning(true);
    setRestored(false);
    setEntries([]);
    setChangedFiles([]);
    setDoneInfo(null);
    setError(null);
    setPending(null);
    runIdRef.current = null;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await edisonApi.streamWorkspaceAgent(
        { task: trimmed, root_id: rootId, auto_run_commands: autoRun, max_steps: 40 },
        handleEvent,
        controller.signal,
      );
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === 'AbortError')) {
        const message = caught instanceof Error ? caught.message : 'Agent stream failed.';
        setError(message);
        append({ kind: 'error', step: 0, text: message });
      }
    } finally {
      setRunning(false);
      setPending(null);
      abortRef.current = null;
      if (onAfterRun) {
        try {
          await onAfterRun();
        } catch {
          /* ignore refresh failure */
        }
      }
    }
  }

  async function decide(approved: boolean) {
    const runId = runIdRef.current;
    const current = pending;
    if (!runId || !current) {
      return;
    }
    setPending(null);
    setEntries((prev) =>
      prev.map((entry) =>
        entry.kind === 'command_request' && entry.stepId === current.stepId
          ? { ...entry, resolved: approved ? 'approved' : 'denied' }
          : entry,
      ),
    );
    try {
      await edisonApi.controlWorkspaceAgent({ run_id: runId, action: approved ? 'approve' : 'deny', step_id: current.stepId });
    } catch {
      /* ignore */
    }
  }

  async function stop() {
    const runId = runIdRef.current;
    if (runId) {
      try {
        await edisonApi.controlWorkspaceAgent({ run_id: runId, action: 'stop' });
      } catch {
        /* ignore */
      }
    }
    abortRef.current?.abort();
  }

  async function applyAndRestart() {
    setRestarting(true);
    append({ kind: 'status', step: 0, text: 'Building the web app and verifying the backend, then restarting...' });
    try {
      const result = await edisonApi.restartEdison();
      append({ kind: 'status', step: 0, text: result.detail || 'Edison is restarting; the page will reconnect shortly.' });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Restart request failed.');
    } finally {
      window.setTimeout(() => setRestarting(false), 12000);
    }
  }

  const doneLabel =
    doneInfo?.status === 'complete'
      ? 'Done'
      : doneInfo?.status === 'cancelled'
        ? 'Stopped'
        : doneInfo?.status === 'incomplete'
          ? 'Paused (step budget reached)'
          : 'Finished with errors';

  return (
    <section className="code-agent-panel" aria-label="Edison Code Agent">
      <div className="section-heading">
        <Sparkles size={18} />
        <h3>Code Agent</h3>
        <span className="agent-target-chip">{selfEdit ? 'editing Edison itself' : `root: ${rootId}`}</span>
        {running && <span className="agent-live-dot" aria-label="running" />}
      </div>
      <p className="assistant-intro">
        Give the agent a goal. It reads, edits, and verifies step by step, streaming its thinking and changes, and keeps
        going until the task is done. It asks before running any command.
      </p>

      <div className="code-agent-transcript" ref={transcriptRef}>
        {restored && (
          <div className="agent-restored-banner">↩ Restored your last session for this Code Space — start a new task to continue.</div>
        )}
        {entries.length === 0 && !running && (
          <div className="empty-line">
            {selfEdit
              ? 'e.g. Add a /api/v1/health/ping route that returns {"pong": true}, then run the tests.'
              : 'Describe what to build or change in this project.'}
          </div>
        )}
        {entries.map((entry, index) => (
          <AgentEntryView key={index} entry={entry} pendingStepId={pending?.stepId ?? null} onDecide={decide} />
        ))}
      </div>

      {doneInfo && (
        <div className={`agent-done-card ${doneInfo.status}`}>
          <div className="agent-done-head">
            <strong>{doneLabel}</strong>
            <span>{doneInfo.summary}</span>
          </div>
          {changedFiles.length > 0 && (
            <div className="agent-changed-files">
              {changedFiles.map((file) => (
                <span key={file.path} className="agent-changed-file">
                  <FileCode2 size={13} /> {file.path} <small>+{file.additions} -{file.deletions}</small>
                </span>
              ))}
            </div>
          )}
          {changedFiles.length > 0 && (
            <button className="apply-button icon-text-button" disabled={restarting} onClick={() => void applyAndRestart()} type="button">
              <RefreshCw size={15} />
              {restarting ? 'Building & restarting...' : 'Apply & restart Edison'}
            </button>
          )}
        </div>
      )}

      {error && <div className="memory-inline-result error">{error}</div>}

      <form className="code-agent-form" onSubmit={(event) => void start(event)}>
        <textarea
          aria-label="Code agent task"
          disabled={running}
          onChange={(event) => setTask(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={selfEdit ? 'Tell Edison what to change about itself...' : 'Describe the change...'}
          rows={3}
          value={task}
        />
        <div className="code-agent-actions">
          <label className="inline-toggle" title="Run tests/build without asking each time">
            <input checked={autoRun} disabled={running} onChange={(event) => setAutoRun(event.target.checked)} type="checkbox" />
            Auto-run commands
          </label>
          {running ? (
            <button className="danger-button icon-text-button" onClick={() => void stop()} type="button">
              <X size={15} />
              Stop
            </button>
          ) : (
            <button className="apply-button icon-text-button" disabled={!task.trim()} type="submit">
              <Send size={15} />
              Start agent
            </button>
          )}
        </div>
      </form>
    </section>
  );
}

function AgentEntryView({
  entry,
  pendingStepId,
  onDecide,
}: {
  entry: AgentEntry;
  pendingStepId: string | null;
  onDecide: (approved: boolean) => Promise<void>;
}) {
  if (entry.kind === 'thought') {
    return (
      <div className="agent-line thought">
        <Brain size={14} />
        <span>{entry.text}</span>
      </div>
    );
  }
  if (entry.kind === 'action') {
    const detail = String(entry.args?.path ?? entry.args?.query ?? entry.args?.command ?? '');
    return (
      <div className="agent-line action">
        <span className="agent-tool-chip">{entry.action}</span>
        {detail ? <code>{detail}</code> : null}
      </div>
    );
  }
  if (entry.kind === 'observation') {
    return <div className="agent-line observation">{entry.text}</div>;
  }
  if (entry.kind === 'edit') {
    return (
      <details className="agent-edit-card">
        <summary>
          <FileCode2 size={14} />
          <strong>{entry.path}</strong>
          <small className="agent-diff-stat">+{entry.additions} -{entry.deletions}</small>
          {entry.summary ? <span className="agent-edit-summary">{entry.summary}</span> : null}
        </summary>
        <pre className="agent-diff">{entry.diff}</pre>
      </details>
    );
  }
  if (entry.kind === 'command_request') {
    const awaiting = pendingStepId === entry.stepId && !entry.resolved;
    return (
      <div className={`agent-command-card ${entry.resolved ?? (awaiting ? 'awaiting' : '')}`}>
        <div className="agent-command-head">
          <Cpu size={14} />
          <code>{entry.command}</code>
          {entry.cwd && entry.cwd !== '.' ? <small>in {entry.cwd}</small> : null}
        </div>
        {entry.reason ? <p className="agent-command-reason">{entry.reason}</p> : null}
        {awaiting ? (
          <div className="agent-command-actions">
            <button className="apply-button icon-text-button" onClick={() => void onDecide(true)} type="button">
              <CheckSquare2 size={14} /> Approve &amp; run
            </button>
            <button className="secondary-button icon-text-button" onClick={() => void onDecide(false)} type="button">
              <X size={14} /> Skip
            </button>
          </div>
        ) : entry.resolved ? (
          <small className={`agent-command-badge ${entry.resolved}`}>
            {entry.resolved === 'approved' ? 'approved' : 'skipped'}
          </small>
        ) : null}
      </div>
    );
  }
  if (entry.kind === 'command_result') {
    const ok = entry.status === 'complete';
    return (
      <details className="agent-command-result" open={!ok}>
        <summary>
          <Cpu size={14} />
          <code>{entry.command}</code>
          <small className={`job-status ${ok ? 'complete' : 'error'}`}>
            {entry.status}
            {entry.exitCode != null ? ` (${entry.exitCode})` : ''}
          </small>
        </summary>
        {entry.stdout ? <pre className="agent-output">{entry.stdout}</pre> : null}
        {entry.stderr ? <pre className="agent-output stderr">{entry.stderr}</pre> : null}
      </details>
    );
  }
  if (entry.kind === 'error') {
    return <div className="agent-line error">{entry.text}</div>;
  }
  if (entry.kind === 'done') {
    return null;
  }
  return <div className="agent-line status">{entry.text}</div>;
}

function monacoLanguage(language: string | null | undefined, path: string): string {
  const byLang: Record<string, string> = {
    typescript: 'typescript', javascript: 'javascript', python: 'python', json: 'json',
    markdown: 'markdown', html: 'html', css: 'css', rust: 'rust', go: 'go', java: 'java',
    yaml: 'yaml', toml: 'ini', shell: 'shell', bash: 'shell', sql: 'sql', c: 'cpp', cpp: 'cpp',
  };
  if (language && byLang[language.toLowerCase()]) {
    return byLang[language.toLowerCase()];
  }
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  const byExt: Record<string, string> = {
    ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript', py: 'python',
    json: 'json', md: 'markdown', html: 'html', css: 'css', rs: 'rust', go: 'go', java: 'java',
    yml: 'yaml', yaml: 'yaml', toml: 'ini', sh: 'shell', sql: 'sql', c: 'cpp', h: 'cpp', cpp: 'cpp',
  };
  return byExt[ext] ?? 'plaintext';
}

function CodeWorkspaceView({
  activeRootId,
  commandResult,
  copilotResult,
  entries,
  draftContent,
  file,
  isBusy,
  onApplyPatch,
  onCreateProject,
  onOpenEntry,
  onParent,
  onPreviewPatch,
  onRunCopilotTask,
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
  copilotResult: WorkspaceCopilotTaskResult | null;
  entries: WorkspaceEntry[];
  draftContent: string;
  file: WorkspaceFile | null;
  isBusy: boolean;
  onApplyPatch: () => Promise<void>;
  onCreateProject: (name: string, prompt: string) => Promise<void>;
  onOpenEntry: (entry: WorkspaceEntry) => Promise<void>;
  onParent: () => Promise<void>;
  onPreviewPatch: () => Promise<void>;
  onRunCopilotTask: (instruction: string, runCommands: boolean) => Promise<void>;
  onRefresh: () => Promise<void>;
  onRunCommand: (command: WorkspaceCommand | string) => Promise<void>;
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
  const [copilotInstruction, setCopilotInstruction] = useState('');
  const [copilotRunCommands, setCopilotRunCommands] = useState(false);
  const [customCommand, setCustomCommand] = useState('');
  const [openTabs, setOpenTabs] = useState<WorkspaceEntry[]>([]);
  const [sidebarView, setSidebarView] = useState<'explorer' | 'search' | 'scm'>('explorer');
  const [bottomTab, setBottomTab] = useState<'terminal' | 'problems' | 'output'>('terminal');
  const [bottomOpen, setBottomOpen] = useState(true);
  const [installPkg, setInstallPkg] = useState('');
  const [installing, setInstalling] = useState(false);
  const [installOut, setInstallOut] = useState<WorkspaceInstallResult | null>(null);
  const topLanguages = Object.entries(summary?.languages ?? {}).slice(0, 3);
  const commandPreview = scan?.commands.slice(0, 6) ?? [];
  const entrypointPreview = scan?.entrypoints.slice(0, 5) ?? [];
  const configPreview = scan?.config_files.slice(0, 6) ?? [];
  const draftChanged = Boolean(file && draftContent !== file.content);
  const activeRoot = roots.find((root) => root.id === activeRootId);

  // Track opened files as editor tabs (VS Code style). Clicking a tab re-opens it.
  useEffect(() => {
    if (!file) {
      return;
    }
    setOpenTabs((tabs) =>
      tabs.some((tab) => tab.path === file.path)
        ? tabs
        : [...tabs, { path: file.path, name: file.name, kind: 'file', language: file.language ?? null, size_bytes: file.size_bytes }],
    );
  }, [file?.path]);

  function closeTab(targetPath: string) {
    setOpenTabs((tabs) => tabs.filter((tab) => tab.path !== targetPath));
  }

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreateProject(projectName, projectPrompt);
    setProjectName('');
    setProjectPrompt('');
  }

  async function handleCopilotTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!copilotInstruction.trim()) {
      return;
    }
    await onRunCopilotTask(copilotInstruction, copilotRunCommands);
    setCopilotInstruction('');
  }

  async function handleCustomCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!customCommand.trim()) {
      return;
    }
    await onRunCommand(customCommand);
    setCustomCommand('');
  }

  async function runInstall(pkg?: string) {
    setInstalling(true);
    setBottomTab('terminal');
    setBottomOpen(true);
    try {
      const result = await edisonApi.installWorkspaceDeps({ root_id: activeRootId, package: pkg ?? null, cwd: path || '.' });
      setInstallOut(result);
      if (pkg) setInstallPkg('');
      await onRefresh();
    } catch (error) {
      setInstallOut({
        manager: 'install',
        command: pkg ? `install ${pkg}` : 'install dependencies',
        cwd: path || '.',
        status: 'error',
        exit_code: null,
        duration_ms: 0,
        stdout: '',
        stderr: error instanceof Error ? error.message : 'Install failed',
        output_truncated: false,
      });
    } finally {
      setInstalling(false);
    }
  }

  return (
    <section className="workbench-view code-view" aria-label="Code Space">
      <div className="vsc-ide">
        <div className="vsc-topbar">
          <div className="vsc-topbar-left">
            <Code2 size={15} />
            <span className="vsc-breadcrumb">{activeRoot?.name ?? 'Edison App'}{path ? ` › ${path}` : ''}</span>
          </div>
          <div className="vsc-topbar-center">
            <select
              aria-label="Code Space"
              className="vsc-root-select"
              disabled={isBusy}
              onChange={(event) => void onSelectRoot(event.target.value)}
              value={activeRootId}
            >
              {(roots.length ? roots : [{ id: 'app', name: 'Edison App', path: summary?.root_path ?? '', kind: 'app' as const }]).map((root) => (
                <option key={root.id} value={root.id}>{root.name}</option>
              ))}
            </select>
          </div>
          <div className="vsc-topbar-right">
            <a className="vsc-icon-btn" href={edisonApi.downloadWorkspaceUrl(activeRootId)} title="Download this Code Space as a .zip"><Download size={15} /></a>
            <button className="vsc-icon-btn" disabled={isBusy} onClick={() => void onRefresh()} title="Refresh" type="button"><RefreshCw size={15} /></button>
          </div>
        </div>

        <div className="vsc-body">
          <nav className="vsc-activity" aria-label="Activity bar">
            <button className={sidebarView === 'explorer' ? 'vsc-act active' : 'vsc-act'} onClick={() => setSidebarView('explorer')} title="Explorer" type="button"><Folder size={22} /></button>
            <button className={sidebarView === 'search' ? 'vsc-act active' : 'vsc-act'} onClick={() => setSidebarView('search')} title="Search" type="button"><Search size={22} /></button>
            <button className={sidebarView === 'scm' ? 'vsc-act active' : 'vsc-act'} onClick={() => setSidebarView('scm')} title="Source Control" type="button"><Network size={22} /></button>
            <div className="vsc-act-spacer" />
            <span className="vsc-act" title="Edison"><Bot size={22} /></span>
          </nav>

          <aside className="vsc-sidebar" aria-label="Sidebar">
            {sidebarView === 'explorer' && (
              <div className="vsc-pane">
                <div className="vsc-pane-head">
                  <span>{(activeRoot?.name ?? summary?.root_name ?? 'workspace').toUpperCase()}</span>
                  <div className="vsc-pane-actions">
                    <button className="vsc-icon-btn" disabled={!path || isBusy} onClick={() => void onParent()} title="Up one folder" type="button"><ChevronUp size={15} /></button>
                    <button className="vsc-icon-btn" disabled={isBusy} onClick={() => void onRefresh()} title="Refresh" type="button"><RefreshCw size={13} /></button>
                  </div>
                </div>
                <div className="vsc-file-tree">
                  {entries.map((entry) => {
                    const Icon = entry.kind === 'directory' ? Folder : FileCode2;
                    return (
                      <button className={file?.path === entry.path ? 'vsc-file active' : 'vsc-file'} key={entry.path} onClick={() => void onOpenEntry(entry)} title={entry.path} type="button">
                        <Icon size={15} />
                        <span>{entry.name}</span>
                      </button>
                    );
                  })}
                  {entries.length === 0 && <div className="empty-line">No files</div>}
                </div>
                <details className="vsc-newproj">
                  <summary>+ New repo</summary>
                  <form onSubmit={(event) => void handleCreateProject(event)}>
                    <input onChange={(event) => setProjectName(event.target.value)} placeholder="repo name" value={projectName} />
                    <input onChange={(event) => setProjectPrompt(event.target.value)} placeholder="what should Edison build?" value={projectPrompt} />
                    <button className="secondary-button" disabled={isBusy || !projectName.trim() || !projectPrompt.trim()} type="submit">Create</button>
                  </form>
                </details>
              </div>
            )}
            {sidebarView === 'search' && (
              <div className="vsc-pane">
                <div className="vsc-pane-head"><span>SEARCH</span></div>
                <form className="vsc-search-form" onSubmit={(event) => void onSearch(event)}>
                  <input onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search files and code" value={searchQuery} />
                </form>
                <div className="vsc-search-results">
                  {searchResults.slice(0, 40).map((result) => (
                    <button
                      className="vsc-search-row"
                      key={`${result.path}-${result.line_number ?? 'file'}`}
                      onClick={() => { onAddChatContextPath(result.path); void onOpenEntry({ path: result.path, name: result.name, kind: 'file', language: result.language }); }}
                      type="button"
                    >
                      <strong>{result.name}{result.line_number ? `:${result.line_number}` : ''}</strong>
                      <span>{result.line_text ?? result.path}</span>
                    </button>
                  ))}
                  {searchQuery && searchResults.length === 0 && <div className="empty-line">No matches</div>}
                </div>
              </div>
            )}
            {sidebarView === 'scm' && (
              <div className="vsc-pane">
                <div className="vsc-pane-head"><span>SOURCE CONTROL</span></div>
                {patchPreview ? (
                  <div className="vsc-scm">
                    <div className="vsc-scm-file">
                      <strong>{patchPreview.path}</strong>
                      <span className="diff-stats"><span>+{patchPreview.additions}</span><span>-{patchPreview.deletions}</span></span>
                    </div>
                    {patchPreview.risk_flags.length > 0 && (
                      <div className="risk-list">{patchPreview.risk_flags.map((flag) => <span key={flag}>{flag.replace(/_/g, ' ')}</span>)}</div>
                    )}
                    <pre className="diff-preview">
                      {(patchPreview.diff || 'No changes').split('\n').map((line, index) => (
                        <div className={line.startsWith('+') && !line.startsWith('+++') ? 'diff-add' : line.startsWith('-') && !line.startsWith('---') ? 'diff-del' : line.startsWith('@@') ? 'diff-hunk' : undefined} key={index}>{line || ' '}</div>
                      ))}
                    </pre>
                  </div>
                ) : (
                  <div className="empty-line">Open a file, edit it, then click “Preview diff” to see changes here.</div>
                )}
              </div>
            )}
          </aside>

          <div className="vsc-center">
            <div className="vsc-editor-area">
              <div className="editor-tab-bar" role="tablist">
                {openTabs.map((tab) => (
                  <div className={file?.path === tab.path ? 'editor-tab active' : 'editor-tab'} key={tab.path}>
                    <button className="editor-tab-label" onClick={() => void onOpenEntry(tab)} title={tab.path} type="button"><FileCode2 size={13} />{tab.name}</button>
                    <button aria-label={`Close ${tab.name}`} className="editor-tab-close" onClick={() => closeTab(tab.path)} type="button"><X size={12} /></button>
                  </div>
                ))}
                {openTabs.length === 0 && <div className="editor-tab placeholder">Welcome</div>}
              </div>
              {file ? (
                <div className="vsc-editor-wrap">
                  <div className="vsc-editor-actions">
                    <span className="vsc-editor-path">{file.path}{draftChanged ? ' ●' : ''} · {file.language ?? 'text'}{file.truncated ? ' · truncated' : ''}</span>
                    <div className="patch-action-row">
                      <button className="secondary-button" onClick={() => onAddChatContextPath(file.path)} type="button">Add to chat</button>
                      <button className="secondary-button" disabled={!draftChanged || isBusy} onClick={() => void onPreviewPatch()} type="button">Preview diff</button>
                      <button className="apply-button" disabled={!patchPreview || !draftChanged || isBusy} onClick={() => void onApplyPatch()} type="button">Apply patch</button>
                    </div>
                  </div>
                  <div className="vsc-monaco">
                    <Editor
                      height="100%"
                      language={monacoLanguage(file.language, file.path)}
                      onChange={(value) => setDraftContent(value ?? '')}
                      options={{ minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false, automaticLayout: true, tabSize: 2, wordWrap: 'on', smoothScrolling: true }}
                      theme="vs-dark"
                      value={draftContent}
                    />
                  </div>
                </div>
              ) : (
                <div className="vsc-welcome">
                  <Code2 size={42} />
                  <strong>Edison Code Space</strong>
                  <span>Open a file from the Explorer, or describe a task to the agent on the right.</span>
                  <div className="vsc-welcome-stats">
                    <span>{summary?.file_count ?? 0} files</span>
                    <span>{scan?.stacks.join(' / ') || summary?.package_managers.join(' / ') || 'no stack marker'}</span>
                    <span>{topLanguages.map(([name]) => name).join(' / ') || 'no language scan'}</span>
                  </div>
                </div>
              )}
            </div>

            <div className={bottomOpen ? 'vsc-panel open' : 'vsc-panel'}>
              <div className="vsc-panel-tabs">
                <button className={bottomTab === 'problems' ? 'active' : ''} onClick={() => { setBottomTab('problems'); setBottomOpen(true); }} type="button">PROBLEMS</button>
                <button className={bottomTab === 'output' ? 'active' : ''} onClick={() => { setBottomTab('output'); setBottomOpen(true); }} type="button">OUTPUT</button>
                <button className={bottomTab === 'terminal' ? 'active' : ''} onClick={() => { setBottomTab('terminal'); setBottomOpen(true); }} type="button">TERMINAL</button>
                <div className="vsc-panel-spacer" />
                <button className="vsc-icon-btn" onClick={() => setBottomOpen((open) => !open)} title={bottomOpen ? 'Collapse panel' : 'Expand panel'} type="button"><ChevronUp size={14} style={{ transform: bottomOpen ? 'none' : 'rotate(180deg)' }} /></button>
              </div>
              {bottomOpen && (
                <div className="vsc-panel-body">
                  {bottomTab === 'terminal' && (
                    <div className="vsc-terminal">
                      {commandResult && (
                        <div className="vsc-term-block">
                          <div className="vsc-term-cmd">$ {commandResult.command} <span className="vsc-term-meta">({commandResult.duration_ms}ms · exit {commandResult.exit_code ?? 'timeout'})</span></div>
                          {commandResult.stdout && <pre>{commandResult.stdout}</pre>}
                          {commandResult.stderr && <pre className="err">{commandResult.stderr}</pre>}
                        </div>
                      )}
                      <form className="vsc-term-input" onSubmit={(event) => void handleCustomCommand(event)}>
                        <span className="vsc-term-ps">{summary?.root_name ?? 'edison'}&nbsp;$</span>
                        <input aria-label="Run command" disabled={isBusy} onChange={(event) => setCustomCommand(event.target.value)} placeholder="git status · npm run build · python -m pytest" value={customCommand} />
                      </form>
                      {commandPreview.length > 0 && (
                        <div className="vsc-term-suggest">
                          {commandPreview.map((command) => (
                            <button disabled={isBusy} key={`${command.cwd}-${command.command}`} onClick={() => void onRunCommand(command)} type="button">{command.command}</button>
                          ))}
                        </div>
                      )}
                      <div className="vsc-term-deps">
                        <button disabled={installing} onClick={() => void runInstall()} type="button">
                          <Download size={13} /> {installing ? 'Installing…' : 'Install dependencies'}
                        </button>
                        <input
                          aria-label="Add a package"
                          onChange={(event) => setInstallPkg(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' && installPkg.trim()) {
                              event.preventDefault();
                              void runInstall(installPkg.trim());
                            }
                          }}
                          placeholder="add a package — axios, requests, …"
                          value={installPkg}
                        />
                        <button disabled={installing || !installPkg.trim()} onClick={() => void runInstall(installPkg.trim())} type="button">Add</button>
                      </div>
                      {installOut && (
                        <div className="vsc-term-block">
                          <div className="vsc-term-cmd">$ {installOut.command} <span className="vsc-term-meta">({installOut.manager} · {installOut.status})</span></div>
                          {installOut.stdout && <pre>{installOut.stdout}</pre>}
                          {installOut.stderr && <pre className="err">{installOut.stderr}</pre>}
                        </div>
                      )}
                    </div>
                  )}
                  {bottomTab === 'problems' && (
                    <div className="vsc-problems">
                      {(patchPreview?.risk_flags.length ?? 0) > 0
                        ? patchPreview!.risk_flags.map((flag) => <div className="vsc-problem" key={flag}>⚠ {flag.replace(/_/g, ' ')} — {patchPreview!.path}</div>)
                        : <div className="empty-line">No problems detected.</div>}
                    </div>
                  )}
                  {bottomTab === 'output' && (
                    <div className="vsc-output">
                      <pre>{commandResult ? (`${commandResult.stdout}\n${commandResult.stderr}`.trim() || 'No output.') : 'No output yet — run a command in the terminal.'}</pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          <aside className="vsc-chat" aria-label="Chat">
            <div className="vsc-chat-head"><MessageSquare size={14} /> CHAT <span className="vsc-chat-sub">Agent · {activeRoot?.name ?? 'app'}</span></div>
            <div className="vsc-chat-body">
              <CodeAgentPanel rootId={activeRootId} onAfterRun={onRefresh} />
            </div>
          </aside>
        </div>

        <div className="vsc-statusbar">
          <span className="vsc-status-item"><Network size={12} /> {summary?.root_name ?? 'main'}</span>
          <span className="vsc-status-item">{summary?.file_count ?? 0} files</span>
          <span className="vsc-status-item">{scan?.stacks.join(', ') || 'no stack'}</span>
          <div className="vsc-status-spacer" />
          <span className="vsc-status-item">⚠ {patchPreview?.risk_flags.length ?? 0}</span>
          <span className="vsc-status-item">Edison</span>
        </div>
      </div>

    </section>
  );
}

const TOYBOX_COLOR_HEX: Record<string, string> = {
  red: '#d41e1e', orange: '#e67814', yellow: '#ebd728', green: '#28aa46', blue: '#285ac8',
  cyan: '#28bec8', purple: '#823cb4', pink: '#eb6eb4', white: '#ededed', black: '#222222',
  gray: '#828282', brown: '#785028',
};

function ModelViewer({ onColorChosen }: { onColorChosen?: (hex: string) => void }) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const ctxRef = useRef<any>(null);
  const meshRef = useRef<any>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [color, setColor] = useState('#3a7bd5');
  const [fileName, setFileName] = useState<string | null>(null);
  const [viewerError, setViewerError] = useState<string | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return undefined;
    const height = 320;
    const width = mount.clientWidth || 480;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x14171f);
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 8000);
    camera.position.set(120, 110, 160);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x303040, 1.1));
    const dir = new THREE.DirectionalLight(0xffffff, 1.0);
    dir.position.set(1, 1.4, 1);
    scene.add(dir);
    scene.add(new THREE.GridHelper(240, 24, 0x2a2f3a, 0x20242c));
    let raf = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    };
    animate();
    ctxRef.current = { scene, camera, renderer, controls };
    const onResize = () => {
      const nextWidth = mount.clientWidth || 480;
      camera.aspect = nextWidth / height;
      camera.updateProjectionMatrix();
      renderer.setSize(nextWidth, height);
    };
    window.addEventListener('resize', onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', onResize);
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement);
      }
    };
  }, []);

  function applyColor(root: any, hex: string) {
    const material = new THREE.MeshStandardMaterial({ color: new THREE.Color(hex), metalness: 0.05, roughness: 0.65 });
    if (root.isMesh) root.material = material;
    root.traverse?.((child: any) => {
      if (child.isMesh) child.material = material;
    });
  }

  function fitCamera(object: any) {
    const ctx = ctxRef.current;
    if (!ctx) return;
    const box = new THREE.Box3().setFromObject(object);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    object.position.sub(center);
    const maxDim = Math.max(size.x, size.y, size.z) || 60;
    ctx.camera.position.set(maxDim * 1.3, maxDim * 1.1, maxDim * 1.7);
    ctx.camera.near = Math.max(0.1, maxDim / 200);
    ctx.camera.far = maxDim * 200;
    ctx.camera.updateProjectionMatrix();
    ctx.controls.target.set(0, 0, 0);
    ctx.controls.update();
  }

  async function loadFile(file: File) {
    const ctx = ctxRef.current;
    if (!ctx) return;
    setViewerError(null);
    setFileName(file.name);
    if (meshRef.current) {
      ctx.scene.remove(meshRef.current);
      meshRef.current = null;
    }
    const ext = file.name.split('.').pop()?.toLowerCase();
    try {
      const buffer = await file.arrayBuffer();
      let object: any = null;
      if (ext === 'stl') {
        const geometry = new STLLoader().parse(buffer);
        geometry.computeVertexNormals();
        object = new THREE.Mesh(geometry);
      } else if (ext === '3mf') {
        object = new ThreeMFLoader().parse(buffer);
      } else if (ext === 'obj') {
        object = new OBJLoader().parse(new TextDecoder().decode(buffer));
      } else {
        setViewerError('Use an STL, 3MF, or OBJ file.');
        return;
      }
      applyColor(object, color);
      ctx.scene.add(object);
      meshRef.current = object;
      fitCamera(object);
    } catch {
      setViewerError('Could not load that model file.');
    }
  }

  function chooseColor(hex: string) {
    setColor(hex);
    if (meshRef.current) applyColor(meshRef.current, hex);
    onColorChosen?.(hex);
  }

  const palette = ['#d41e1e', '#e67814', '#ebd728', '#28aa46', '#285ac8', '#28bec8', '#823cb4', '#eb6eb4', '#ededed', '#222222', '#828282', '#785028'];

  return (
    <div className="toybox-viewer">
      <div className="toybox-viewer-head">
        <span><Box size={15} /> 3D model · color assignment</span>
        <button className="secondary-button icon-text-button" onClick={() => fileRef.current?.click()} type="button">
          <Upload size={14} /> Load model
        </button>
        <input accept=".stl,.3mf,.obj" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void loadFile(file); }} ref={fileRef} type="file" />
      </div>
      <div className="toybox-canvas" ref={mountRef}>
        {!fileName && <div className="toybox-canvas-empty">Load an STL / 3MF / OBJ to preview and assign its color</div>}
      </div>
      <div className="toybox-palette">
        {palette.map((swatch) => (
          <button className={color === swatch ? 'toybox-pal active' : 'toybox-pal'} key={swatch} onClick={() => chooseColor(swatch)} style={{ background: swatch }} title={swatch} type="button" />
        ))}
        <input aria-label="Custom color" onChange={(event) => chooseColor(event.target.value)} type="color" value={color} />
        {fileName && <span className="toybox-viewer-file">{fileName}</span>}
      </div>
      {viewerError && <div className="memory-inline-result error">{viewerError}</div>}
    </div>
  );
}

function MemoryProfileDrawer() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [embed, setEmbed] = useState<{ embedded_chunks: number; total_chunks: number; pending: number } | null>(null);
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [newFact, setNewFact] = useState('');

  const load = useCallback(async () => {
    const [profileResult, embedResult] = await Promise.all([
      edisonApi.getUserProfile().catch(() => null),
      edisonApi.getEmbeddingStatus().catch(() => null),
    ]);
    if (profileResult) {
      setProfile(profileResult);
      setDraft(profileResult.summary);
    }
    if (embedResult) setEmbed(embedResult);
  }, []);
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 20000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function rebuild() {
    setBusy(true);
    try {
      const updated = await edisonApi.rebuildUserProfile();
      setProfile(updated);
      setDraft(updated.summary);
    } catch {
      /* surfaced as empty */
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    try {
      const updated = await edisonApi.setUserProfile(draft);
      setProfile(updated);
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }
  async function addFact() {
    if (!newFact.trim()) return;
    const updated = await edisonApi.addUserFact(newFact.trim());
    setProfile(updated);
    setNewFact('');
  }

  const pct = embed && embed.total_chunks ? Math.round((embed.embedded_chunks / embed.total_chunks) * 100) : 0;

  return (
    <details className="context-drawer rag-drawer">
      <summary>
        <span><Brain size={16} /> What Edison knows about you</span>
        <small>{profile?.facts?.length ? `${profile.facts.length} notes` : 'memory profile'}</small>
      </summary>
      <div className="context-drawer-content rag-drawer-content memory-profile">
        {embed && embed.pending > 0 && (
          <div className="memory-embed-progress">Indexing memory for semantic recall… {pct}% ({embed.embedded_chunks.toLocaleString()}/{embed.total_chunks.toLocaleString()})</div>
        )}
        {!editing ? (
          <div className="memory-profile-text">{profile?.summary?.trim() ? profile.summary : 'No profile yet — build one from your imported conversations.'}</div>
        ) : (
          <textarea className="memory-profile-edit" value={draft} onChange={(event) => setDraft(event.target.value)} rows={7} />
        )}
        <div className="memory-profile-actions">
          {!editing ? (
            <>
              <button className="secondary-button" onClick={() => setEditing(true)} type="button">Edit</button>
              <button className="secondary-button" disabled={busy} onClick={() => void rebuild()} type="button">{busy ? 'Building…' : 'Rebuild from memory'}</button>
            </>
          ) : (
            <>
              <button className="apply-button" disabled={busy} onClick={() => void save()} type="button">Save</button>
              <button className="secondary-button" onClick={() => { setEditing(false); setDraft(profile?.summary ?? ''); }} type="button">Cancel</button>
            </>
          )}
        </div>
        {profile?.facts && profile.facts.length > 0 && (
          <ul className="memory-profile-facts">
            {profile.facts.map((fact) => (
              <li key={fact.id}>
                <span>{fact.content}</span>
                <button className="toybox-iconbtn" onClick={() => void edisonApi.deleteUserFact(fact.id).then(setProfile).catch(() => undefined)} type="button"><Trash2 size={11} /></button>
              </li>
            ))}
          </ul>
        )}
        <div className="memory-fact-add">
          <input
            value={newFact}
            onChange={(event) => setNewFact(event.target.value)}
            placeholder="Add a fact (e.g. I run a 3D print shop)"
            onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); void addFact(); } }}
          />
          <button className="secondary-button" onClick={() => void addFact()} type="button">Add</button>
        </div>
      </div>
    </details>
  );
}

function ToyBoxPrinterCard({
  printer,
  status,
  onEdit,
  onDelete,
  onPrinted,
}: {
  printer: ToyBoxPrinterProfileRecord;
  status?: ToyBoxPrinterLiveStatus;
  onEdit: () => void;
  onDelete: () => void;
  onPrinted: () => void;
}) {
  const [files, setFiles] = useState<ToyBoxFileRecord[]>([]);
  const [showFiles, setShowFiles] = useState(false);
  const [uploadName, setUploadName] = useState('');
  const [pending, setPending] = useState<File | null>(null);
  const [fileBusy, setFileBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [showCam, setShowCam] = useState(true);
  const [lightOn, setLightOn] = useState(true);
  const [jogStep, setJogStep] = useState(10);
  const [showMove, setShowMove] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const meta = (printer.metadata ?? {}) as Record<string, unknown>;
  const color = String(status?.loaded_color ?? meta?.loaded_color ?? '');
  const address = String(meta?.ip ?? meta?.host ?? '');
  const model = String(meta?.model ?? '');
  const label = printer.kind === 'bambu' ? (model || 'bambu').toUpperCase() : printer.kind.toUpperCase();
  const online = Boolean(status?.online);
  const canPrint = ['bambu', 'moonraker', 'octoprint'].includes(printer.kind);
  const hasCamera = (printer.kind === 'bambu' && /x1|a1|p1s/i.test(model)) || Boolean(meta?.camera_url);

  const loadFiles = useCallback(async () => {
    setFiles(await edisonApi.listToyBoxFiles(printer.id).catch(() => []));
  }, [printer.id]);

  useEffect(() => {
    if (showFiles) void loadFiles();
  }, [showFiles, loadFiles]);

  async function doUpload() {
    if (!pending) return;
    setFileBusy(true);
    setNote(null);
    try {
      await edisonApi.uploadToyBoxFile(printer.id, pending, uploadName.trim() || pending.name);
      setUploadName('');
      setPending(null);
      if (inputRef.current) inputRef.current.value = '';
      await loadFiles();
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'Upload failed.');
    } finally {
      setFileBusy(false);
    }
  }

  async function sendFile(fileId: string) {
    setFileBusy(true);
    setNote(null);
    try {
      const result = await edisonApi.printToyBoxFile(fileId);
      setNote(result.detail);
      onPrinted();
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'Send failed.');
    } finally {
      setFileBusy(false);
    }
  }

  async function removeFile(fileId: string) {
    await edisonApi.deleteToyBoxFile(fileId).catch(() => undefined);
    await loadFiles();
  }

  async function control(
    action: 'pause' | 'resume' | 'stop' | 'light_on' | 'light_off' | 'home' | 'jog',
    extra?: { axis?: string; distance?: number },
  ) {
    setNote(null);
    try {
      const result = await edisonApi.controlToyBoxPrinter(printer.id, action, extra);
      setNote(result.detail);
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'Command failed.');
    }
  }

  function toggleLight() {
    const next = !lightOn;
    setLightOn(next);
    void control(next ? 'light_on' : 'light_off');
  }

  return (
    <article className={online ? 'toybox-printer online' : 'toybox-printer'}>
      <div className="toybox-printer-head">
        <strong>{printer.name}</strong>
        <div className="toybox-printer-head-right">
          <span className={online ? 'toybox-dot on' : 'toybox-dot off'} />
          <button className="toybox-iconbtn" onClick={onEdit} title="Edit settings" type="button"><Settings size={13} /></button>
          <button className="toybox-iconbtn" onClick={onDelete} title="Remove printer" type="button"><Trash2 size={13} /></button>
        </div>
      </div>
      <div className="toybox-printer-meta">{label} · {address}</div>
      {color && (
        <div className="toybox-filament">
          <span className="toybox-swatch" style={{ background: TOYBOX_COLOR_HEX[color] ?? color }} />
          {color} {String(status?.loaded_material ?? meta?.loaded_material ?? '')}
        </div>
      )}
      {online ? (
        <>
          <div className="toybox-state">{status?.state ?? 'idle'}{status?.job_name ? ` · ${status.job_name}` : ''}</div>
          {typeof status?.progress === 'number' && status.progress > 0 && (
            <div className="toybox-progress"><span style={{ width: `${status.progress}%` }} /><em>{status.progress}%</em></div>
          )}
          <div className="toybox-temps">nozzle {Math.round(status?.nozzle_temp ?? 0)}° · bed {Math.round(status?.bed_temp ?? 0)}°{status?.remaining_min ? ` · ${status.remaining_min}m left` : ''}</div>
          <div className="toybox-controls">
            <button className="toybox-ctrl" onClick={() => void control('pause')} title="Pause" type="button"><Pause size={13} /> Pause</button>
            <button className="toybox-ctrl" onClick={() => void control('resume')} title="Resume" type="button"><Play size={13} /> Resume</button>
            <button className="toybox-ctrl danger" onClick={() => void control('stop')} title="Stop" type="button"><Square size={11} /> Stop</button>
          </div>
          <div className="toybox-controls">
            <button className={lightOn ? 'toybox-ctrl on' : 'toybox-ctrl'} onClick={toggleLight} title="Toggle chamber light" type="button"><Lightbulb size={13} /> {lightOn ? 'Light off' : 'Light on'}</button>
            <button className="toybox-ctrl" onClick={() => void control('home')} title="Home all axes" type="button"><Home size={12} /> Home</button>
            <button className={showMove ? 'toybox-ctrl on' : 'toybox-ctrl'} onClick={() => setShowMove((value) => !value)} title="Jog controls" type="button"><Move size={12} /> Move</button>
          </div>
          {showMove && (
            <div className="toybox-jog">
              <div className="toybox-jog-pad">
                <button className="toybox-jog-btn yp" onClick={() => void control('jog', { axis: 'Y', distance: jogStep })} type="button">Y+</button>
                <button className="toybox-jog-btn xm" onClick={() => void control('jog', { axis: 'X', distance: -jogStep })} type="button">X−</button>
                <button className="toybox-jog-btn ho" onClick={() => void control('home')} title="Home" type="button"><Home size={12} /></button>
                <button className="toybox-jog-btn xp" onClick={() => void control('jog', { axis: 'X', distance: jogStep })} type="button">X+</button>
                <button className="toybox-jog-btn ym" onClick={() => void control('jog', { axis: 'Y', distance: -jogStep })} type="button">Y−</button>
              </div>
              <div className="toybox-jog-z">
                <button className="toybox-jog-btn" onClick={() => void control('jog', { axis: 'Z', distance: jogStep })} type="button">Z+</button>
                <button className="toybox-jog-btn" onClick={() => void control('jog', { axis: 'Z', distance: -jogStep })} type="button">Z−</button>
              </div>
              <div className="toybox-jog-step">
                {[1, 10, 50].map((step) => (
                  <button
                    key={step}
                    className={jogStep === step ? 'active' : ''}
                    onClick={() => setJogStep(step)}
                    type="button"
                  >
                    {step}mm
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="toybox-offline">{status?.detail ?? 'Connecting…'}</div>
      )}

      {hasCamera && (
        <>
          {showCam && (
            <div className="toybox-cam">
              <img
                className="toybox-cam-img"
                src={`/api/v1/toybox/printers/${printer.id}/camera`}
                alt={`${printer.name} camera`}
                onError={() => setNote('Camera stream unavailable — for the X1C enable LAN Mode Liveview on the printer; the A1 mini camera needs LAN access on.')}
              />
            </div>
          )}
          <button className="toybox-files-toggle" onClick={() => setShowCam((value) => !value)} type="button">
            <Camera size={13} /> {showCam ? 'Hide camera' : 'Show camera'}
          </button>
        </>
      )}

      {canPrint && (
        <button className="toybox-files-toggle" onClick={() => setShowFiles((value) => !value)} type="button">
          <FileText size={13} /> Files{files.length ? ` (${files.length})` : ''}
        </button>
      )}
      {canPrint && showFiles && (
        <div className="toybox-files">
          <div className="toybox-file-upload">
            <input
              ref={inputRef}
              type="file"
              accept=".gcode,.gco,.g,.3mf"
              onChange={(event) => {
                const chosen = event.target.files?.[0] ?? null;
                setPending(chosen);
                if (chosen && !uploadName) setUploadName(chosen.name);
              }}
            />
            <input placeholder="Name (optional)" value={uploadName} onChange={(event) => setUploadName(event.target.value)} />
            <button className="secondary-button icon-text-button" disabled={!pending || fileBusy} onClick={() => void doUpload()} type="button">
              <Upload size={13} /> Add
            </button>
          </div>
          {files.map((file) => (
            <div className="toybox-file-row" key={file.id}>
              <span className="toybox-file-kind">{file.kind}</span>
              <div className="toybox-file-info">
                <strong>{file.name}</strong>
                <span>{(file.size / 1024).toFixed(0)} KB</span>
              </div>
              <button className="toybox-iconbtn send" disabled={fileBusy} onClick={() => void sendFile(file.id)} title="Send to printer & start print" type="button"><Printer size={13} /></button>
              <button className="toybox-iconbtn" onClick={() => void removeFile(file.id)} title="Delete file" type="button"><Trash2 size={12} /></button>
            </div>
          ))}
          {files.length === 0 && <div className="toybox-files-empty">No files yet. Add a .gcode or .3mf, name it, then hit the printer icon to send &amp; print.</div>}
        </div>
      )}
      {note && <div className="toybox-file-note">{note}</div>}
    </article>
  );
}

function ToyBoxView() {
  const [printers, setPrinters] = useState<ToyBoxPrinterProfileRecord[]>([]);
  const [discovered, setDiscovered] = useState<ToyBoxDiscoveredPrinter[]>([]);
  const [live, setLive] = useState<Record<string, ToyBoxPrinterLiveStatus>>({});
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [queue, setQueue] = useState<ToyBoxQueueItemRecord[]>([]);
  const [form, setForm] = useState({ name: '', connection: 'bambu', ip: '', serial: '', access_code: '', host: '', api_key: '', model: 'x1c', camera_url: '', loaded_color: '', loaded_material: 'PLA' });
  const [routeProduct, setRouteProduct] = useState('');
  const [routeColor, setRouteColor] = useState('');
  const [routeResult, setRouteResult] = useState<ToyBoxRouteResult | null>(null);
  const [routing, setRouting] = useState(false);

  async function routeOrder() {
    if (!routeProduct.trim()) return;
    setRouting(true);
    try {
      setRouteResult(await edisonApi.routeToyBoxOrder({ product: routeProduct.trim(), color: routeColor.trim() || null }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Routing failed.');
    } finally {
      setRouting(false);
    }
  }

  const loadPrinters = useCallback(async () => {
    try {
      setPrinters(await edisonApi.listToyBoxPrinters());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load printers.');
    }
  }, []);
  useEffect(() => {
    void loadPrinters();
  }, [loadPrinters]);

  const loadQueue = useCallback(async () => {
    setQueue(await edisonApi.listToyBoxQueue().catch(() => []));
  }, []);
  useEffect(() => {
    void loadQueue();
    const timer = window.setInterval(() => void loadQueue(), 8000);
    return () => window.clearInterval(timer);
  }, [loadQueue]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const bambu = printers.filter(
      (printer) =>
        ['bambu', 'creality', 'moonraker', 'octoprint'].includes(printer.kind) &&
        ((printer.metadata as Record<string, unknown>)?.ip || (printer.metadata as Record<string, unknown>)?.host),
    );
    async function poll() {
      const updates: Record<string, ToyBoxPrinterLiveStatus> = {};
      await Promise.all(
        bambu.map(async (printer) => {
          const status = await edisonApi.getToyBoxPrinterLive(printer.id).catch(() => null);
          if (status) updates[printer.id] = status;
        }),
      );
      if (!cancelled) {
        setLive((current) => ({ ...current, ...updates }));
        timer = window.setTimeout(() => void poll(), 6000);
      }
    }
    if (bambu.length) void poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [printers]);

  async function scan() {
    setScanning(true);
    try {
      setDiscovered(await edisonApi.discoverToyBoxPrinters());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network scan failed.');
    } finally {
      setScanning(false);
    }
  }

  async function addPrinter() {
    const host = (form.connection === 'bambu' ? form.ip : form.host || form.ip).trim();
    if (!form.name.trim() || !host) return;
    setBusy(true);
    try {
      const metadata: Record<string, unknown> = {
        loaded_color: form.loaded_color.trim().toLowerCase(),
        loaded_material: form.loaded_material.trim(),
      };
      if (form.connection === 'bambu') {
        metadata.ip = form.ip.trim();
        metadata.serial = form.serial.trim();
        metadata.access_code = form.access_code.trim();
        metadata.model = form.model;
      } else {
        metadata.host = host;
        if (form.connection === 'octoprint') metadata.api_key = form.api_key.trim();
      }
      if (form.camera_url.trim()) metadata.camera_url = form.camera_url.trim();
      await edisonApi.upsertToyBoxPrinter({ name: form.name.trim(), kind: form.connection, role: 'printer', status: 'ready', metadata });
      setForm({ name: '', connection: form.connection, ip: '', serial: '', access_code: '', host: '', api_key: '', model: 'x1c', camera_url: '', loaded_color: '', loaded_material: 'PLA' });
      await loadPrinters();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add printer.');
    } finally {
      setBusy(false);
    }
  }

  function editPrinter(printer: ToyBoxPrinterProfileRecord) {
    const meta = (printer.metadata ?? {}) as Record<string, unknown>;
    const connection = ['bambu', 'creality', 'moonraker', 'octoprint'].includes(printer.kind) ? printer.kind : 'bambu';
    setForm({
      name: printer.name,
      connection,
      ip: String(meta.ip ?? ''),
      serial: String(meta.serial ?? ''),
      access_code: String(meta.access_code ?? ''),
      host: String(meta.host ?? ''),
      api_key: String(meta.api_key ?? ''),
      model: String(meta.model ?? 'x1c'),
      camera_url: String(meta.camera_url ?? ''),
      loaded_color: String(meta.loaded_color ?? ''),
      loaded_material: String(meta.loaded_material ?? 'PLA'),
    });
    setShowAdd(true);
  }

  async function deletePrinter(printerId: string) {
    await edisonApi.deleteToyBoxPrinter(printerId).catch(() => undefined);
    await loadPrinters();
  }

  const bambuPrinters = printers.filter((printer) => ['bambu', 'creality', 'moonraker', 'octoprint'].includes(printer.kind));

  const reverseColorName = (hex: string) =>
    Object.entries(TOYBOX_COLOR_HEX).find(([, value]) => value.toLowerCase() === hex.toLowerCase())?.[0];

  return (
    <section className="workbench-view toybox-view" aria-label="Toy Box management">
      <div className="toybox-toolbar">
        <div className="toybox-toolbar-title">
          <Box size={20} />
          <span>Toy Box Management</span>
          <small>{bambuPrinters.length} printer{bambuPrinters.length === 1 ? '' : 's'} · {queue.length} queued</small>
        </div>
        <div className="toybox-toolbar-actions">
          <button className="secondary-button icon-text-button" disabled={scanning} onClick={() => void scan()} type="button">
            <Search size={15} /> {scanning ? 'Scanning…' : 'Scan'}
          </button>
          <button className={showAdd ? 'apply-button icon-text-button toybox-addbtn active' : 'apply-button icon-text-button toybox-addbtn'} onClick={() => setShowAdd((value) => !value)} type="button">
            <Box size={15} /> {showAdd ? 'Close' : 'Add printer'}
          </button>
        </div>
      </div>
      {error && <div className="memory-inline-result error">{error}</div>}

      {showAdd && (
        <section className="toybox-add toybox-add-panel">
          <div className="section-heading">
            <Box size={18} /><h3>Add a printer</h3>
          </div>
          <p className="assistant-intro">
            <strong>Bambu</strong>: Settings → Network → LAN Only Mode shows the Access Code; Serial is under Device info.
            <strong> K1 SE</strong>: its IP (Moonraker). <strong>CR10S</strong>: an OctoPrint host + API key.
          </p>
          <div className="toybox-add-grid">
          <select onChange={(event) => setForm({ ...form, connection: event.target.value })} value={form.connection}>
            <option value="bambu">Bambu (LAN / MQTT)</option>
            <option value="creality">Creality K1 / K1 SE (LAN)</option>
            <option value="moonraker">Klipper (Moonraker)</option>
            <option value="octoprint">OctoPrint (CR10S)</option>
          </select>
          <input onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Name (e.g. X1C)" value={form.name} />
          {form.connection === 'bambu' ? (
            <>
              <input onChange={(event) => setForm({ ...form, ip: event.target.value })} placeholder="IP (e.g. 192.168.1.8)" value={form.ip} />
              <input onChange={(event) => setForm({ ...form, serial: event.target.value })} placeholder="Serial number" value={form.serial} />
              <input onChange={(event) => setForm({ ...form, access_code: event.target.value })} placeholder="Access code" value={form.access_code} />
              <select onChange={(event) => setForm({ ...form, model: event.target.value })} value={form.model}>
                <option value="x1c">X1C</option>
                <option value="a1mini">A1 mini</option>
                <option value="a1">A1</option>
                <option value="p1s">P1S</option>
              </select>
            </>
          ) : (
            <>
              <input
                onChange={(event) => setForm({ ...form, host: event.target.value })}
                placeholder={form.connection === 'octoprint' ? 'OctoPrint host (IP or URL)' : 'Printer IP / host'}
                value={form.host}
              />
              {form.connection === 'octoprint' && (
                <input onChange={(event) => setForm({ ...form, api_key: event.target.value })} placeholder="OctoPrint API key" value={form.api_key} />
              )}
            </>
          )}
          <input onChange={(event) => setForm({ ...form, loaded_color: event.target.value })} placeholder="Loaded color (e.g. blue)" value={form.loaded_color} />
          <input onChange={(event) => setForm({ ...form, loaded_material: event.target.value })} placeholder="Material (PLA)" value={form.loaded_material} />
          <input
            onChange={(event) => setForm({ ...form, camera_url: event.target.value })}
            placeholder={form.connection === 'bambu' ? 'Camera URL (optional — X1C auto)' : 'Camera URL (MJPEG/RTSP, optional)'}
            value={form.camera_url}
          />
          <button
            className="apply-button icon-text-button"
            disabled={busy || !form.name.trim() || !(form.connection === 'bambu' ? form.ip.trim() : form.host.trim() || form.ip.trim())}
            onClick={() => void addPrinter()}
            type="button"
          >
            <Box size={15} /> Add printer
          </button>
          </div>
        </section>
      )}

      {discovered.length > 0 && (
        <section className="toybox-discovered">
          <div className="section-heading"><Search size={18} /><h3>Found on your network</h3></div>
          <div className="toybox-found-grid">
            {discovered.map((item) => {
              const kind = ['bambu', 'creality', 'moonraker', 'octoprint'].includes(item.kind) ? item.kind : 'bambu';
              const modelValue = (() => {
                const lowered = (item.model || '').toLowerCase();
                if (lowered.includes('mini')) return 'a1mini';
                if (lowered.includes('a1')) return 'a1';
                if (lowered.includes('p1')) return 'p1s';
                return 'x1c';
              })();
              return (
                <article className="toybox-found-card" key={item.ip}>
                  <strong>{item.model || item.label}</strong>
                  <span>{item.ip}</span>
                  {item.serial ? <span>SN {item.serial}</span> : null}
                  <span className="toybox-kind">{item.kind}</span>
                  {item.already_added ? (
                    <span className="toybox-added">added</span>
                  ) : (
                    <button
                      className="secondary-button"
                      onClick={() => {
                        setShowAdd(true);
                        setForm((current) => ({
                          ...current,
                          connection: kind,
                          ip: kind === 'bambu' ? item.ip : current.ip,
                          host: kind !== 'bambu' ? item.ip : current.host,
                          serial: item.serial || current.serial,
                          model: item.model ? modelValue : current.model,
                          name: current.name || item.model || `${item.kind} ${item.ip.split('.').pop()}`,
                        }));
                      }}
                      type="button"
                    >
                      Use ↑
                    </button>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      )}

      <div className="toybox-dashboard">
        <div className="toybox-dash-main">
          <div className="toybox-printer-grid">
            {bambuPrinters.map((printer) => (
              <ToyBoxPrinterCard
                key={printer.id}
                printer={printer}
                status={live[printer.id]}
                onEdit={() => editPrinter(printer)}
                onDelete={() => void deletePrinter(printer.id)}
                onPrinted={() => void loadQueue()}
              />
            ))}
            {bambuPrinters.length === 0 && <div className="empty-line">No printers yet — click “Add printer” above, or Scan to find them.</div>}
          </div>
          <ModelViewer onColorChosen={(hex) => { const name = reverseColorName(hex); if (name) setRouteColor(name); }} />
        </div>

        <div className="toybox-dash-side">
          <section className="toybox-route">
            <div className="section-heading"><Waypoints size={18} /><h3>Route a print order</h3></div>
            <p className="assistant-intro">Type an order (e.g. “blue keychain”) and Edison picks the printer with that color loaded.</p>
            <div className="toybox-route-row">
              <input
                onChange={(event) => setRouteProduct(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    void routeOrder();
                  }
                }}
                placeholder="Order (e.g. blue keychain)"
                value={routeProduct}
              />
              <input className="toybox-route-color" onChange={(event) => setRouteColor(event.target.value)} placeholder="color" value={routeColor} />
              <button className="apply-button icon-text-button" disabled={routing || !routeProduct.trim()} onClick={() => void routeOrder()} type="button">
                <Waypoints size={15} /> Route
              </button>
            </div>
            {routeResult && (
              <div className={routeResult.matched_printer_id ? 'toybox-route-result ok' : 'toybox-route-result warn'}>
                <strong>{routeResult.reason}</strong>
                <div className="toybox-route-cands">
                  {routeResult.candidates.map((candidate) => (
                    <span className={candidate.printer_id === routeResult.matched_printer_id ? 'toybox-cand matched' : 'toybox-cand'} key={candidate.printer_id}>
                      {candidate.loaded_color && <span className="toybox-swatch" style={{ background: TOYBOX_COLOR_HEX[candidate.loaded_color] ?? candidate.loaded_color }} />}
                      {candidate.printer_name}: {candidate.note}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="toybox-queue">
            <div className="section-heading"><Activity size={18} /><h3>Order queue</h3></div>
            <div className="toybox-queue-list">
              {queue.map((item) => (
                <article className="toybox-queue-item" key={item.id}>
                  <span className={`toybox-q-status ${item.status}`}>{item.status.replace(/_/g, ' ')}</span>
                  <div className="toybox-q-body">
                    <strong>{item.title}</strong>
                    {item.printer_id && <span>→ {printers.find((entry) => entry.id === item.printer_id)?.name ?? item.printer_id}</span>}
                  </div>
                </article>
              ))}
              {queue.length === 0 && <div className="empty-line">Queue is empty. Routed orders will appear here.</div>}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}

function ScheduledView() {
  const [status, setStatus] = useState<ScheduledTasksStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [kind, setKind] = useState<'daily' | 'interval'>('daily');
  const [timeOfDay, setTimeOfDay] = useState('08:00');
  const [intervalMinutes, setIntervalMinutes] = useState(60);
  const [includeBriefing, setIncludeBriefing] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await edisonApi.listScheduledTasks());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load scheduled tasks.');
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function create() {
    if (!title.trim() || !prompt.trim()) return;
    setBusy(true);
    try {
      await edisonApi.createScheduledTask({
        title: title.trim(),
        prompt: prompt.trim(),
        schedule_kind: kind,
        time_of_day: timeOfDay,
        interval_minutes: intervalMinutes,
        include_briefing: includeBriefing,
      });
      setTitle('');
      setPrompt('');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create task.');
    } finally {
      setBusy(false);
    }
  }
  async function runNow(id: string) {
    setRunningId(id);
    try {
      await edisonApi.runScheduledTask(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Run failed.');
    } finally {
      setRunningId(null);
    }
  }
  async function toggle(task: ScheduledTaskRecord) {
    await edisonApi.updateScheduledTask(task.id, { enabled: !task.enabled }).catch(() => undefined);
    await load();
  }
  async function remove(id: string) {
    await edisonApi.deleteScheduledTask(id).catch(() => undefined);
    await load();
  }

  const tasks = status?.tasks ?? [];
  const serverTime = status?.server_time ? new Date(status.server_time).toLocaleString() : '—';

  return (
    <section className="workbench-view scheduled-view" aria-label="Scheduled agents">
      <div className="view-heading">
        <CalendarDays size={26} />
        <h3>Scheduled Agents</h3>
        <button className="secondary-button icon-text-button" onClick={() => void load()} type="button">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>
      <p className="assistant-intro">
        Edison runs these prompts automatically on a schedule (server time: {serverTime}). Enable “include live context”
        for briefings to inject the current time + weather.
      </p>
      {error && <div className="memory-inline-result error">{error}</div>}

      <section className="scheduled-create">
        <div className="section-heading"><CalendarDays size={18} /><h3>New scheduled task</h3></div>
        <input onChange={(event) => setTitle(event.target.value)} placeholder="Title — e.g. Morning briefing" value={title} />
        <textarea
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="What should Edison do? e.g. Give me a short morning briefing with the weather and three priorities for today."
          rows={3}
          value={prompt}
        />
        <div className="scheduled-create-row">
          <label>
            Schedule
            <select onChange={(event) => setKind(event.target.value as 'daily' | 'interval')} value={kind}>
              <option value="daily">Daily at</option>
              <option value="interval">Every</option>
            </select>
          </label>
          {kind === 'daily' ? (
            <input onChange={(event) => setTimeOfDay(event.target.value)} type="time" value={timeOfDay} />
          ) : (
            <label className="scheduled-interval">
              <input min={5} max={10080} onChange={(event) => setIntervalMinutes(Number(event.target.value) || 60)} type="number" value={intervalMinutes} /> min
            </label>
          )}
          <label className="inline-toggle">
            <input checked={includeBriefing} onChange={(event) => setIncludeBriefing(event.target.checked)} type="checkbox" /> include live context
          </label>
          <button className="apply-button icon-text-button" disabled={busy || !title.trim() || !prompt.trim()} onClick={() => void create()} type="button">
            <Send size={15} /> Schedule
          </button>
        </div>
      </section>

      <div className="scheduled-list">
        {tasks.map((task) => (
          <article className={task.enabled ? 'scheduled-card' : 'scheduled-card off'} key={task.id}>
            <div className="scheduled-card-head">
              <strong>{task.title}</strong>
              <span className="scheduled-when">
                {task.schedule_kind === 'daily' ? `daily ${task.time_of_day}` : `every ${task.interval_minutes}m`}
                {task.include_briefing ? ' · live' : ''}
              </span>
              <div className="scheduled-actions">
                <button className="secondary-button" disabled={runningId === task.id} onClick={() => void runNow(task.id)} type="button">
                  {runningId === task.id ? 'Running…' : 'Run now'}
                </button>
                <button className="secondary-button" onClick={() => void toggle(task)} type="button">{task.enabled ? 'Pause' : 'Enable'}</button>
                <button className="icon-button" onClick={() => void remove(task.id)} title="Delete" type="button"><Trash2 size={14} /></button>
              </div>
            </div>
            <p className="scheduled-prompt">{task.prompt}</p>
            <div className="scheduled-meta">
              <span>next: {task.next_run_at ? new Date(task.next_run_at).toLocaleString() : '—'}</span>
              {task.last_run_at && <span>last: {new Date(task.last_run_at).toLocaleString()} · {task.last_status}</span>}
            </div>
            {task.last_result && (
              <details className="scheduled-result">
                <summary>Last result</summary>
                <MessageContent content={task.last_result} metadata={{}} />
              </details>
            )}
          </article>
        ))}
        {tasks.length === 0 && <div className="empty-line">No scheduled tasks yet — create one above.</div>}
      </div>
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
  const [chatFiles, setChatFiles] = useState<File[]>([]);
  const [chatSource, setChatSource] = useState<ChatImportSource>('auto');
  const [chatImporting, setChatImporting] = useState(false);
  const [chatResult, setChatResult] = useState<string | null>(null);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const [webQuery, setWebQuery] = useState('');
  const [webBusy, setWebBusy] = useState(false);
  const [webResult, setWebResult] = useState<string | null>(null);
  const presetButtons: Array<{ preset: KnowledgePreset; label: string }> = [
    { preset: 'coding-reference', label: 'Coding Reference' },
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

          <form
            className="memory-import-form chat-import"
            onSubmit={(event) => {
              event.preventDefault();
              if (!chatFiles.length || chatImporting) {
                return;
              }
              setChatImporting(true);
              setChatResult(null);
              void edisonApi
                .importKnowledgeChatExport(chatFiles, chatSource)
                .then(async (result) => {
                  const skippedNote = result.skipped_count ? ` (${result.skipped_count} skipped)` : '';
                  setChatResult(
                    `Imported ${result.imported_count} of ${result.conversation_count} ${result.detected_source} conversation${result.conversation_count === 1 ? '' : 's'}${skippedNote}.`,
                  );
                  setChatFiles([]);
                  if (chatInputRef.current) {
                    chatInputRef.current.value = '';
                  }
                  await onRefresh();
                })
                .catch((error: unknown) => {
                  setChatResult(error instanceof Error ? error.message : 'Chat import failed.');
                })
                .finally(() => setChatImporting(false));
            }}
          >
            <label htmlFor="knowledge-chat-export">Claude / ChatGPT Chats</label>
            <input
              id="knowledge-chat-export"
              ref={chatInputRef}
              type="file"
              accept=".json,.zip,application/json,application/zip"
              multiple
              onChange={(event) => setChatFiles(Array.from(event.target.files ?? []))}
            />
            <select
              aria-label="Chat export source"
              value={chatSource}
              onChange={(event) => setChatSource(event.target.value as ChatImportSource)}
            >
              <option value="auto">Auto-detect</option>
              <option value="chatgpt">ChatGPT</option>
              <option value="claude">Claude</option>
            </select>
            <button
              className="secondary-button icon-text-button"
              disabled={!chatFiles.length || chatImporting || isBusy}
              type="submit"
            >
              <MessageSquare size={16} />
              {chatImporting ? 'Importing...' : 'Import Chats'}
            </button>
            <small className="memory-import-hint">
              Upload <code>conversations.json</code> or the export <code>.zip</code> from your ChatGPT or Claude data export.
            </small>
            {chatResult && <div className="memory-inline-result">{chatResult}</div>}
          </form>

          <form
            className="memory-import-form web-search-import"
            onSubmit={(event) => {
              event.preventDefault();
              const query = webQuery.trim();
              if (!query || webBusy) {
                return;
              }
              setWebBusy(true);
              setWebResult(null);
              void edisonApi
                .ingestKnowledgeWebSearch({ query, max_results: 4 })
                .then(async (sources) => {
                  setWebResult(`Saved ${sources.length} web result${sources.length === 1 ? '' : 's'} to memory.`);
                  setWebQuery('');
                  await onRefresh();
                })
                .catch((error: unknown) => {
                  setWebResult(error instanceof Error ? error.message : 'Web search failed.');
                })
                .finally(() => setWebBusy(false));
            }}
          >
            <label htmlFor="knowledge-web-search">Search the web</label>
            <input
              id="knowledge-web-search"
              value={webQuery}
              onChange={(event) => setWebQuery(event.target.value)}
              placeholder="Search the internet and remember the top results"
            />
            <button
              className="secondary-button icon-text-button"
              disabled={!webQuery.trim() || webBusy || isBusy}
              type="submit"
            >
              <Globe2 size={16} />
              {webBusy ? 'Searching...' : 'Search & Remember'}
            </button>
            <small className="memory-import-hint">
              Runs a DuckDuckGo search, fetches the top pages, and stores them in Edison's knowledge base.
            </small>
            {webResult && <div className="memory-inline-result">{webResult}</div>}
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
  onCreateGeneration: (mode: MediaGenerationMode, prompt: string, referenceFile?: File | null, metadata?: Record<string, unknown>) => Promise<void>;
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
    {
      label: 'Creator Studio',
      status: mediaStatus?.creator_studio.status ?? 'setup_required',
      detail: mediaStatus?.creator_studio.detail ?? 'Creator Studio assets have not been checked yet.',
      meta: mediaStatus?.creator_studio.normalized_root ?? mediaStatus?.creator_studio.source_path ?? 'No creator bundle path',
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
  const toyboxDashboard = toyBoxStatus?.dashboard ?? {};
  const orderCounts = dashboardBucket(toyboxDashboard, 'orders');
  const queueCounts = dashboardBucket(toyboxDashboard, 'queue');
  const webhookCounts = dashboardBucket(toyboxDashboard, 'webhooks');
  const toyboxMetrics = [
    ['Open Orders', dashboardNumber(toyboxDashboard, 'open_orders'), formatCountSummary(orderCounts)],
    ['Queue Items', Object.values(queueCounts).reduce((sum, value) => sum + value, 0), formatCountSummary(queueCounts)],
    ['Blocked', dashboardNumber(toyboxDashboard, 'blocked_queue'), 'Needs mapping, printer, or operator attention'],
    ['Webhooks', webhookCounts.received ?? 0, dashboardFlag(toyboxDashboard, 'shopify', 'webhooks_enabled') ? 'Signed Shopify intake enabled' : 'Shopify intake disabled'],
    ['Ready Mappings', dashboardNumber(toyboxDashboard, 'ready_mappings'), 'SKU to print profiles ready'],
  ];

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
          {toyBoxStatus && (
            <div className="toybox-metric-grid">
              {toyboxMetrics.map(([label, value, detail]) => (
                <article className="toybox-metric-card" key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                  <small>{detail}</small>
                </article>
              ))}
            </div>
          )}
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
  onDeleteArtifact,
  onDeleteJob,
  onRefresh,
  onUseArtifactInChat,
  runtimeSettings,
}: {
  artifacts: ArtifactRecord[];
  jobs: JobRecord[];
  onDeleteArtifact: (artifact: ArtifactRecord) => Promise<void> | void;
  onDeleteJob: (job: JobRecord) => Promise<void> | void;
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
                  <button className="danger-button" onClick={() => void onDeleteArtifact(artifact)} type="button">
                    <Trash2 size={14} />
                    Delete
                  </button>
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
                <div className="job-row-actions">
                  <span className={`job-status ${job.status}`}>{job.status}</span>
                  <button
                    aria-label={`Delete generation job ${job.title}`}
                    className="icon-danger-button"
                    onClick={() => void onDeleteJob(job)}
                    title="Delete job"
                    type="button"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
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
    ['creator_photo', 'Creator Photo', 'creator', 'image', 'comfyui', 'Photoreal virtual creator images using safe AI-only persona references.', true, 'Photoreal image', 'Describe a non-explicit creator photo.'],
    ['creator_video', 'Creator Video', 'creator', 'video', 'wan22', 'Short safe virtual creator video clips.', true, 'Short video', 'Describe a safe creator video clip.'],
    ['creator_dataset', 'Creator Dataset', 'creator', 'document', 'creator-studio', 'Dataset intake and training handoff plan.', true, 'Dataset spec', 'Describe the fictional persona and dataset.'],
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
  onClose,
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
  onClose: () => void;
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
        <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
          <button className="apply-button" form="runtime-settings-form" type="submit">Save Changes</button>
          <button className="secondary-button icon-text-button" onClick={onClose} type="button">
            <X size={15} /> Done
          </button>
        </div>
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
              checked={settingBoolean(draft.toybox, 'shopify_webhooks_enabled', true)}
              onChange={(event) => updateSetting('toybox', 'shopify_webhooks_enabled', event.target.checked)}
              type="checkbox"
            />
            <span>Accept signed Shopify order webhooks</span>
          </label>
          <label className="settings-toggle-row">
            <input
              checked={settingBoolean(draft.toybox, 'auto_queue_orders', true)}
              onChange={(event) => updateSetting('toybox', 'auto_queue_orders', event.target.checked)}
              type="checkbox"
            />
            <span>Auto-create print queue items from mapped Shopify SKUs</span>
          </label>
          <label className="settings-toggle-row">
            <input
              checked={settingBoolean(draft.toybox, 'auto_print_labels', false)}
              onChange={(event) => updateSetting('toybox', 'auto_print_labels', event.target.checked)}
              type="checkbox"
            />
            <span>Auto-print shipping labels after QA approval</span>
          </label>
          <p className="settings-hint">Webhook endpoint: /api/v1/toybox/shopify/webhooks/orders. Set EDISON_SHOPIFY_WEBHOOK_SECRET on the Edison API service.</p>
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
      shopify_webhooks_enabled: true,
      auto_queue_orders: true,
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

function dashboardBucket(section: Record<string, unknown>, key: string): Record<string, number> {
  const value = section[key];
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => typeof item === 'number' && Number.isFinite(item))
      .map(([name, item]) => [name, item as number]),
  );
}

function dashboardNumber(section: Record<string, unknown>, key: string) {
  const value = section[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function dashboardFlag(section: Record<string, unknown>, bucket: string, key: string) {
  const value = section[bucket];
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  return (value as Record<string, unknown>)[key] === true;
}

function formatCountSummary(counts: Record<string, number>) {
  const entries = Object.entries(counts).filter(([, value]) => value > 0);
  if (!entries.length) {
    return 'No active records';
  }
  return entries.map(([key, value]) => `${key.replace('_', ' ')} ${value}`).join(' / ');
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
  if (isDesktopBridgeToolPrompt(content)) {
    return 'image';
  }
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
  if (isDesktopBridgeToolPrompt(content)) {
    return null;
  }
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
  const mentionsCreator = /\b(onlyfans|ai\s*creator|virtual\s*(creator|influencer|model)|creator\s*studio|fictional\s*persona|persona\s*dataset|creator\s*dataset|lora\s*persona)\b/.test(lowered);
  if (mentionsCreator) {
    if (/\b(dataset|training|lora|caption|trigger\s*token|persona\s*pack)\b/.test(lowered)) {
      return 'creator_dataset';
    }
    if (/\b(video|animation|clip|reel|shorts|motion|wan)\b/.test(lowered)) {
      return 'creator_video';
    }
    return 'creator_photo';
  }
  if (/\b(product\s*render|shopify\s*(image|photo|listing|thumbnail)|listing\s*(image|render)|toybox3d\s*(render|listing))\b/.test(lowered)) {
    return 'product_render';
  }
  if (/\b(social\s*media|instagram|tiktok|facebook|x post|tweet|caption|reel|shorts|campaign|ad copy)\b/.test(lowered)) {
    return 'social_media_content';
  }
  return null;
}

function isDesktopBridgeToolPrompt(content: string): boolean {
  const lowered = content.toLowerCase();
  const mentionsBridge = /\b(desktop\s*bridge|bridge\s*tools?|connected\s+(apps|tools|printers|slicers)|allowed\s+(folders|roots))\b/.test(lowered);
  const mentionsFusion = /\b(fusion\s*360|autodesk\s+fusion|fusion\s+bridge|use\s+fusion|in\s+fusion)\b/.test(lowered);
  const mentionsSlicer = /\b(bambu\s*studio|bambu\s*lab|orcaslicer|orca\s*slicer|cura|slicer\s+handoff|prepare\s+.*\bslicer|slice\s+this|print\s+handoff)\b/.test(lowered);
  const mentionsCadWorkflow = /\b(cad|parametric|sketch|extrude|chamfer|fillet|solid\s+body|step|iges|f3d)\b/.test(lowered)
    && /\b(mm|millimeter|dimension|stl|3mf|export|part|model|body|block)\b/.test(lowered);
  return mentionsBridge || mentionsFusion || mentionsSlicer || mentionsCadWorkflow;
}

function isMediaGenerationPrompt(content: string): boolean {
  if (isDesktopBridgeToolPrompt(content)) {
    return false;
  }
  const lowered = content.toLowerCase();
  return /\b(generate|make|create|render|draw|design|turn|convert|animate|produce)\b/.test(lowered)
    && /\b(image|picture|photo|art|poster|video|animation|movie|clip|3d|3-d|three-dimensional|mesh|glb|obj|stl|sculpt|modly|comfy|wan|minecraft|texture|texture\s*pack|resource\s*pack|blockbench|world|structure|schematic|product\s*render|shopify\s*listing|social\s*media|caption|campaign|onlyfans|ai\s*creator|virtual\s*(creator|influencer|model)|creator\s*studio|fictional\s*persona|creator\s*dataset|lora\s*persona)\b/.test(lowered);
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
    'candidate',
    'cataloged',
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
