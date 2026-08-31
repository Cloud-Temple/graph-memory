package scanner

import (
	"os"
	"path/filepath"
	"testing"
)

func TestScanLocalDedupAndBinaryAllowlist(t *testing.T) {
	dir := t.TempDir()
	for name, data := range map[string][]byte{"a.md": []byte("text"), "b.md": []byte("text"), "binary.md": {0, 1, 2}, "doc.pdf": {'%', 'P', 'D', 'F', 0}, ".secret.md": []byte("secret")} {
		if err := os.WriteFile(filepath.Join(dir, name), data, 0600); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.Symlink(filepath.Join(dir, "a.md"), filepath.Join(dir, "link.md")); err != nil {
		t.Fatal(err)
	}
	res, err := Scan(ScanOptions{RootPath: dir, AllowedExtensions: []string{".md", ".pdf"}})
	if err != nil || res.TotalFiles != 2 || res.SkippedCount != 1 {
		t.Fatalf("scan=%+v err=%v", res, err)
	}
	if res.Batches[0].Files[0].RelPath != "a.md" || res.Batches[0].Files[1].RelPath != "doc.pdf" {
		t.Fatalf("wrong files: %+v", res.Batches)
	}
}
