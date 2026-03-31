import sqlite3
import os
import time
import subprocess
from pathlib import Path

# Dynamically calculate the path to the bin folder inside the package
PACKAGE_ROOT = Path(__file__).parent.parent.parent
LINUX_BIN = str(PACKAGE_ROOT / "bin" / "musu-indexer-linux")
WIN_BIN = str(PACKAGE_ROOT / "bin" / "musu-indexer.exe")

INDEX_VERSION = 2

def find_project_root(start_path: str = None) -> Path:
    """Finds the root directory of the project by looking for .git or .musu_dev.db"""
    curr = Path(start_path or os.getcwd()).resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / ".git").exists() or (parent / ".musu_dev.db").exists():
            return parent
    return curr

def get_db(project_root: Path):
    db_path = str(project_root / ".musu_dev.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Ultra-fast main DB configuration
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA mmap_size=3000000000") # 3GB Memory Mapping
    return conn

def init_db(project_root: Path):
    """Initializes the SQLite schema for the indexer."""
    conn = get_db(project_root)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, size INTEGER, last_modified REAL, category TEXT, indexed_at TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS doc_sections (file_path TEXT, title TEXT, level INTEGER, content TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS code_symbols (file_path TEXT, name TEXT, kind TEXT, line_start INTEGER, signature TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS work_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, action TEXT, details TEXT, status TEXT)""")
    cursor.execute("DROP TABLE IF EXISTS search_index")
    cursor.execute("""CREATE VIRTUAL TABLE search_index USING fts5(path, title, content, type, tokenize='unicode61')""")
    conn.commit()
    conn.close()

def sync_core(project_root: Path, scope: str = "all") -> str:
    """Core synchronization logic using incremental state and external Go binaries."""
    # Ensure DB is initialized
    db_path = str(project_root / ".musu_dev.db")
    if not os.path.exists(db_path):
        init_db(project_root)

    start_time = time.time()
    
    # Detect WSL2 Environment
    is_wsl = False
    try:
        with open("/proc/version", "r") as f:
            if "microsoft" in f.read().lower(): 
                is_wsl = True
    except: 
        pass

    # 1. Ultra-fast Metadata Scan using Go Muscle
    # WSL2 Optimization: If running inside WSL but the project is on a mounted Windows drive (e.g., /mnt/c/),
    # invoke the native Windows binary (.exe) via wslpath to bypass the slow 9P protocol file system bridge.
    if is_wsl and str(project_root).startswith("/mnt/") and os.path.exists(WIN_BIN):
        try:
            win_root = subprocess.check_output(["wslpath", "-w", str(project_root)], encoding='utf-8').strip()
            cmd = [WIN_BIN, "scan", win_root]
        except: 
            cmd = [LINUX_BIN, "scan", str(project_root)]
    else:
        cmd = [LINUX_BIN, "scan", str(project_root)]

    scan_output = subprocess.check_output(cmd, encoding='utf-8', errors='ignore')
    
    # 2. Incremental Diffing & Stable Key Mapping (Python Brain)
    conn = get_db(project_root)
    cursor = conn.cursor()
    cursor.execute("SELECT path, last_modified, size FROM files")
    db_files = {r['path']: (r['last_modified'], r['size']) for r in cursor.fetchall()}
    
    changed_list = []
    seen_paths = set()
    reused_count = 0
    
    for line in scan_output.splitlines():
        if '|' not in line: continue
        rel_path, mtime_str, size_str = line.split('|')
        rel_path = rel_path.replace('\\', '/') # Normalize paths for Windows compatibility
        
        # Apply scope filtering
        if scope == "doc" and not rel_path.startswith("docs"): continue
        if scope == "code" and not any(rel_path.startswith(d) for d in ["src", "crates", "release", "lib", "internal"]): continue

        stable_key = rel_path
        seen_paths.add(stable_key)
        mtime, size = float(mtime_str), int(size_str)
        
        # Check if the file is unmodified since last sync
        if stable_key in db_files:
            dm, ds = db_files[stable_key]
            if abs(mtime - dm) < 1.0 and size == ds:
                reused_count += 1
                continue
        changed_list.append(stable_key)

    # Clean up stale entries for deleted files
    deleted = set(db_files.keys()) - seen_paths
    if deleted:
        for dp in deleted:
            cursor.execute("DELETE FROM files WHERE path = ?", (dp,))
            cursor.execute("DELETE FROM doc_sections WHERE file_path = ?", (dp,))
            cursor.execute("DELETE FROM code_symbols WHERE file_path = ?", (dp,))
            cursor.execute("DELETE FROM search_index WHERE path = ?", (dp,))
        conn.commit()

    if not changed_list:
        conn.execute("PRAGMA optimize")
        conn.close()
        return f"Index is up to date. ({reused_count} reused, {len(deleted)} deleted). Time: {time.time()-start_time:.2f}s"

    # 3. Precision Indexing (Go Muscle) - Only process changed files
    tmp_dir = project_root / "work" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    list_file = tmp_dir / "sync_targets.txt"
    with open(list_file, "w") as f: 
        f.write("\n".join(changed_list))

    # WSL2 Optimization for Indexing
    if is_wsl and str(project_root).startswith("/mnt/") and os.path.exists(WIN_BIN):
        try:
            win_db = subprocess.check_output(["wslpath", "-w", db_path], encoding='utf-8').strip()
            win_root = subprocess.check_output(["wslpath", "-w", str(project_root)], encoding='utf-8').strip()
            win_list = subprocess.check_output(["wslpath", "-w", str(list_file)], encoding='utf-8').strip()
            cmd = [WIN_BIN, "index", win_db, win_root, win_list]
        except: 
            cmd = [LINUX_BIN, "index", db_path, str(project_root), str(list_file)]
    else:
        cmd = [LINUX_BIN, "index", db_path, str(project_root), str(list_file)]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    cursor.execute("INSERT INTO work_log (action, details, status) VALUES ('sync', ?, 'success')", 
                   (f"v{INDEX_VERSION} Incremental: {len(changed_list)} rematched",))
    conn.execute("PRAGMA optimize")
    conn.commit()
    conn.close()
    
    return f"Sync Complete! Indexed {len(changed_list)} files, {reused_count} unchanged. Time: {time.time()-start_time:.2f}s"

def search_index(project_root: Path, query: str, limit: int = 15) -> list[dict]:
    """Execute a Full-Text Search (FTS5) against the index."""
    conn = get_db(project_root)
    safe_query = f'"{query}"'
    res = conn.execute(
        "SELECT path, title, type, snippet(search_index, -1, '<b>', '</b>', '...', 32) as match_snippet FROM search_index WHERE content MATCH ? LIMIT ?", 
        (safe_query, limit)
    ).fetchall()
    
    results = [{"path": r['path'], "title": r['title'], "type": r['type'], "snippet": r['match_snippet']} for r in res]
    conn.close()
    return results

def log_activity(project_root: Path, message: str) -> None:
    """Log an event or action to the local project database."""
    conn = get_db(project_root)
    conn.execute("INSERT INTO work_log (action, details, status) VALUES ('agent_log', ?, 'done')", (message,))
    conn.commit()
    conn.close()
