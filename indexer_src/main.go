package main

import (
	"bufio"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	_ "modernc.org/sqlite"
)

// 구조체 정의
type Symbol struct{ Name, Kind string; LineStart int; Signature string }
type Section struct{ Title string; Level int; Content string }

type IndexTask struct {
	Path    string
	Size    int
	Content string
	Syms    []Symbol
	Secs    []Section
}

var (
	rsPatterns = []struct{ re *regexp.Regexp; kind string }{
		{regexp.MustCompile(`^\s*(?:pub(?:\(.*\))?\s+)?fn\s+([a-zA-Z_]\w*)`), "function"},
		{regexp.MustCompile(`^\s*(?:pub(?:\(.*\))?\s+)?struct\s+([a-zA-Z_]\w*)`), "struct"},
		{regexp.MustCompile(`^\s*(?:pub(?:\(.*\))?\s+)?enum\s+([a-zA-Z_]\w*)`), "enum"},
		{regexp.MustCompile(`^\s*impl(?:\s+.*)?\s+([a-zA-Z_]\w*)`), "impl"},
	}
	tsPatterns = []struct{ re *regexp.Regexp; kind string }{
		{regexp.MustCompile(`^\s*(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z_]\w*)`), "function"},
		{regexp.MustCompile(`^\s*(?:export\s+)?class\s+([a-zA-Z_]\w*)`), "class"},
		{regexp.MustCompile(`^\s*(?:export\s+)?interface\s+([a-zA-Z_]\w*)`), "interface"},
	}
	pyPatterns = []struct{ re *regexp.Regexp; kind string }{
		{regexp.MustCompile(`^\s*def\s+([a-zA-Z_]\w*)`), "function"},
		{regexp.MustCompile(`^\s*class\s+([a-zA-Z_]\w*)`), "class"},
	}
	goPatterns = []struct{ re *regexp.Regexp; kind string }{
		{regexp.MustCompile(`^\s*func\s+(?:\([^\)]+\)\s+)?([a-zA-Z_]\w*)`), "function"},
		{regexp.MustCompile(`^\s*type\s+([a-zA-Z_]\w*)\s+struct`), "struct"},
		{regexp.MustCompile(`^\s*type\s+([a-zA-Z_]\w*)\s+interface`), "interface"},
	}
	mdHeader = regexp.MustCompile(`^(#{1,6})\s+(.*)$`)
)

func parseFile(path, content string) ([]Symbol, []Section) {
	ext := filepath.Ext(path)
	var syms []Symbol
	var secs []Section
	lines := strings.Split(content, "\n")
	
	var pats []struct{ re *regexp.Regexp; kind string }
	switch ext {
	case ".rs": pats = rsPatterns
	case ".ts", ".tsx": pats = tsPatterns
	case ".py": pats = pyPatterns
	case ".go": pats = goPatterns
	}

	if pats != nil {
		for i, line := range lines {
			for _, p := range pats {
				if m := p.re.FindStringSubmatch(line); len(m) > 1 {
					syms = append(syms, Symbol{Name: m[1], Kind: p.kind, LineStart: i + 1, Signature: strings.TrimSpace(line)})
				}
			}
		}
	}
	if ext == ".md" {
		var cur *Section
		for _, line := range lines {
			if m := mdHeader.FindStringSubmatch(line); m != nil {
				if cur != nil { secs = append(secs, *cur) }
				cur = &Section{Title: strings.TrimSpace(m[2]), Level: len(m[1]), Content: ""}
			} else if cur != nil {
				cur.Content += line + "\n"
			}
		}
		if cur != nil { secs = append(secs, *cur) }
	}
	return syms, secs
}

// 1. Syncthing-style 병렬 스캐너
func doScan(root string) {
	ignore := map[string]bool{"node_modules": true, "target": true, ".git": true, "dist": true, "build": true, ".vibe": true, "venv": true, "__pycache__": true}
	targets := map[string]bool{".rs": true, ".ts": true, ".tsx": true, ".md": true, ".py": true, ".go": true, ".json": true, ".toml": true, ".sql": true}

	var wg sync.WaitGroup
	results := make(chan string, 1000)

	// 병렬 탐색기 시작
	var walkDir func(dir string)
	walkDir = func(dir string) {
		defer wg.Done()
		entries, err := os.ReadDir(dir)
		if err != nil { return }
		
		for _, d := range entries {
			if d.IsDir() {
				if !ignore[d.Name()] {
					wg.Add(1)
					go walkDir(filepath.Join(dir, d.Name()))
				}
			} else if targets[filepath.Ext(d.Name())] {
				fullPath := filepath.Join(dir, d.Name())
				if info, err := d.Info(); err == nil {
					rel, _ := filepath.Rel(root, fullPath)
					results <- fmt.Sprintf("%s|%d|%d", filepath.ToSlash(rel), info.ModTime().Unix(), info.Size())
				}
			}
		}
	}

	// 큐 출력기
	go func() {
		for r := range results {
			fmt.Println(r)
		}
	}()

	wg.Add(1)
	walkDir(root)
	wg.Wait()
	close(results)
}

// 2. Syncthing-style Producer-Consumer 파이프라인 (Lock-Free)
func doIndex(dbPath, root, listFile string) {
	f, _ := os.Open(listFile)
	defer f.Close()
	scanner := bufio.NewScanner(f)
	var files []string
	for scanner.Scan() {
		if t := scanner.Text(); t != "" { files = append(files, t) }
	}
	if len(files) == 0 { return }

	tasks := make(chan string, len(files))
	parsedChan := make(chan IndexTask, 100) // Producer -> Consumer 채널

	for _, rel := range files { tasks <- rel }
	close(tasks)

	// Producer: N개의 워커 고루틴 (순수 파일 I/O 및 파싱)
	var parseWg sync.WaitGroup
	numWorkers := 16
	for i := 0; i < numWorkers; i++ {
		parseWg.Add(1)
		go func() {
			defer parseWg.Done()
			for rel := range tasks {
				data, err := os.ReadFile(filepath.Join(root, rel))
				if err != nil { continue }
				content := string(data)
				syms, secs := parseFile(rel, content)
				parsedChan <- IndexTask{Path: rel, Size: len(data), Content: content, Syms: syms, Secs: secs}
			}
		}()
	}

	// 파싱 완료 후 채널 닫기
	go func() {
		parseWg.Wait()
		close(parsedChan)
	}()

	// Consumer: 단일 전담 DB Writer (SQLite Lock 병목 원천 차단)
	db, _ := sql.Open("sqlite", dbPath)
	defer db.Close()
	db.Exec("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA mmap_size=3000000000; PRAGMA cache_size=-20000;")

	processed := 0
	tx, _ := db.Begin()

	for t := range parsedChan {
		category := strings.Split(t.Path, "/")[0]
		tx.Exec("INSERT OR REPLACE INTO files (path, size, last_modified, category, indexed_at) VALUES (?, ?, ?, ?, datetime(\"now\"))", t.Path, t.Size, 0, category)
		tx.Exec("DELETE FROM doc_sections WHERE file_path = ?; DELETE FROM code_symbols WHERE file_path = ?; DELETE FROM search_index WHERE path = ?;", t.Path, t.Path, t.Path)
		
		short := t.Content; if len(short) > 2000 { short = short[:2000] }
		tx.Exec("INSERT INTO search_index (path, title, content, type) VALUES (?, ?, ?, \"file\")", t.Path, t.Path, short)
		
		for _, s := range t.Secs {
			tx.Exec("INSERT INTO doc_sections (file_path, title, level, content) VALUES (?, ?, ?, ?)", t.Path, s.Title, s.Level, s.Content)
			ss := s.Content; if len(ss) > 1000 { ss = ss[:1000] }
			tx.Exec("INSERT INTO search_index (path, title, content, type) VALUES (?, ?, ?, \"section\")", t.Path, s.Title, ss)
		}
		for _, s := range t.Syms {
			tx.Exec("INSERT INTO code_symbols (file_path, name, kind, line_start, signature) VALUES (?, ?, ?, ?, ?)", t.Path, s.Name, s.Kind, s.LineStart, s.Signature)
			tx.Exec("INSERT INTO search_index (path, title, content, type) VALUES (?, ?, ?, \"symbol\")", t.Path, s.Kind+": "+s.Name, s.Signature)
		}

		processed++
		// 1000건마다 트랜잭션 커밋하여 메모리 폭발 방지 (Bulk Insert)
		if processed%1000 == 0 {
			tx.Commit()
			tx, _ = db.Begin()
			fmt.Printf("  ⚡ Synced %d/%d files...\n", processed, len(files))
		}
	}
	tx.Commit() // 남은 데이터 커밋
	db.Exec("PRAGMA optimize")
	time.Sleep(100 * time.Millisecond) // WAL Sync 대기
}

func main() {
	if len(os.Args) < 3 { return }
	cmd := os.Args[1]
	switch cmd {
	case "scan": doScan(os.Args[2])
	case "index": doIndex(os.Args[2], os.Args[3], os.Args[4])
	}
}
