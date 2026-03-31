---
name: musu-indexer
description: An ultra-fast, cross-platform codebase indexer and search engine. Use this skill to sync project state, perform deep semantic searches, and log activities within any workspace using the `musu-indexer` CLI.
---

# Musu Indexer Skill

This skill grants you the ability to interact with the high-performance `musu-indexer` engine. It relies on a local SQLite database (`.musu_dev.db`) populated by a blazingly fast Go-based scanner.

## Core Directives

When working in a large codebase, NEVER rely solely on `grep` or manual file reading to find references. ALWAYS use the `musu-indexer` for accurate context gathering.

### 1. Synchronize the Workspace
If you modify files, create new ones, or suspect the index is out of date, sync the database. It uses an incremental update system, so it is extremely fast.

- **Command**: `musu-indexer sync` (or `musu-indexer sync --scope code` / `doc`)
- **Usage**: Run this when starting a session or after significant codebase modifications.

### 2. Deep Search
Use the FTS5 search engine to find code symbols, document sections, or text.

- **Command**: `musu-indexer search "<query>"`
- **Usage**: Example: `musu-indexer search "parallel_scan"` or `musu-indexer search "VRAM"`. This returns specific file paths and snippets which you should then read using standard file tools.

### 3. Log Activity
Maintain a persistent history of your actions, decisions, and milestones.

- **Command**: `musu-indexer log "<message>"`
- **Usage**: After finishing a complex refactoring or fixing a bug, write a concise log entry.

## Execution Rules
- The CLI tool automatically detects the project root (where `.git` or `.musu_dev.db` is located). You can run it from any subdirectory.
- If you receive a "Database error" indicating the tables do not exist, run `musu-indexer sync` immediately to initialize them.
