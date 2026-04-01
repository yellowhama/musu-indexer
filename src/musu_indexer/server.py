from mcp.server.fastmcp import FastMCP
from .core import sync_core, search_index, log_activity, find_project_root, get_recent, get_spy_context
from pathlib import Path

# Create the MCP Server instance
mcp = FastMCP("Musu Indexer MCP")

@mcp.tool()
async def get_spy_logs(window_keyword: str, limit: int = 5) -> str:
    """
    Retrieve recently captured raw text from an external window (mechanical logs).
    Use this to understand the current state of a chat or external tool.
    """
    project_root = find_project_root()
    try:
        results = get_spy_context(project_root, window_keyword, limit=limit)
        if not results:
            return f"No spy logs found for window matching: '{window_keyword}'."
        
        output = [f"Found {len(results)} recent snapshots for '{window_keyword}':"]
        for r in results:
            output.append(f"--- Timestamp: {r['timestamp']} ---\n{r['content']}\n")
        return "\n".join(output)
    except Exception as e:
        return f"Database error. Please ensure the 'spy' command is running. ({e})"

@mcp.tool()
async def sync_workspace(scope: str = "all") -> str:
    """
    Synchronize the local SQLite database with the current file system state.
    MUST run this if the database is outdated or files have been modified.
    Scope can be 'all', 'code', or 'doc'.
    """
    project_root = find_project_root()
    try:
        result = sync_core(project_root, scope=scope)
        return result
    except Exception as e:
        return f"Error syncing workspace: {e}"

@mcp.tool()
async def search_codebase(query: str, limit: int = 15, exclude: list[str] = None) -> str:
    """
    Search the project codebase and documentation using ultra-fast FTS5.
    Returns matched file paths, sections, and symbols.
    You can use the 'exclude' parameter to filter out extensions or paths (e.g. ['tsx', 'json', 'node_modules']).
    """
    project_root = find_project_root()
    try:
        results = search_index(project_root, query, limit=limit, exclude_patterns=exclude)
        if not results:
            return f"No results found for '{query}'."
        
        output = [f"Found {len(results)} matches for '{query}':"]
        for r in results:
            output.append(f"[{r['type'].upper()}] {r['path']} > {r['title']}\n  ...{r['snippet']}...")
        return "\n".join(output)
    except Exception as e:
        return f"Database error. Please run sync_workspace first. ({e})"

@mcp.tool()
async def get_recent_results(limit: int = 10) -> str:
    """
    Fetch the most recently created or modified files in the project.
    Use this to quickly check what was just generated or updated (e.g. specs, logs).
    """
    project_root = find_project_root()
    try:
        results = get_recent(project_root, limit=limit)
        if not results:
            return "No recent files found."
        
        output = [f"Found {len(results)} recent files:"]
        for r in results:
            output.append(f"[{r['category'].upper()}] {r['path']} (Modified: {r['modified']})")
        return "\n".join(output)
    except Exception as e:
        return f"Database error. Please run sync_workspace first. ({e})"

@mcp.tool()
async def log_action(message: str) -> str:
    """
    Log a significant action, decision, or milestone to the project's history database.
    """
    project_root = find_project_root()
    try:
        log_activity(project_root, message)
        return f"Successfully logged action: {message}"
    except Exception as e:
        return f"Failed to log action: {e}"

def main():
    """Entry point for the MCP server."""
    # Run via stdio communication
    mcp.run()

if __name__ == "__main__":
    main()
