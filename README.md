# Musu Indexer MCP Server

High-performance codebase indexer and MCP (Model Context Protocol) server powered by Go and SQLite FTS5.

This repository contains the complete toolset:
1. **The Scanner & Indexer (Go Engine)**: An ultra-fast, parallelized filesystem scanner and parser (`indexer_src/`).
2. **The Database Manager (Python)**: Orchestrates the Go engine and manages the `.musu_dev.db` SQLite database using `WAL` mode and 3GB memory mapping.
3. **The MCP Server (Python)**: Exposes the indexed context directly to AI assistants (Claude, Gemini, etc.) via tools like `search_codebase` and `sync_workspace`.

## Features
- **Ultra-fast Parallel Indexing**: Uses a compiled Go binary (`musu-indexer`) to scan and index thousands of files in seconds using a Syncthing-style Producer-Consumer lock-free architecture.
- **Incremental Sync**: Only updates modified files using stable filesystem keys.
- **FTS5 Search**: Provides deep contextual search across code symbols, document sections, and raw text.
- **MCP Integration**: Exposes `sync_workspace`, `search_codebase`, and `log_action` tools directly to AI assistants.
- **Cross-Platform & WSL2 Optimized**: Includes both Linux and Windows native binaries out-of-the-box.

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

## 3 Ways to Use Musu Indexer

This project is built as a complete ecosystem, offering three distinct ways to interact with the engine:

### 1. As an MCP Server (For AI Assistants)
Expose the indexed context directly to Claude, Gemini, and other MCP-compatible clients. The server runs in the background and responds to tool calls (`search_codebase`, `sync_workspace`).

Add the following to your MCP client configuration (e.g., `claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "musu-indexer": {
      "command": "musu-indexer",
      "args": ["mcp"]
    }
  }
}
```

### 2. As an "Everything" CLI (For Humans)
You don't need an AI to benefit from ultra-fast FTS5 searches. Use the CLI tool directly in your terminal:
```bash
# Sync the current project
musu-indexer sync

# Search the codebase instantly
musu-indexer search "VRAM configuration"

# Log an important milestone
musu-indexer log "Refactored the parallel scanning logic"
```

### 3. As an AI Skill (For CLI Agents)
If you are using terminal-based AI agents (like Gemini CLI), you can load the `SKILL.md` file included in this repository. This instructs the AI on exactly how to use the `musu-indexer` CLI commands to gather context autonomously, replacing slow and error-prone `grep` searches with instant database queries.
