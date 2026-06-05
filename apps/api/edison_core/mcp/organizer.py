from __future__ import annotations

from typing import Any

from edison_core.config import load_settings
from edison_core.database import SQLiteDatabase
from edison_core.mcp.runtime import MCPServer, MCPTool, integer_schema, object_schema, string_schema
from edison_core.schemas import (
    DocumentCreate,
    DocumentFormat,
    KnowledgeIngestTextRequest,
    OrganizerItemCreate,
    OrganizerItemUpdate,
    OrganizerKind,
    OrganizerStatus,
)
from edison_core.services.knowledge_store import KnowledgeStore
from edison_core.services.personal_workspace import PersonalWorkspaceStore


def create_server(
    store: PersonalWorkspaceStore | None = None,
    knowledge: KnowledgeStore | None = None,
) -> MCPServer:
    workspace = store or _default_store()
    knowledge_store = knowledge or _default_knowledge()
    return MCPServer(
        name="edison-organizer",
        version="0.1.0",
        tools=[
            MCPTool(
                name="organizer.list",
                description="List Edison tasks, notes, or calendar items.",
                input_schema=object_schema(
                    {
                        "kind": string_schema("Optional kind: task, note, or calendar", ""),
                        "status": string_schema("Optional status: active, done, archived, cancelled", ""),
                        "limit": integer_schema("Maximum items to return", 50, 1, 200),
                    }
                ),
                handler=lambda args: workspace.list_items(
                    kind=_optional_kind(args.get("kind")),
                    status=_optional_status(args.get("status")),
                    limit=int(args.get("limit", 50)),
                ),
            ),
            MCPTool(
                name="organizer.create",
                description="Create an Edison task, note, or calendar item.",
                input_schema=object_schema(
                    {
                        "kind": string_schema("Kind: task, note, or calendar", "task"),
                        "title": string_schema("Item title"),
                        "body": string_schema("Item body or notes", ""),
                        "status": string_schema("Status: active, done, archived, cancelled", "active"),
                        "tags": _tags_schema(),
                    },
                    ["title"],
                ),
                handler=lambda args: workspace.create_item(
                    OrganizerItemCreate(
                        kind=OrganizerKind(str(args.get("kind") or "task")),
                        title=str(args["title"]),
                        body=str(args.get("body") or ""),
                        status=OrganizerStatus(str(args.get("status") or "active")),
                        tags=_tags(args.get("tags")),
                    )
                ),
            ),
            MCPTool(
                name="organizer.update",
                description="Update an Edison organizer item.",
                input_schema=object_schema(
                    {
                        "item_id": string_schema("Organizer item id"),
                        "title": string_schema("Optional new title", ""),
                        "body": string_schema("Optional new body", ""),
                        "status": string_schema("Optional status: active, done, archived, cancelled", ""),
                        "tags": _tags_schema(),
                    },
                    ["item_id"],
                ),
                handler=lambda args: workspace.update_item(str(args["item_id"]), _item_update(args)),
            ),
            MCPTool(
                name="documents.list",
                description="List recent Edison personal documents.",
                input_schema=object_schema({"limit": integer_schema("Maximum documents to return", 50, 1, 200)}),
                handler=lambda args: workspace.list_documents(limit=int(args.get("limit", 50))),
            ),
            MCPTool(
                name="documents.search",
                description="Search Edison personal documents.",
                input_schema=object_schema(
                    {
                        "query": string_schema("Search query"),
                        "max_results": integer_schema("Maximum matches to return", 8, 1, 50),
                    },
                    ["query"],
                ),
                handler=lambda args: workspace.search_documents(
                    str(args["query"]),
                    max_results=int(args.get("max_results", 8)),
                ),
            ),
            MCPTool(
                name="documents.create",
                description="Create a Markdown or text document in Edison.",
                input_schema=object_schema(
                    {
                        "title": string_schema("Document title"),
                        "content": string_schema("Document content", ""),
                        "format": string_schema("Document format: markdown or text", "markdown"),
                        "tags": _tags_schema(),
                    },
                    ["title"],
                ),
                handler=lambda args: workspace.create_document(
                    DocumentCreate(
                        title=str(args["title"]),
                        content=str(args.get("content") or ""),
                        format=DocumentFormat(str(args.get("format") or "markdown")),
                        tags=_tags(args.get("tags")),
                    )
                ),
            ),
            MCPTool(
                name="documents.ingest",
                description="Ingest an Edison personal document into the local knowledge base.",
                input_schema=object_schema({"document_id": string_schema("Document id")}, ["document_id"]),
                handler=lambda args: _ingest_document(str(args["document_id"]), workspace, knowledge_store),
            ),
            MCPTool(
                name="business.brief.create",
                description="Create a practical business-management brief plus a follow-up task.",
                input_schema=object_schema(
                    {
                        "title": string_schema("Business initiative title"),
                        "customer": string_schema("Target customer or buyer", ""),
                        "offer": string_schema("Product, service, or offer", ""),
                        "channels": string_schema("Sales/marketing channels", ""),
                        "operations": string_schema("Operations, fulfillment, or support notes", ""),
                        "success_metrics": string_schema("Metrics that define success", ""),
                        "next_action": string_schema("Next concrete action Edison should track", ""),
                    },
                    ["title"],
                ),
                handler=lambda args: _create_business_brief(args, workspace),
            ),
            MCPTool(
                name="product.design_brief.create",
                description="Create a product-design brief plus a follow-up implementation task.",
                input_schema=object_schema(
                    {
                        "title": string_schema("Product or feature title"),
                        "problem": string_schema("Problem to solve", ""),
                        "users": string_schema("Primary users or buyers", ""),
                        "workflow": string_schema("Key user workflow", ""),
                        "assets": string_schema("Visual, brand, CAD, print, or content assets needed", ""),
                        "constraints": string_schema("Technical, brand, legal, or production constraints", ""),
                        "success_metrics": string_schema("Metrics that define success", ""),
                        "next_action": string_schema("Next concrete action Edison should track", ""),
                    },
                    ["title"],
                ),
                handler=lambda args: _create_product_design_brief(args, workspace),
            ),
        ],
    )


def _create_business_brief(args: dict[str, Any], store: PersonalWorkspaceStore) -> dict[str, Any]:
    title = str(args["title"])
    next_action = _text(args.get("next_action")) or f"Review business plan for {title}"
    document = store.create_document(
        DocumentCreate(
            title=f"Business brief: {title}",
            content=_business_markdown(args),
            format=DocumentFormat.MARKDOWN,
            tags=["business", "brief"],
            metadata={"source": "mcp", "template": "business.brief"},
        )
    )
    task = store.create_item(
        OrganizerItemCreate(
            kind=OrganizerKind.TASK,
            title=next_action,
            body=f"Linked Edison document: {document.id}",
            tags=["business", "next-action"],
            metadata={"document_id": document.id, "template": "business.brief"},
        )
    )
    return {"document": document, "task": task}


def _create_product_design_brief(args: dict[str, Any], store: PersonalWorkspaceStore) -> dict[str, Any]:
    title = str(args["title"])
    next_action = _text(args.get("next_action")) or f"Turn {title} into a scoped product-design plan"
    document = store.create_document(
        DocumentCreate(
            title=f"Product design brief: {title}",
            content=_product_design_markdown(args),
            format=DocumentFormat.MARKDOWN,
            tags=["product-design", "brief"],
            metadata={"source": "mcp", "template": "product.design_brief"},
        )
    )
    task = store.create_item(
        OrganizerItemCreate(
            kind=OrganizerKind.TASK,
            title=next_action,
            body=f"Linked Edison document: {document.id}",
            tags=["product-design", "next-action"],
            metadata={"document_id": document.id, "template": "product.design_brief"},
        )
    )
    return {"document": document, "task": task}


def _ingest_document(document_id: str, store: PersonalWorkspaceStore, knowledge: KnowledgeStore) -> dict[str, Any]:
    document = store.get_document(document_id)
    source = knowledge.ingest_text(
        KnowledgeIngestTextRequest(
            title=f"Personal document: {document.title}",
            text=document.content or document.title,
            uri=f"edison:personal-doc/{document.id}",
            metadata={"source": "personal_document", "document_id": document.id, "tags": document.tags},
        )
    )
    return {"document": document, "knowledge_source": source}


def _item_update(args: dict[str, Any]) -> OrganizerItemUpdate:
    fields: dict[str, Any] = {}
    if _text(args.get("title")):
        fields["title"] = _text(args.get("title"))
    if _text(args.get("body")) is not None:
        fields["body"] = _text(args.get("body"))
    if _text(args.get("status")):
        fields["status"] = OrganizerStatus(_text(args.get("status")))
    if "tags" in args:
        fields["tags"] = _tags(args.get("tags"))
    return OrganizerItemUpdate(**fields)


def _business_markdown(args: dict[str, Any]) -> str:
    return _markdown(
        f"# Business Brief: {args['title']}",
        {
            "Target Customer": _text(args.get("customer")),
            "Offer": _text(args.get("offer")),
            "Channels": _text(args.get("channels")),
            "Operations": _text(args.get("operations")),
            "Success Metrics": _text(args.get("success_metrics")),
            "Next Action": _text(args.get("next_action")),
        },
    )


def _product_design_markdown(args: dict[str, Any]) -> str:
    return _markdown(
        f"# Product Design Brief: {args['title']}",
        {
            "Problem": _text(args.get("problem")),
            "Users": _text(args.get("users")),
            "Core Workflow": _text(args.get("workflow")),
            "Assets Needed": _text(args.get("assets")),
            "Constraints": _text(args.get("constraints")),
            "Success Metrics": _text(args.get("success_metrics")),
            "Next Action": _text(args.get("next_action")),
        },
    )


def _markdown(title: str, sections: dict[str, str | None]) -> str:
    blocks = [title]
    for heading, body in sections.items():
        blocks.append(f"## {heading}\n{body or 'TBD'}")
    return "\n\n".join(blocks) + "\n"


def _optional_kind(value: Any) -> OrganizerKind | None:
    text = _text(value)
    return OrganizerKind(text) if text else None


def _optional_status(value: Any) -> OrganizerStatus | None:
    text = _text(value)
    return OrganizerStatus(text) if text else None


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:16]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()][:16]
    return []


def _tags_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "description": "Tags to attach",
        "items": {"type": "string"},
        "default": [],
    }


def _default_store() -> PersonalWorkspaceStore:
    settings = load_settings()
    store = PersonalWorkspaceStore(SQLiteDatabase(settings.database_path))
    store.initialize()
    return store


def _default_knowledge() -> KnowledgeStore:
    settings = load_settings()
    store = KnowledgeStore(SQLiteDatabase(settings.database_path), settings.workspace_roots[0])
    store.initialize()
    return store


def main() -> None:
    create_server().serve_stdio()


if __name__ == "__main__":
    main()
