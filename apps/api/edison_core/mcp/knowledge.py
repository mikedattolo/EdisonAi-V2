from __future__ import annotations

from edison_core.config import load_settings
from edison_core.database import SQLiteDatabase
from edison_core.mcp.runtime import MCPServer, MCPTool, integer_schema, object_schema, string_schema
from edison_core.schemas import KnowledgeIngestTextRequest
from edison_core.services.knowledge_store import KnowledgeStore


def create_server(store: KnowledgeStore | None = None) -> MCPServer:
    knowledge = store or _default_store()
    return MCPServer(
        name="edison-knowledge",
        version="0.1.0",
        tools=[
            MCPTool(
                name="knowledge.status",
                description="Return Edison knowledge-base source and chunk counts.",
                input_schema=object_schema(),
                handler=lambda _: knowledge.status(),
            ),
            MCPTool(
                name="knowledge.search",
                description="Search Edison local RAG sources.",
                input_schema=object_schema(
                    {
                        "query": string_schema("Search query"),
                        "max_results": integer_schema("Maximum matches to return", 8, 1, 50),
                    },
                    ["query"],
                ),
                handler=lambda args: knowledge.search(
                    str(args["query"]),
                    max_results=int(args.get("max_results", 8)),
                ),
            ),
            MCPTool(
                name="knowledge.sources",
                description="List recently ingested Edison knowledge sources.",
                input_schema=object_schema(
                    {"limit": integer_schema("Maximum sources to return", 20, 1, 100)}
                ),
                handler=lambda args: knowledge.list_sources(limit=int(args.get("limit", 20))),
            ),
            MCPTool(
                name="knowledge.ingest_text",
                description="Ingest a short text source into Edison knowledge.",
                input_schema=object_schema(
                    {
                        "title": string_schema("Source title"),
                        "text": string_schema("Text content"),
                        "uri": string_schema("Optional URI", ""),
                    },
                    ["title", "text"],
                ),
                handler=lambda args: knowledge.ingest_text(
                    KnowledgeIngestTextRequest(
                        title=str(args["title"]),
                        text=str(args["text"]),
                        uri=str(args.get("uri") or "") or None,
                    )
                ),
            ),
        ],
    )


def _default_store() -> KnowledgeStore:
    settings = load_settings()
    store = KnowledgeStore(SQLiteDatabase(settings.database_path), settings.workspace_roots[0])
    store.initialize()
    return store


def main() -> None:
    create_server().serve_stdio()


if __name__ == "__main__":
    main()
