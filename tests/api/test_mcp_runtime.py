import json

from edison_core.database import SQLiteDatabase
from edison_core.mcp.knowledge import create_server as create_knowledge_server
from edison_core.mcp.workspace import create_server as create_workspace_server
from edison_core.schemas import KnowledgeIngestTextRequest
from edison_core.services.knowledge_store import KnowledgeStore
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
