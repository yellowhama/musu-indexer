import argparse
import sys
from pathlib import Path
from .core import sync_core, search_index, log_activity, find_project_root, get_recent, sync_bottom_up, get_spy_context
from .server import mcp
from .watcher import start_watcher
from .spy_sink import start_spy_logging

def main():
    parser = argparse.ArgumentParser(description="Musu Indexer: High-performance codebase indexer and MCP server")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: sync (Standard)
    sync_parser = subparsers.add_parser("sync", help="Standard incremental sync")
    sync_parser.add_argument("--scope", type=str, default="all", choices=["all", "code", "doc"], help="Scope of the sync")

    # Command: sync-map (Bottom-Up Strategy)
    map_parser = subparsers.add_parser("sync-map", help="Deep-first bottom-up sync strategy for massive projects")
    map_parser.add_argument("--scope", type=str, default="all", help="Scope of the sync")

    # Command: spy (Mechanical Logger)
    spy_parser = subparsers.add_parser("spy", help="Start the mechanical chat logger for a specific window")
    spy_parser.add_argument("window", type=str, help="Window title keyword to watch")

    # Command: spy-logs (View Logs)
    spy_logs_parser = subparsers.add_parser("spy-logs", help="View recent mechanical spy logs")
    spy_logs_parser.add_argument("window", type=str, help="Window title keyword")
    spy_logs_parser.add_argument("--limit", type=int, default=3, help="Max entries to show")

    # Command: mcp (Run as MCP server)
    mcp_parser = subparsers.add_parser("mcp", help="Run the MCP server (stdio mode)")

    # Command: watch
    watch_parser = subparsers.add_parser("watch", help="Start the Auto-Ingest Daemon to watch for file changes")
    watch_parser.add_argument("--debounce", type=int, default=2, help="Debounce time in seconds")

    # Command: search
    search_parser = subparsers.add_parser("search", help="Search the codebase using FTS5")
    search_parser.add_argument("query", type=str, help="The search query")
    search_parser.add_argument("--limit", type=int, default=15, help="Maximum number of results")
    search_parser.add_argument("--exclude", nargs='+', help="Exclude patterns (e.g., tsx, node_modules, /tests/)")

    # Command: recent
    recent_parser = subparsers.add_parser("recent", help="View recently created or modified files")
    recent_parser.add_argument("--limit", type=int, default=10, help="Maximum number of results")

    # Command: log
    log_parser = subparsers.add_parser("log", help="Log an activity")
    log_parser.add_argument("message", type=str, help="Activity description")

    args = parser.parse_args()

    # Default to MCP if no args provided
    if args.command is None or args.command == "mcp":
        mcp.run()
        return

    project_root = find_project_root()

    if args.command == "sync":
        print(f"Syncing project at: {project_root}")
        result = sync_core(project_root, scope=args.scope)
        print(result)

    elif args.command == "sync-map":
        print(f"Executing Bottom-Up Sync at: {project_root}")
        result = sync_bottom_up(project_root, scope=args.scope)
        print(result)

    elif args.command == "spy":
        start_spy_logging(project_root, args.window)

    elif args.command == "spy-logs":
        results = get_spy_context(project_root, args.window, limit=args.limit)
        if not results:
            print(f"No logs found for '{args.window}'.")
        else:
            print(f"\n🕵️‍♂️ Recent Spy Logs for '{args.window}':")
            for r in results:
                print(f"[{r['timestamp']}]")
                print(f"{r['content']}\n" + "-"*40)

    elif args.command == "watch":
        start_watcher(project_root, debounce_seconds=args.debounce)

    elif args.command == "search":
        results = search_index(project_root, args.query, limit=args.limit, exclude_patterns=args.exclude)
        if not results:
            print(f"No results found for '{args.query}'.")
        else:
            print(f"\n🔍 Found {len(results)} matches for '{args.query}':")
            for r in results:
                print(f"[{r['type'].upper()}] {r['path']} > {r['title']}")
                print(f"    ...{r['snippet']}...\n")

    elif args.command == "recent":
        results = get_recent(project_root, limit=args.limit)
        if not results:
            print("No recent files found.")
        else:
            print(f"\n🕒 Found {len(results)} recent files:")
            for r in results:
                print(f"[{r['category'].upper()}] {r['path']} (Modified: {r['modified']})")

    elif args.command == "log":
        log_activity(project_root, args.message)
        print(f"✅ Logged: {args.message}")

if __name__ == "__main__":
    main()
