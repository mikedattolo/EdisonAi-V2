# Odysseus Integration Map

Source reviewed: `pewdiepie-archdaemon/odysseus` at commit `04fd9633948e0db9b086dbd7c001bdef8b632597`.

License: MIT. Odysseus also carries separate acknowledgements for dependencies and adapted components, so Edison should port features intentionally and keep attribution when borrowing implementation details.

## Feature Inventory

Odysseus is a self-hosted AI workspace with these major feature surfaces:

- Chat and agents across local/API models, MCP tools, files, shell, skills, and memory.
- Deep Research with multi-step source gathering, synthesis, reports, and source inspection.
- Compare mode for side-by-side model/search/research runs.
- Document editor, notes, tasks, calendar, email, image editor, gallery, file uploads, presets, sessions, themes, and 2FA.
- RAG and memory backed by ChromaDB/fastembed with vector plus keyword retrieval.
- Search providers including SearXNG, DuckDuckGo, Brave, and API-driven providers.
- Cookbook-style hardware scan, model recommendation, download, and serving helpers.

## Edison Mapping

Already present in Edison:

- Local model lanes through the model registry and OpenAI-compatible routing.
- Streaming chat and persisted conversations.
- Media job orchestration with ComfyUI, InvokeAI, Wan, and Modly delivery into chat.
- Workspace file browsing, search, patch preview, command execution, and code-focused context.
- Basic knowledge ingestion for text, URLs, Wikipedia, local files, and presets.

Added in this integration pass:

- A real Memory Center in the web UI for source status, RAG search, URL/Wikipedia/local/text ingestion, presets, and source library browsing.
- Chat-level RAG controls for enabling knowledge retrieval, overriding the search query, and choosing match count.
- Assistant message source rendering so knowledge matches show as collapsible, reload-safe source panels instead of invisible metadata.
- Richer knowledge metadata in chat responses, including source URI, path, score, and snippet.
- Better local keyword ranking with phrase/title bonuses and stored chunk paths.
- A Compare workspace that sends one prompt to multiple ready chat model lanes in parallel, streams answers side-by-side, supports blind labels, optional RAG, synthesizes winners/misses, and links each result back to its saved chat.
- A Research workspace that turns a topic into a streaming source-aware report, supports depth selection and RAG match limits, and links the report back to its saved chat.
- Persistent organizer APIs and UI for tasks, notes, and calendar-style dated items.
- Persistent document drafts with editing, saving, and one-click ingestion into Edison knowledge.
- Search comparison across the knowledge base, workspace index, and saved documents.
- Chat and agent requests can include personal organizer/document context in model metadata and prompts.

Next high-value ports:

- Vector retrieval using the existing `local-embeddings` lane, with keyword fallback.
- File upload ingestion for PDFs, Office docs, CSVs, and images with OCR/VLM summaries.
- Multi-step Deep Research jobs with progress events, source library persistence, report export, and chat spinoff.
- External search provider comparison and synthesis.
- Deeper agent actions over notes/tasks/calendar primitives, including automatic task creation and status changes.
- Cookbook hardware-aware model recommendations linked to Edison’s installed GPUs and storage layout.

## Porting Constraints

Edison is a FastAPI plus React application, while Odysseus is a larger mostly static JS/FastAPI workspace. Direct file copying would create duplicated frameworks and incompatible state management. The safer path is to port the behaviors and selectively adapt small implementation ideas while keeping Edison’s existing API boundaries.
