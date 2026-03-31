# Musu Indexer MCP Server

High-performance codebase indexer and MCP (Model Context Protocol) server powered by Go and SQLite FTS5.

## Features
- **Ultra-fast Parallel Indexing**: Uses a compiled Go binary (`musu-indexer`) to scan and index thousands of files in seconds.
- **Incremental Sync**: Only updates modified files using stable filesystem keys.
- **FTS5 Search**: Provides deep contextual search across code symbols, document sections, and raw text.
- **MCP Integration**: Exposes `sync_workspace`, `search_codebase`, and `log_action` tools directly to AI assistants.
- **Cross-Platform & WSL2 Optimized**: Includes both Linux and Windows native binaries.

## 🚀 Special Note for Windows & WSL2 Users

If you are a Windows user developing inside WSL2 (Ubuntu, Debian, etc.) while your project files reside on a mounted Windows drive (e.g., `/mnt/c/` or `/mnt/f/`), **file system access can be notoriously slow** due to the 9P protocol bridge.

**Musu Indexer automatically solves this!**
When it detects a WSL2 environment and a mounted path, the Python server intelligently bypasses the slow bridge by executing the native Windows binary (`musu-indexer.exe`) directly via `wslpath`. This guarantees ultra-fast native disk I/O speeds even while you work entirely inside Linux!

## Installation

This package requires Python 3.10+ and the `mcp` library.

1. Navigate to this directory.
2. Install via pip:
   ```bash
   pip install -e .
   ```

## Configuring in AI Clients (Claude Desktop / Gemini)

Add the following to your MCP client configuration (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "musu-indexer": {
      "command": "musu-indexer",
      "args": []
    }
  }
}
```

Or you can run it directly via Python module:
```json
{
  "mcpServers": {
    "musu-indexer": {
      "command": "python",
      "args": ["-m", "musu_indexer.server"]
    }
  }
}
```

## How it Works
When a tool like `sync_workspace` is called, the Python MCP server dynamically locates the `musu-indexer-linux` (or `.exe`) binary in the `bin/` directory, executes the high-speed scan, and builds a `.musu_dev.db` SQLite database at your project root. The `search_codebase` tool then queries this database to provide context to the AI.
