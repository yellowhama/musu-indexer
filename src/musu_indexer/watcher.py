import time
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from .core import ingest_core

class DirtyQueueHandler(FileSystemEventHandler):
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.dirty_set = set()
        self.lock = threading.Lock()
        
        # 무시할 디렉토리 목록 (성능을 위해)
        self.ignore_dirs = {'.git', 'node_modules', 'target', 'build', 'dist', '__pycache__', '.vibe', '.musu_dev.db'}

    def _should_ignore(self, path: str) -> bool:
        parts = Path(path).parts
        for ignored in self.ignore_dirs:
            if ignored in parts:
                return True
        # SQLite 저널 파일들도 무시
        if path.endswith('-wal') or path.endswith('-shm'):
            return True
        return False

    def _add_dirty(self, path: str):
        if not self._should_ignore(path):
            try:
                # DB가 요구하는 상대 경로로 변환
                rel_path = str(Path(path).relative_to(self.project_root))
                with self.lock:
                    self.dirty_set.add(rel_path)
            except ValueError:
                pass

    def on_modified(self, event):
        if not event.is_directory:
            self._add_dirty(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._add_dirty(event.src_path)

    def pop_all(self):
        """Debounce 주기마다 쌓인 큐를 싹 비워서 반환"""
        with self.lock:
            items = list(self.dirty_set)
            self.dirty_set.clear()
            return items

def start_watcher(project_root: Path, debounce_seconds: int = 2):
    """
    데몬 모드: 파일 변경을 감지하고, Debounce 주기마다 묶어서 (Auto-Ingest) 처리합니다.
    """
    event_handler = DirtyQueueHandler(project_root)
    observer = Observer()
    observer.schedule(event_handler, str(project_root), recursive=True)
    observer.start()
    
    print(f"👀 [index.watch] Auto-Ingest Daemon started. Watching {project_root}...")
    try:
        while True:
            time.sleep(debounce_seconds)
            dirty_files = event_handler.pop_all()
            if dirty_files:
                print(f"\n⚡ Detected changes in {len(dirty_files)} files. Auto-ingesting...")
                result = ingest_core(project_root, dirty_files)
                print(result)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[index.watch] Daemon stopped.")
    observer.join()
