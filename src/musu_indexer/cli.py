import argparse
import sys
from pathlib import Path
from .core import sync_core, search_index, log_activity, find_project_root
from .server import mcp

def main():
    parser = argparse.ArgumentParser(description="Musu Indexer: High-performance codebase indexer and MCP server")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: mcp (Run as MCP server)
    mcp_parser = subparsers.add_parser("mcp", help="Run the MCP server (stdio mode)")

    # Command: sync
    sync_parser = subparsers.add_parser("sync", help="Synchronize the local SQLite database")
    sync_parser.add_argument("--scope", type=str, default="all", choices=["all", "code", "doc"], help="Scope of the sync")

    # Command: search
    search_parser = subparsers.add_parser("search", help="Search the codebase using FTS5")
    search_parser.add_argument("query", type=str, help="The search query")
    search_parser.add_argument("--limit", type=int, default=15, help="Maximum number of results")

    # Command: log
    log_parser = subparsers.add_parser("log", help="Log an activity")
    log_parser.add_argument("message", type=str, help="Activity description")

    args = parser.parse_args()

    # Default to MCP if no args provided (useful for standard MCP client configs)
    if args.command is None or args.command == "mcp":
        mcp.run()
        return

    project_root = find_project_root()

    if args.command == "sync":
        print(f"Syncing project at: {project_root}")
        result = sync_core(project_root, scope=args.scope)
        print(result)

    elif args.command == "search":
        results = search_index(project_root, args.query, limit=args.limit)
        if not results:
            print(f"No results found for '{args.query}'.")
        else:
            print(f"\n🔍 Found {len(results)} matches for '{args.query}':")
            for r in results:
                print(f"[{r['type'].upper()}] {r['path']} > {r['title']}")
                print(f"    ...{r['snippet']}...\n")

    elif args.command == "log":
        log_activity(project_root, args.message)
        print(f"✅ Logged: {args.message}")

if __name__ == "__main__":
    main()
