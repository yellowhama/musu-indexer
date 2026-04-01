import subprocess
import json
import time
from pathlib import Path
from .core import get_db, find_project_root, PACKAGE_ROOT

# Use the same bin detection logic as core.py
SPY_ENGINE_BIN = str(PACKAGE_ROOT.parent / "musu-computer-tools" / "musu-chat-spy-engine" / "target" / "release" / "musu-chat-spy-engine")

def start_spy_logging(project_root: Path, window_keyword: str):
    """
    Spawns the Rust spy engine and blindly inserts its JSON output into the database.
    (Mechanical Logging approach - stable and AI-friendly)
    """
    print(f"🕵️‍♂️ [spy.sink] Starting mechanical logger for window: '{window_keyword}'")
    
    # Check if binary exists
    if not Path(SPY_ENGINE_BIN).exists():
        # Fallback to local development path if package bin is missing
        print(f"⚠️ Warning: Spy engine binary not found at {SPY_ENGINE_BIN}. Please compile the Rust engine.")
        return

    cmd = [SPY_ENGINE_BIN, window_keyword]
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
    
    conn = get_db(project_root)
    
    try:
        for line in process.stdout:
            line = line.strip()
            if not line: continue
            
            try:
                data = json.loads(line)
                timestamp = data.get("timestamp")
                source = data.get("window_title")
                content = data.get("content")
                
                if content:
                    # Blindly insert raw data (Mechanical Log)
                    conn.execute(
                        "INSERT INTO raw_snapshots (source, content) VALUES (?, ?)",
                        (source, content)
                    )
                    conn.commit()
                    print(f"📝 Logged {len(content)} chars from '{source}'")
            except json.JSONDecodeError:
                # Print non-JSON lines (like startup messages)
                print(f"LOG: {line}")
                
    except KeyboardInterrupt:
        print("\n🛑 [spy.sink] Stopping logger...")
    finally:
        process.terminate()
        conn.close()
