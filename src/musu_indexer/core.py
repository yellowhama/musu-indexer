import sqlite3
import os
import time
import subprocess
from pathlib import Path
from .query_expander import QueryExpander

# Dynamically calculate the path to the bin folder inside the package
PACKAGE_ROOT = Path(__file__).parent
LINUX_BIN = str(PACKAGE_ROOT / "bin" / "musu-indexer-linux")

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

def sync_bottom_up(project_root: Path, scope: str = "all") -> str:
    """[New Strategy] Map directories first, then conquer from deepest subfolders upward."""
    print(f"🗺️  [1/3] Mapping project structure: {project_root}")
    start_time = time.time()
    
    # DB 초기화 검증
    db_path = str(project_root / ".musu_dev.db")
    if not os.path.exists(db_path):
        init_db(project_root)

    # 1. 지도 그리기 (폴더 목록만 추출)
    cmd = [LINUX_BIN, "dirs", str(project_root)]
    output = subprocess.check_output(cmd, encoding='utf-8', errors='ignore')
    dirs = [d.strip() for d in output.splitlines() if d.strip()]
    
    # 2. 가장 깊은 폴더부터 정렬 (Bottom-Up)
    # 경로 조각(/)이 많은 순서대로 정렬
    dirs.sort(key=lambda x: x.count('/'), reverse=True)
    dirs.insert(0, ".") # 마지막에 루트 폴더 추가
    
    print(f"📂 Found {len(dirs)} directories. Starting bottom-up conquest...")

    total_files = 0
    # 3. 폴더별 정밀 타격
    for i, rel_dir in enumerate(dirs):
        full_dir = project_root / rel_dir
        # 해당 폴더 '직계' 파일들만 찾기 (재귀 X)
        target_files = []
        try:
            for entry in os.scandir(full_dir):
                if entry.is_file():
                    ext = Path(entry.name).suffix
                    if ext in {'.rs', '.ts', '.tsx', '.md', '.py', '.go', '.json', '.toml', '.sql'}:
                        rel_file_path = str(Path(rel_dir) / entry.name).replace('\\', '/')
                        if rel_file_path.startswith("./"): rel_file_path = rel_file_path[2:]
                        target_files.append(rel_file_path)
        except Exception: continue

        if target_files:
            print(f"  [{i+1}/{len(dirs)}] Ingesting {len(target_files)} files in: {rel_dir}")
            ingest_core(project_root, target_files, start_time=None)
            total_files += len(target_files)

    return f"🚀 Conquest Complete! Successfully indexed {total_files} files across {len(dirs)} folders in {time.time()-start_time:.2f}s"

def sync_core(project_root: Path, scope: str = "all") -> str:
    """Core synchronization logic using Linux native engine for maximum stability in WSL."""
    # Ensure DB is initialized
    db_path = str(project_root / ".musu_dev.db")
    if not os.path.exists(db_path):
        init_db(project_root)

    start_time = time.time()
    
    # Force use of Linux binary
    cmd = [LINUX_BIN, "scan", str(project_root)]

    # 2. Incremental Diffing & Stable Key Mapping (Python Brain)
    conn = get_db(project_root)
    cursor = conn.cursor()
    cursor.execute("SELECT path, last_modified, size FROM files")
    db_files = {r['path']: (r['last_modified'], r['size']) for r in cursor.fetchall()}
    
    changed_list = []
    seen_paths = set()
    reused_count = 0

    # Execute scan and process output line-by-line (Streaming)
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='ignore')
    for line in process.stdout:
        line = line.strip()
        if '🔍 Scanning...' in line:
            print(line, flush=True)
            continue
        if '|' not in line: continue
        
        rel_path, mtime_str, size_str = line.split('|')
        rel_path = rel_path.replace('\\', '/')
        
        # Apply scope filtering
        if scope == "doc" and not rel_path.startswith("docs"): continue
        if scope == "code" and not any(rel_path.startswith(d) for d in ["src", "crates", "release", "lib", "internal"]): continue

        stable_key = rel_path
        seen_paths.add(stable_key)
        mtime, size = float(mtime_str), int(size_str)
        
        if stable_key in db_files:
            dm, ds = db_files[stable_key]
            if abs(mtime - dm) < 1.0 and size == ds:
                reused_count += 1
                continue
        changed_list.append(stable_key)
    
    process.wait()

    # Clean up deleted files
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

    # 3. Precision Indexing (Go Engine)
    return ingest_core(project_root, changed_list, start_time, reused_count)

def ingest_core(project_root: Path, dirty_paths: list[str], start_time: float = None, reused_count: int = 0) -> str:
    """Partially reindex only the specified dirty files (Auto-Ingest)."""
    if not dirty_paths:
        return "No files to ingest."

    if start_time is None:
        start_time = time.time()

    db_path = str(project_root / ".musu_dev.db")
    if not os.path.exists(db_path):
        init_db(project_root)

    tmp_dir = project_root / "work" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    list_file = tmp_dir / "sync_targets.txt"
    
    normalized_paths = [p.replace('\\', '/') for p in dirty_paths]
    with open(list_file, "w") as f: 
        f.write("\n".join(normalized_paths))

    cmd = [LINUX_BIN, "index", db_path, str(project_root), str(list_file)]

    print(f"  [3/3] Rematching {len(normalized_paths)} entries using Go Engine...")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    for line in process.stdout:
        print(line, end='', flush=True)
    process.wait()

    # [Phase 4] Auto-Tagging System (Post-processing)
    print("  [4/4] Applying auto-tags and finalizing...")
    conn = get_db(project_root)
    cursor = conn.cursor()
    cursor.execute("UPDATE files SET category = 'spec' WHERE path LIKE '%spec%' OR path LIKE '%docs/%'")
    cursor.execute("UPDATE files SET category = 'report' WHERE path LIKE '%report%'")
    cursor.execute("UPDATE files SET category = 'log' WHERE path LIKE '%log%'")
    cursor.execute("UPDATE files SET category = 'reference' WHERE path LIKE '%reference%'")
    
    cursor.execute("INSERT INTO work_log (action, details, status) VALUES ('sync_or_ingest', ?, 'success')", 
                   (f"Processed {len(dirty_paths)} files, {reused_count} reused",))
    conn.commit()
    conn.close()
    
    return f"Done! Indexed {len(dirty_paths)} files in {time.time()-start_time:.2f}s"

def get_recent(project_root: Path, limit: int = 10) -> list[dict]:
    """Fetch the most recently modified or indexed files."""
    conn = get_db(project_root)
    res = conn.execute(
        "SELECT path, category, datetime(last_modified, 'unixepoch', 'localtime') as mod_time FROM files ORDER BY last_modified DESC LIMIT ?",
        (limit,)
    ).fetchall()
    results = [{"path": r['path'], "category": r['category'], "modified": r['mod_time']} for r in res]
    conn.close()
    return results

def search_index(project_root: Path, query: str, limit: int = 15) -> list[dict]:
    """Execute a Full-Text Search (FTS5) against the index with smart query expansion."""
    conn = get_db(project_root)
    fts_query = QueryExpander.build_fts_query(query, max_terms=6)
    
    if not fts_query:
        return []

    res = conn.execute(
        "SELECT path, title, type, snippet(search_index, -1, '<b>', '</b>', '...', 32) as match_snippet FROM search_index WHERE content MATCH ? LIMIT ?", 
        (fts_query, limit)
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
