from __future__ import annotations

from edison_core.config import load_settings
from edison_core.mcp.runtime import MCPServer, MCPTool, integer_schema, object_schema, string_schema
from edison_core.schemas import WorkspaceIndexSearchRequest, WorkspaceSearchRequest
from edison_core.services.workspace_tools import WorkspaceTools


def create_server(workspace: WorkspaceTools | None = None) -> MCPServer:
    tools = workspace or _default_workspace()
    return MCPServer(
        name="edison-workspace",
        version="0.1.0",
        tools=[
            MCPTool(
                name="workspace.summary",
                description="Summarize the current Edison workspace root.",
                input_schema=object_schema(),
                handler=lambda _: tools.summarize(),
            ),
            MCPTool(
                name="workspace.search",
                description="Search workspace paths and file contents.",
                input_schema=object_schema(
                    {
                        "query": string_schema("Search query"),
                        "max_results": integer_schema("Maximum matches to return", 25, 1, 100),
                    },
                    ["query"],
                ),
                handler=lambda args: tools.search(
                    WorkspaceSearchRequest(
                        query=str(args["query"]),
                        max_results=int(args.get("max_results", 25)),
                    )
                ),
            ),
            MCPTool(
                name="workspace.index_search",
                description="Search Edison's lightweight workspace semantic index.",
                input_schema=object_schema(
                    {
                        "query": string_schema("Search query"),
                        "max_results": integer_schema("Maximum matches to return", 8, 1, 50),
                    },
                    ["query"],
                ),
                handler=lambda args: tools.search_index(
                    WorkspaceIndexSearchRequest(
                        query=str(args["query"]),
                        max_results=int(args.get("max_results", 8)),
                    )
                ),
            ),
            MCPTool(
                name="workspace.read",
                description="Read a text file from the Edison workspace root.",
                input_schema=object_schema(
                    {"path": string_schema("Workspace-relative file path")},
                    ["path"],
                ),
                handler=lambda args: tools.read_file(str(args["path"])),
            ),
        ],
    )


def _default_workspace() -> WorkspaceTools:
    settings = load_settings()
    return WorkspaceTools(settings.workspace_roots[0])


def main() -> None:
    create_server().serve_stdio()


if __name__ == "__main__":
    main()
