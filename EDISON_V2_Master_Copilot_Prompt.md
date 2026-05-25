# EDISON V2 — Master GitHub Copilot Build Prompt

## Mission

Build **EDISON V2**, a local-first, modular, multi-agent AI assistant and creator/developer platform that feels like a combination of:

- **ChatGPT** for natural conversation, web-aware answers, memory, multimodal assistance, voice, and polished UX
- **Claude** for long-context project work, documents, thoughtful reasoning, and agentic workflows
- **GitHub Copilot / Claude Code** for coding, repository inspection, implementation, package installation, test execution, debugging, and project development
- **ComfyUI / creative AI pipelines** for image generation, image asset creation, video generation/editing, and other media workflows
- **A personal AI operating layer** for the user’s projects, files, apps, automations, local hardware, and future tool integrations

EDISON V2 should be designed as a **serious, extensible AI platform**, not a simple chatbot. It must be capable of general chat, reasoning, coding, media generation, agent workflows, memory, learning from user interactions, voice mode, and safe tool execution.

---

# 1. Hardware Target

Design EDISON V2 specifically for this hardware environment.

## Primary Edison AI PC
- CPU: **Intel i5-12600K**
- RAM: **128 GB DDR4**
- Storage:
  - **4 TB main SSD**
  - **2 × 2 TB SSDs**
- GPUs:
  - **RTX 3090 — 24 GB VRAM**
  - **RTX 5060 Ti — 16 GB VRAM**
  - **RTX 4060 Ti — 16 GB VRAM**
- Total local GPU VRAM: **56 GB**, but **do not assume pooled VRAM** unless a supported model/runtime explicitly implements tensor/pipeline parallelism.

## Laptop Node
- CPU: **Intel i7**
- RAM: **32 GB DDR4**
- GPU: **RTX A3000 — 6 GB VRAM**

## Beelink Mini PC Node
- Mini PC with:
  - **2 TB storage currently installed**
  - **6 SSD slots total**
- Treat this primarily as:
  - storage/indexing/cache/backup node
  - lightweight service node
  - file/database/vector-store/archive node
  - optionally a CPU task worker or automation service host

---

# 2. Core Product Vision

EDISON V2 should be an **all-in-one local AI assistant and production system** that can:

## Conversation and Intelligence
- Answer general questions
- Hold natural multi-turn conversations
- Search the internet when enabled
- Explain technical topics
- Summarize documents, folders, webpages, and codebases
- Remember user preferences, projects, context, and prior decisions
- Maintain persistent chat history
- Support follow-up questions naturally
- Support multiple response modes such as:
  - Instant / Fast
  - Chat
  - Reasoning / Thinking
  - Coding
  - Agent
  - Swarm / Multi-Agent
  - Creative / Media

## Memory, Learning, and Adaptation
Implement practical “learning” as:
- persistent user memory
- project memory
- conversation memory
- extracted facts/preferences
- task continuation state
- semantic recall
- self-improving workflow analytics
- prompt/profile adaptation based on user feedback

Do **not** claim magical sentience or true consciousness. Instead implement:
- **operational self-awareness**
- knowledge of EDISON’s own modules, enabled tools, service health, model status, GPU state, active tasks, and limits
- awareness of current session, current project, and previously generated artifacts
- ability to inspect its own source code in safe read-only ways unless an explicit development workflow authorizes controlled changes

## Voice Mode
EDISON V2 should support:
- microphone input
- wake-word or push-to-talk architecture
- speech-to-text
- streaming transcription if feasible
- text-to-speech
- a configurable Edison voice
- interruptions / barge-in where possible
- conversation transcript view
- optional voice orb / animation state in UI:
  - idle
  - listening
  - thinking
  - speaking
  - tool-running
  - error

## Agent Mode
EDISON V2 should support a true agent workflow:
- understand a goal
- create a plan
- select tools
- execute steps
- update user with progress
- pause for approval where required
- inspect results
- self-check
- recover from errors
- summarize work completed
- preserve logs and artifacts

Examples:
- “Research this topic and build a PDF report”
- “Look through this project and fix why it fails”
- “Create a logo concept, export assets, and zip them”
- “Analyze a repo, implement feature X, run tests, and show what changed”
- “Search the web for current information and compare options”

## Multi-Agent / Swarm Mode
Support coordinated specialist agents, such as:
- **Manager / Orchestrator Agent**
- **Planner Agent**
- **Research Agent**
- **Coder Agent**
- **Code Reviewer / QA Agent**
- **Debugger Agent**
- **Media Agent**
- **Document Agent**
- **Memory Agent**
- **Tool Safety Agent**
- **Critic / Verification Agent**

Swarm mode should allow:
- decomposition of complex tasks
- parallel subtasks when safe
- explicit task ownership
- cross-agent review
- final synthesis
- conflict resolution
- progress timeline in the UI

## Coding and Project Development
EDISON V2 should be able to act like a local coding agent:
- inspect codebases
- understand project structure
- map files, routes, modules, configs, and dependencies
- answer repo questions
- propose implementation plans
- edit files in controlled workspace contexts
- generate new modules
- refactor safely
- install packages where permitted
- run linters/tests/builds
- run shell commands in sandboxed or policy-controlled execution environments
- capture command outputs
- explain errors
- propose patches
- maintain a diff/patch log
- rollback or show change history where feasible

Important:
- destructive or security-sensitive actions require approval
- file writes must be workspace-scoped
- commands should be allowlisted or policy-checked
- changes should be logged, testable, and reversible

## Media and Artifact Generation
EDISON V2 should be able to generate:
- images
- image assets
- logos and brand materials
- web graphics
- social graphics
- videos
- short animations
- thumbnails
- PDFs
- Word documents
- text documents
- zip folders
- spreadsheets where useful
- basic 3D models / 3D workflows / export tooling where feasible
- STL/OBJ/GLB pipeline support where appropriate
- 3D-print-related assistant functions in future phases

It should provide:
- job queues
- render status
- output gallery
- metadata
- prompt history
- versioning of generated assets
- downloadable/exportable artifacts

---

# 3. Non-Negotiable Engineering Constraints

Follow these carefully.

## Preserve Existing Edison Work Where Applicable
If building inside or alongside the current Edison repo:
- **Do not break existing features**
- **Do not delete working routes, pages, services, or workflows**
- **Do not rename/move/delete top-level folders unless absolutely unavoidable**
- Prefer **additive modules**, compatibility layers, and gradual refactors
- Keep the app runnable after every major step
- Document any migration path
- Maintain backward compatibility wherever feasible

## Build Modularly
Avoid turning one service file into a massive monolith. Prefer:
- service modules
- route modules
- adapters
- registries
- typed schemas
- config-driven behavior
- feature flags
- plugin boundaries

## Local-First Architecture
EDISON V2 should work locally/offline for the majority of capabilities.
Internet/API integrations may be optional modules, but:
- local models
- local memory
- local files
- local UI
- local task orchestration
should be the default foundation.

## Do Not Assume Hardware Magic
- Do not assume multiple GPUs automatically become one pooled VRAM bank
- Implement a real **GPU Resource Manager**
- Detect GPUs dynamically
- Track VRAM usage
- Decide where models/jobs should run
- Route tasks based on model size, capability, and available VRAM
- Support task pausing/unloading where needed
- Plan for “exclusive render” modes for heavy media workflows

## Security and Safety
Build from the start with:
- least privilege
- safe tool execution
- command restrictions
- workspace-root file restrictions
- audit logs
- approval gates for destructive or external side effects
- secrets stored outside code
- API key/env variable usage
- authentication for remote nodes
- human approval modes for risky actions

---

# 4. Recommended High-Level Architecture

Build EDISON V2 as a multi-service platform.

## Core Services

### 4.1 Edison Core API
Primary backend, likely FastAPI-based if continuing existing architecture.

Responsibilities:
- authentication/session management
- chat endpoints
- conversation routing
- model routing
- agent execution requests
- memory access
- tools API
- project registry
- artifacts API
- job status API
- node registration/status
- health endpoints
- admin/system endpoints

### 4.2 Model Gateway / Model Router
A centralized routing layer for all AI model inference.

Responsibilities:
- register available local models
- route prompts by mode/capability
- select fast vs reasoning vs code vs vision model
- expose a unified API to other services
- support OpenAI-compatible local serving where useful
- support streaming tokens
- support structured outputs
- support model fallback rules
- support per-model context limits
- support prompt/system templates
- monitor latency, token use, and errors

Required design:
- `ModelRegistry`
- `ModelProfile`
- `ModelCapability`
- `ModelRouter`
- `InferenceRequest`
- `InferenceResponse`
- per-model configuration in YAML/JSON

Capabilities should include tags like:
- chat
- fast-chat
- reasoning
- coding
- vision
- tool-calling
- long-context
- JSON-structured-output
- multimodal

### 4.3 Agent Orchestration Service
Use a graph/state-machine approach for agents.

Responsibilities:
- task graph execution
- planning
- state persistence
- tool calling
- interruption/resume
- human approval checkpoints
- multi-agent workflows
- retries
- critic/reviewer passes
- final answer synthesis
- progress events for UI

Design:
- `AgentRun`
- `AgentState`
- `TaskPlan`
- `TaskStep`
- `ToolCall`
- `ToolResult`
- `ApprovalRequest`
- `AgentEvent`
- `AgentCheckpoint`

Agent modes:
- simple answer mode
- tool-using agent mode
- coding agent mode
- multi-agent swarm mode
- research mode
- media production mode

### 4.4 Memory Service
Responsibilities:
- chat history
- user memory
- project memory
- session state
- task continuity
- artifact references
- embeddings and semantic search
- fact extraction and memory updates
- user controls to inspect, edit, delete, disable memory

Required memory layers:
1. **Short-Term Conversation Context**
2. **Session State**
3. **Long-Term User Memory**
4. **Project Memory**
5. **Semantic Document Memory / RAG**
6. **Operational State Memory**
7. **Artifact Memory**

Suggested entities:
- users
- conversations
- messages
- memories
- memory_sources
- projects
- project_context
- artifacts
- tasks
- agent_runs
- tool_logs

### 4.5 Web Research / Browser Agent Service
Responsibilities:
- search the web
- open pages
- parse webpages
- extract relevant content
- optionally drive a browser for agent tasks
- maintain visual/live agent browser session in UI
- store citations/source metadata
- summarize with source grounding

Design goals:
- Playwright-based browser automation or equivalent
- optional headless and visible modes
- streamed browser snapshots/events to frontend
- source capture:
  - title
  - URL
  - timestamp
  - excerpt
  - search query
  - page notes

UI should show:
- live browser viewport or snapshots
- current page
- steps performed
- retrieved sources
- agent notes
- pause/approve button

### 4.6 Coding Agent / Dev Workspace Service
Responsibilities:
- inspect repos
- search files
- open files
- create code maps
- edit files in workspace
- run commands in controlled execution environment
- install dependencies when allowed
- run tests/builds
- collect logs
- produce patch summary
- maintain rollback metadata

Required capabilities:
- repo scanner
- dependency detector
- test runner
- command runner
- package installer interface
- patch generator/applier
- diff viewer
- validation reporter
- terminal output streaming

Security requirements:
- workspace root allowlist
- command allowlist or policy engine
- no arbitrary destructive shell commands without approval
- no hidden network exfiltration
- every write action logged
- every command result attached to agent run history

### 4.7 Tool / Plugin System
EDISON V2 should support a modular tool layer.

Tools may include:
- filesystem tools
- web search tools
- browser tools
- document tools
- image generation tools
- video tools
- code tools
- shell tools
- database tools
- printer/tools in future
- remote node tools

Design for:
- discoverable tool metadata
- schemas for tool input/output
- permissions
- tool categories
- rate limits
- dry-run mode
- approval-required flag
- audit logging
- plugin registration

Strongly consider compatibility with **MCP-style concepts**:
- Resources
- Prompts
- Tools

Even if full MCP support is not implemented immediately, architect the tool layer so MCP-style adapters can be added later.

### 4.8 Media Generation Service
Responsibilities:
- image generation
- image editing
- asset pipelines
- ComfyUI workflow execution
- video generation pipeline hooks
- upscaling
- background removal
- format conversion
- metadata capture
- GPU scheduling
- output gallery

Submodules:
- `ImageGenerationService`
- `ImageEditService`
- `VideoGenerationService`
- `AssetPackService`
- `ComfyWorkflowRunner`
- `MediaJobQueue`
- `MediaPresetRegistry`

Support:
- prompts
- negative prompts
- seeds
- workflow templates
- LoRA/model selection
- batch generation
- output folders
- preview images
- job retry

### 4.9 Document and Artifact Service
Generate and export:
- PDFs
- DOCX
- Markdown
- plain text
- ZIP archives
- tables and structured reports
- project briefs
- design specs
- implementation plans
- prompt packs
- code export bundles

Responsibilities:
- template engine
- artifact registry
- MIME/type metadata
- versioning
- packaging
- downloadable paths
- artifact previews where possible

### 4.10 Voice Service
Responsibilities:
- STT input
- TTS output
- streaming microphone sessions
- voice activation state
- low-latency conversational loop
- voice configuration/profile selection
- transcript storage
- audio device configuration

UI:
- mic button
- live waveform or input level
- transcription display
- speaker status
- voice mode settings

### 4.11 Node Manager / Distributed Worker System
Responsibilities:
- register laptop node and Beelink node
- heartbeat/status checks
- node capability profiles
- assign tasks to nodes
- receive artifacts/logs
- monitor disk and worker health
- define storage roles

Node roles:
- **Primary PC**: orchestration, main LLM inference, heavy AI media tasks
- **Laptop node**: smaller GPU jobs, background tasks, auxiliary model inference, light media preprocess
- **Beelink node**: storage, archives, vector DB backups, document indexing, download/cache services, CPU worker tasks

Implement:
- `NodeRegistry`
- `NodeHeartbeat`
- `NodeCapability`
- `TaskDispatch`
- `RemoteWorkerClient`
- `RemoteWorkerServer`
- secure auth between nodes
- private-network deployment support

---

# 5. Recommended Product UX

Build EDISON V2 to feel polished and modern.

## Main UI Sections

### 5.1 Chat
- ChatGPT-like conversational interface
- conversation list/history
- pinned conversations
- rename conversations
- search chat history
- message editing/regeneration
- attachments
- tool activity display
- citations/source panel where relevant
- memory toggle
- model/mode selector

### 5.2 Agent Mode
- task input
- generated plan
- live status timeline
- browser/coding/media step logs
- approvals area
- pause/resume/cancel
- live results
- final deliverables

### 5.3 Swarm Mode
- show each active specialist agent
- subtask assignment
- agent-to-agent handoff summary
- parallel progress indicators
- final synthesis panel

### 5.4 Code Workspace
- repository/file tree
- code viewer/editor
- diff viewer
- terminal output panel
- test results
- task history
- “Implement with Edison” workflow
- “Explain this repo” workflow
- “Fix failing build” workflow

### 5.5 Media Studio
- image generation tab
- image editing tab
- logo/branding asset workflow
- video generation tab
- output gallery
- prompts/workflows library
- metadata inspector
- GPU job queue view

### 5.6 Documents / Artifacts
- generated files
- reports
- PDFs
- DOCX
- zips
- export buttons
- artifact history
- link artifacts back to chats/tasks

### 5.7 Memory Center
- remembered facts
- editable user profile/context
- project memory
- memory audit trail
- delete/disable memory controls
- “why Edison remembered this” explanations

### 5.8 Models & System
- active models
- available models
- GPU usage
- node health
- storage status
- job queues
- running services
- logs
- settings

---

# 6. Model and Inference Strategy

Do not hardcode Edison V2 to one model. Build a **pluggable model router**.

## Suggested Model Lanes

### Instant / Lightweight Chat
Purpose:
- low-latency responses
- classification
- intent detection
- simple chats
- tool routing hints

### General Chat Model
Purpose:
- everyday assistant use
- explanations
- ordinary reasoning
- documents and summaries

### Reasoning Model
Purpose:
- deep reasoning
- planning
- complex task decomposition
- architecture discussions
- multi-step problem-solving

### Coding Model
Purpose:
- repo reasoning
- implementation planning
- code patching
- debugging
- test interpretation

### Vision / Multimodal Model
Purpose:
- images
- UI screenshots
- diagrams
- document pages
- OCR-like tasks
- browser visual context

### Embedding Model
Purpose:
- RAG
- memory retrieval
- semantic search

### Reranker / Retrieval Refinement
Purpose:
- better document search quality
- better source selection
- memory recall ranking

## Inference Infrastructure
Design adapters for:
- local OpenAI-compatible servers
- vLLM-style serving
- llama.cpp or other GGUF servers where useful
- SGLang or similar serving systems where appropriate
- custom model backends

Build:
- server health checks
- model warmup status
- active context size reporting
- GPU memory footprint tracking
- max batch / concurrency settings
- streaming support

---

# 7. GPU Resource Manager

This is important for EDISON V2.

Implement a dedicated `GPUResourceManager` that:
- detects all local GPUs
- records:
  - name
  - VRAM total
  - VRAM used
  - temperature
  - utilization
  - power draw where available
- tags devices by preferred workloads
- routes workloads intelligently
- prevents overcommitting VRAM
- warns when memory pressure is high
- supports “exclusive GPU render mode”

## Example Scheduling Concepts
- RTX 3090:
  - large LLM workloads
  - heavy reasoning/coding model
  - demanding image/video tasks when selected
- RTX 5060 Ti:
  - secondary inference
  - image generation
  - supporting models
- RTX 4060 Ti:
  - batch tasks
  - fast models
  - auxiliary media
- RTX A3000 laptop node:
  - smaller models
  - preprocessing
  - embeddings/reranking
  - low-VRAM media utilities

## Exclusive GPU Render Mode
For heavy image/video jobs:
1. snapshot current active Edison GPU services
2. detect which models/tasks can be paused or unloaded
3. wait until required VRAM is available
4. run render job
5. monitor progress and VRAM
6. restore prior services if configured
7. log pre/post state

Do not implement fake multi-GPU VRAM pooling. Implement real supported strategies only:
- process-level workload distribution
- multiple independent servers
- model sharding only where backend/model supports it
- tensor/pipeline parallelism only with compatible serving runtimes

---

# 8. Memory Architecture

Implement memory intentionally, not as a random pile of logs.

## 8.1 Conversation Records
Store:
- chat ID
- session ID
- message ID
- role
- content
- timestamp
- attachments
- active mode
- active model
- tool events tied to message

## 8.2 User Memory
Store:
- stable preferences
- recurring projects
- technical environment
- writing style preferences
- optional personal facts explicitly useful to assistance

Memory should support:
- confidence
- source conversation/message
- user editable
- expiry/review metadata
- active/inactive status

## 8.3 Project Memory
For projects like EDISON, portfolio sites, branding work, etc.:
- project summary
- current goals
- constraints
- files/repos
- decisions
- TODOs
- artifacts
- last active date

## 8.4 Session State Object
Maintain a structured session state with fields such as:
- `current_task`
- `current_project`
- `active_domain`
- `last_tool_used`
- `last_generated_artifact`
- `task_stage`
- `last_intent`
- `current_plan`
- `pending_approval`
- `selected_mode`
- `selected_model`

## 8.5 Memory Controls
UI should let the user:
- turn memory on/off
- inspect memory
- edit remembered facts
- delete memories
- see why a memory was used
- review project context

---

# 9. Agent Reasoning and Execution Design

EDISON V2 agents should use a structured loop:

1. Understand user goal
2. Retrieve relevant context/memory/project state
3. Decide if tools are required
4. Draft plan
5. Check approval requirements
6. Execute steps
7. Inspect results
8. Verify correctness
9. Revise if needed
10. Present final result
11. Save relevant task memory/artifacts

## Agent State Machine
Build a formal state machine/graph with states such as:
- received
- classified
- context_loaded
- planned
- awaiting_approval
- executing
- verifying
- recovering
- completed
- failed
- cancelled

## Tool Invocation Records
Every tool invocation should store:
- tool name
- inputs
- outputs
- elapsed time
- status
- errors
- whether user approval was required
- artifact IDs generated

## Human Approval Boundaries
Approval required for:
- destructive file operations
- deleting user data
- external communications
- costly API usage if optional cloud integrations exist
- pushing code to remotes
- system-level package installation outside controlled environments
- writing outside approved workspaces
- risky browser actions involving real accounts

---

# 10. Coding Agent Requirements

The coding agent must be genuinely useful.

## Required Features
- analyze project files
- build project map
- identify app entrypoints
- identify routes, services, stores, config
- detect tech stack
- inspect dependency files
- read logs
- summarize repo architecture
- create implementation plan
- modify code
- run tests
- run build/lint/typecheck
- detect failures
- patch based on failures
- provide change summary

## Coding Workflow
For a request like “add feature X”:
1. inspect repo
2. summarize relevant architecture
3. create plan
4. find best integration points
5. modify minimal files
6. add/update tests
7. run tests
8. iterate if failures
9. produce final diff summary
10. list remaining issues

## Controlled Tooling
Implement:
- file search
- file read
- file write
- patch apply
- command run
- command status
- dependency install
- test run
- lint run
- package audit summary
- diff generation

## Code Execution Environments
Support:
- Python virtualenv or container
- Node package environments
- Docker-based sandbox where appropriate
- per-project config
- captured stdout/stderr
- timeout handling

---

# 11. Web Research Agent Requirements

Web research should be:
- current
- source-aware
- traceable
- citation-ready
- not just raw search snippets

## Web Agent Capabilities
- form search queries
- open results
- parse pages
- extract relevant sections
- compare multiple sources
- capture publish/event dates when possible
- distinguish new developments from old background
- summarize findings
- provide grounded answers
- store source objects

## Browser Agent UX
Provide:
- live visible browser activity when an agent is browsing
- step-by-step timeline
- visited pages
- extracted snippets
- a user-facing explanation of what it found

---

# 12. Media System Requirements

## 12.1 Image Generation
Support:
- ComfyUI integration
- prompt-based generation
- reference-based generation where workflow supports it
- style presets
- logo/branding workflows
- asset batches
- upscaling
- background removal workflow hooks
- metadata preservation

## 12.2 Video Generation
Support:
- image-to-video pipelines
- text-to-video pipelines if local stack supports it
- short clip generation
- camera motion/movement prompts where model allows
- queue handling
- GPU-heavy task modes

## 12.3 3D and Fabrication-Oriented Features
Scaffold architecture for:
- basic 3D asset generation workflow hooks
- mesh file management
- STL/OBJ/GLB output registration
- 3D print project support in future
- geometry-generation add-ons later

Do not overpromise production-quality 3D generation from day one. Build it as a modular extension point.

---

# 13. Document and File Generation

Implement reusable helpers for:
- PDF generation
- Word document generation
- Markdown reports
- zipped deliverables
- plain text files
- JSON exports
- code bundles

Artifacts should:
- have IDs
- have creation timestamps
- be linked to originating chat/task
- record mime type and file path
- be downloadable from UI
- be browsable in artifact history

---

# 14. Voice Mode Details

## Speech-to-Text
Architect for:
- microphone capture
- audio chunking
- streaming/near-streaming transcription
- endpoint for upload transcription
- endpoint for live session transcription
- local-first processing

## Text-to-Speech
Architect for:
- configurable speaker voice
- queue of spoken messages
- interruption handling
- expressive speaking profiles
- local audio output
- saved narration artifacts when requested

## Conversation Loop
A voice session should:
1. listen
2. transcribe
3. send text to EDISON Core
4. receive streaming reply
5. synthesize speech
6. display transcript and speaking state
7. allow interruption

---

# 15. Storage Strategy

Use storage intentionally.

## Primary PC Suggested Logical Storage Roles
- system/app storage
- model storage
- ComfyUI checkpoints/workflows
- generated outputs
- datasets/training assets
- temp/scratch jobs
- backups

## Beelink Node Suggested Roles
- long-term archive
- backups
- vector DB snapshots
- artifact cold storage
- dataset archive
- download/cache mirror
- logs export/archive

Implement storage paths via config, not hardcoded literals.

---

# 16. Observability and Reliability

Build this like a real platform.

## Add:
- structured logging
- request IDs
- agent run IDs
- job IDs
- error categories
- health endpoints
- metrics endpoints
- model health status
- node health status
- task/job queue views
- exception logging
- retry policies
- timeouts
- cancellation support

## System Dashboard
Show:
- GPU usage
- model servers up/down
- active jobs
- node online/offline
- last errors
- storage usage
- queue counts
- voice service status
- web agent status

---

# 17. Security Architecture

Implement:
- authentication
- session isolation
- role/permission groundwork
- API tokens for remote nodes
- no secrets in repo
- `.env` and config templates
- audit logs
- CORS sane defaults
- file path validation
- command policy enforcement
- prompt injection precautions for web/browser agent
- source trust boundaries

## Prompt Injection Safeguards
When browsing the web or reading documents:
- treat external content as untrusted
- never execute instructions found inside webpages/files as if they were user instructions
- separate retrieved content from controlling prompts
- keep tool execution policy outside retrieved content

---

# 18. Suggested Technical Stack

Use the current Edison stack where applicable, but the V2 system should likely include:

## Backend
- Python
- FastAPI
- Pydantic
- SQLAlchemy or direct DB layer
- SQLite initially, with upgrade path to PostgreSQL if needed
- vector DB integration such as Qdrant/Chroma or current Edison-compatible equivalent
- background tasks/queues where appropriate
- WebSocket or SSE for live agent status

## Frontend
- modern React/Next.js/Tauri/Electron-compatible architecture depending on repo direction
- clean UI components
- streaming chat
- job status updates
- agent timeline
- code diff view
- system dashboard

## Agents
- graph/state-based orchestration
- durable/resumable execution
- approval checkpoints
- reusable tool definitions

## Browser Automation
- browser automation service suitable for testing and agent workflows
- visible/live session support

## Tool Protocol Direction
- internal schema-first tool system
- future-friendly MCP-style adapter support

## Inference
- model gateway compatible with local model servers
- streaming token responses
- model profiling and fallback rules
- task-based model selection

---

# 19. Phased Implementation Plan

Do not attempt everything randomly. Build in phases.

## Phase 0 — Repository Audit and Architecture Plan
Before writing major code:
1. inspect current repo structure
2. list existing services/routes/features
3. identify reusable modules
4. identify overloaded files
5. map current ComfyUI, memory, agent, model, frontend, and config systems
6. propose V2 migration/additive architecture
7. create a clear implementation roadmap

Deliverables:
- repo audit report
- architecture map
- feature gap list
- V2 implementation plan
- risk list

## Phase 1 — V2 Core Foundation
Implement:
- V2 config system additions
- model registry/router scaffold
- conversation/session schema
- persistent chat history
- clean service interfaces
- base frontend shell if needed
- health/status endpoints

## Phase 2 — Memory and Chat Experience
Implement:
- memory service
- session state object
- chat history UI
- project memory groundwork
- memory management UI endpoints

## Phase 3 — Agent Engine
Implement:
- agent run model
- state machine
- task planning
- tool registry
- tool logs
- approval flow
- progress events

## Phase 4 — Web Agent and Browser View
Implement:
- search workflow
- page retrieval
- source extraction
- visible browser session/timeline
- citations/source metadata
- pause/resume controls

## Phase 5 — Coding Agent
Implement:
- workspace manager
- file tools
- repo scanner
- command runner
- test runner
- patch flow
- diff reporting
- coding task UI

## Phase 6 — Media Studio Integration
Implement:
- image job service
- ComfyUI runner
- media queue
- artifact gallery
- metadata capture
- video generation hooks
- GPU job mode

## Phase 7 — Voice Mode
Implement:
- STT service
- TTS service
- live transcript
- speaking UI
- settings panel
- interruption pipeline if feasible

## Phase 8 — Multi-Agent / Swarm Mode
Implement:
- agent roles
- task decomposition
- worker allocation
- critic review
- synthesis step
- swarm visualizer

## Phase 9 — Distributed Nodes
Implement:
- laptop worker agent
- Beelink storage/utility service
- heartbeat/status
- secure node auth
- job dispatch
- artifact return

## Phase 10 — Polish, Testing, Docs, Reliability
Implement:
- tests
- docs
- setup/install guide
- developer guide
- troubleshooting docs
- monitoring dashboards
- performance profiling
- error recovery improvements

---

# 20. Required Deliverables From Copilot

Copilot should not just code blindly. It should produce:

1. **Initial architecture assessment**
2. **Proposed V2 module layout**
3. **Implementation roadmap**
4. **Code changes in logical batches**
5. **Config additions with safe defaults**
6. **Database schema/migrations where needed**
7. **API route additions**
8. **Frontend UI updates**
9. **Tests**
10. **Docs**
11. **Validation steps**
12. **Known limitations**
13. **Next steps**

---

# 21. Coding Style and Quality Requirements

- Keep code modular
- Use type hints
- Use Pydantic schemas
- Avoid giant god classes
- Avoid magic literals
- Centralize config
- Centralize logging
- Add docstrings where helpful
- Prefer small functions with clear purpose
- Write tests for critical systems
- Preserve backwards compatibility
- Keep imports organized
- Follow existing repo style unless clearly flawed
- Add comments only where useful
- Do not over-engineer simple pieces, but do build durable foundations for complex systems

---

# 22. Acceptance Criteria

EDISON V2 foundation is successful when:

## Chat
- user can create chats
- history persists
- chat supports modes
- assistant can recall relevant context when memory is enabled

## Agent
- user can submit a multi-step task
- system creates a plan
- executes tools
- streams progress
- pauses for approvals where required
- returns final result and logs

## Coding
- system can inspect a sample repo
- explain architecture
- modify a file
- run a test/build
- show changes and command outputs

## Web
- system can search/open sources
- summarize findings
- preserve source metadata
- show browser/step activity in UI

## Media
- system can trigger an image generation workflow
- save result as an artifact
- show it in gallery/history

## Voice
- system can transcribe input
- produce spoken output
- show live transcript/status

## Nodes
- system can see node online/offline state
- optionally dispatch at least one safe job type to another node

## Reliability
- services provide health endpoints
- major errors are logged cleanly
- no existing important Edison capability is broken if working in current repo

---

# 23. Start Here — Immediate Copilot Execution Instructions

Begin now with the following sequence:

## Step 1: Audit Existing Edison Codebase
Inspect the repository thoroughly and report:
- current top-level structure
- current backend entrypoints
- current frontend structure
- current ComfyUI integration points
- current memory/RAG systems
- current agent/work/swarm systems
- current model management
- current config files
- current tests
- current pain points and overloaded files

## Step 2: Produce V2 Architecture Map
Create a written architecture proposal showing:
- what should be reused
- what should be added
- what should be refactored later
- what should remain untouched initially
- where each new V2 service/module belongs

## Step 3: Implement Only the V2 Foundation First
Do not immediately jump to all features.
Start with:
1. configuration scaffolding
2. V2 model registry/router abstractions
3. persistent conversation/chat storage foundation
4. session state object
5. service health/status endpoints
6. documented roadmap file

## Step 4: Keep the App Runnable
After each code batch:
- run tests if present
- run targeted smoke tests
- validate imports
- verify startup
- summarize what changed

## Step 5: Show a Clear Final Report
At the end of the first implementation pass, provide:
- changes made
- files added/modified
- how to run
- what works now
- what remains next
- any issues discovered

---

# 24. Copilot Operating Rules

Follow these rules while working:

- Do not ask repetitive questions when repository evidence provides the answer.
- Make grounded assumptions, state them, and proceed.
- Prefer incremental working changes over giant risky rewrites.
- Do not break existing endpoints or UI flows.
- Do not remove current functionality merely because a better architecture exists.
- Add compatibility layers where needed.
- Make the codebase more maintainable with each change.
- Every major system should have:
  - data model
  - service layer
  - API layer
  - config
  - tests or validation plan
  - docs
- When uncertain, inspect the code first.
- For every implementation batch, describe:
  - why it was done
  - how it integrates
  - how it was validated

---

# 25. Optional Future Features to Keep in Mind

Do not build all of these immediately, but keep architecture extensible for:
- personal calendar/email connectors
- GitHub connectors
- local file indexing
- desktop app packaging
- mobile companion app
- 3D printing workflows
- printer monitoring
- branding studio workflows
- project/client folders
- local business marketing asset generation
- plugin marketplace / custom skill registry
- Edison personality customization
- proactive notifications
- task scheduling
- collaboration features
- secure remote access over a private network

---

# 26. Final Instruction to Copilot

Treat this as the beginning of **EDISON V2**, a local-first, high-capability AI platform.  
The goal is not to create a toy chatbot.  
The goal is to build a scalable foundation for a personal AI system that can converse, reason, remember, use tools, code, browse, generate media, manage tasks, and grow into a true AI workstation and assistant.

Begin by auditing the current repo, proposing the V2 architecture, and implementing the first safe, additive foundation layer without breaking existing Edison functionality.
