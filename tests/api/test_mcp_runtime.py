import json

from edison_core.database import SQLiteDatabase
from edison_core.mcp.media import create_server as create_media_server
from edison_core.mcp.organizer import create_server as create_organizer_server
from edison_core.mcp.knowledge import create_server as create_knowledge_server
from edison_core.mcp.workspace import create_server as create_workspace_server
from edison_core.schemas import MediaBackendStatus
from edison_core.services.generation_store import GenerationStore
from edison_core.schemas import KnowledgeIngestTextRequest
from edison_core.services.knowledge_store import KnowledgeStore
from edison_core.services.personal_workspace import PersonalWorkspaceStore
from edison_core.services.workspace_tools import WorkspaceTools


def test_mcp_initialize_and_list_tools(tmp_path):
    store = KnowledgeStore(SQLiteDatabase(tmp_path / "edison.sqlite3"), tmp_path)
    store.initialize()
    server = create_knowledge_server(store)

    initialized = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    tools = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

    assert initialized["result"]["protocolVersion"] == "2025-06-18"
    assert initialized["result"]["capabilities"]["tools"] == {}
    assert {tool["name"] for tool in tools["result"]["tools"]} >= {"knowledge.status", "knowledge.search"}


def test_mcp_calls_knowledge_search_tool(tmp_path):
    store = KnowledgeStore(SQLiteDatabase(tmp_path / "edison.sqlite3"), tmp_path)
    store.initialize()
    store.ingest_text(
        KnowledgeIngestTextRequest(
            title="Edison Hardware",
            text="Hailo object detection and Brio camera feeds belong in the hardware command center.",
        )
    )
    server = create_knowledge_server(store)

    response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "knowledge.search", "arguments": {"query": "Hailo camera"}},
        }
    )
    content = json.loads(response["result"]["content"][0]["text"])

    assert response["result"]["isError"] is False
    assert content[0]["source_title"] == "Edison Hardware"


def test_mcp_calls_workspace_read_tool(tmp_path):
    (tmp_path / "README.md").write_text("# Edison\n\nWorkspace MCP read test.\n", encoding="utf-8")
    server = create_workspace_server(WorkspaceTools(tmp_path))

    response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "workspace.read", "arguments": {"path": "README.md"}},
        }
    )
    content = json.loads(response["result"]["content"][0]["text"])

    assert content["path"] == "README.md"
    assert "Workspace MCP read test" in content["content"]


def test_mcp_media_create_job_records_setup_required_when_backend_is_not_ready(tmp_path):
    store = GenerationStore(SQLiteDatabase(tmp_path / "edison.sqlite3"))
    store.initialize()
    server = create_media_server(
        store=store,
        comfyui=_FakeMediaBackend("ComfyUI needs setup"),
        invokeai=_FakeMediaBackend("InvokeAI needs setup"),
        wan22=_FakeMediaBackend("WAN needs setup"),
        modly=_FakeMediaBackend("Modly needs setup"),
    )

    response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "media.create_job",
                "arguments": {"title": "Product render", "prompt": "small toy robot", "job_type": "image"},
            },
        }
    )
    content = json.loads(response["result"]["content"][0]["text"])

    assert content["status"] == "setup_required"
    assert content["backend"] == "comfyui"
    assert store.job_counts()["setup_required"] == 1


def test_mcp_organizer_creates_business_brief_and_ingests_document(tmp_path):
    database = SQLiteDatabase(tmp_path / "edison.sqlite3")
    personal = PersonalWorkspaceStore(database)
    personal.initialize()
    knowledge = KnowledgeStore(database, tmp_path)
    knowledge.initialize()
    server = create_organizer_server(personal, knowledge)

    brief_response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "business.brief.create",
                "arguments": {
                    "title": "ToyBox3D launch",
                    "customer": "Shopify buyers",
                    "offer": "Printed articulated toys",
                    "next_action": "Map products to printers",
                },
            },
        }
    )
    brief = json.loads(brief_response["result"]["content"][0]["text"])
    document_id = brief["document"]["id"]

    ingest_response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "documents.ingest", "arguments": {"document_id": document_id}},
        }
    )
    ingest = json.loads(ingest_response["result"]["content"][0]["text"])

    assert brief["task"]["title"] == "Map products to printers"
    assert "Printed articulated toys" in brief["document"]["content"]
    assert ingest["knowledge_source"]["kind"] == "text"
    assert ingest["knowledge_source"]["metadata"]["source"] == "personal_document"


class _FakeMediaBackend:
    base_url = None

    def __init__(self, detail: str) -> None:
        self.detail = detail

    def status(self) -> MediaBackendStatus:
        return MediaBackendStatus(status="setup_required", detail=self.detail)
