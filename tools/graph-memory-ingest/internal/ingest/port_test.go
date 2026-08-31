package ingest

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"graph-memory-ingest/internal/mcpclient"
	"graph-memory-ingest/internal/scanner"
)

func TestReconcileBatchRejectsAmbiguity(t *testing.T) {
	files := []scanner.FileItem{{RelPath: "a/doc.md", Filename: "doc.md"}, {RelPath: "b/doc.md", Filename: "doc.md"}}
	cases := map[string]string{
		"duplicate source":          `{"items":[{"source_path":"a/doc.md","status":"succeeded"},{"source_path":"a/doc.md","status":"succeeded"}]}`,
		"duplicate job":             `{"items":[{"source_path":"a/doc.md","job_id":"1","status":"queued"},{"source_path":"b/doc.md","job_id":"1","status":"queued"}]}`,
		"unknown source":            `{"items":[{"source_path":"x/doc.md","status":"succeeded"}]}`,
		"missing source":            `{"items":[{"source_path":"a/doc.md","status":"succeeded"}]}`,
		"ambiguous filename":        `{"jobs":[{"filename":"doc.md","status":"succeeded"}]}`,
		"single job multiple files": `{"job_id":"1","status":"queued"}`,
		"missing job":               `{"items":[{"source_path":"a/doc.md","status":"queued"}]}`,
		"unknown status":            `{"items":[{"source_path":"a/doc.md","status":"mystery"}]}`,
		"contradictory error":       `{"items":[{"source_path":"a/doc.md","status":"succeeded"}],"errors":[{"source_path":"a/doc.md","error":"failure"}]}`,
		"malformed errors":          `{"items":[],"errors":"invalid"}`,
		"duplicate errors":          `{"errors":[{"source_path":"a/doc.md","error":"x"},{"source_path":"a/doc.md","error":"x"}]}`,
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			var response map[string]interface{}
			if err := json.Unmarshal([]byte(body), &response); err != nil {
				t.Fatal(err)
			}
			if _, err := ReconcileBatch(files, response); err == nil {
				t.Fatal("accepted an ambiguous batch")
			}
		})
	}
}

func TestReconcileCanonicalStatuses(t *testing.T) {
	statuses := []string{"succeeded", "completed", "skipped", "changed_skipped", "queued", "running", "failed", "error", "queue_full", "cancelled"}
	for _, status := range statuses {
		t.Run(status, func(t *testing.T) {
			files := []scanner.FileItem{{RelPath: "a/doc.md", Filename: "doc.md", SHA256: "fresh"}}
			res := map[string]interface{}{"jobs": []interface{}{map[string]interface{}{"filename": "doc.md", "job_id": "job", "status": status}}}
			records, err := ReconcileBatch(files, res)
			if err != nil || len(records) != 1 || records[0].Status != status || records[0].SHA256 != "fresh" {
				t.Fatalf("records=%+v err=%v", records, err)
			}
		})
	}
	var res map[string]interface{}
	_ = json.Unmarshal([]byte(`{"items":[{"source_path":"a","status":"completed"}],"errors":[{"source_path":"b","error":"queue full"}]}`), &res)
	records, err := ReconcileBatch([]scanner.FileItem{{RelPath: "a"}, {RelPath: "b"}}, res)
	if err != nil || len(records) != 2 || records[1].Error != "queue full" {
		t.Fatalf("errors-only outcome lost: %+v %v", records, err)
	}
}

func TestEngineStandaloneAndNoPollCounts(t *testing.T) {
	for _, status := range []string{"queued", "succeeded"} {
		t.Run(status, func(t *testing.T) {
			dir := t.TempDir()
			data := []byte("standalone ingestion")
			if err := os.WriteFile(filepath.Join(dir, "doc.md"), data, 0600); err != nil {
				t.Fatal(err)
			}
			hash := sha256.Sum256(data)
			expectedSHA := hex.EncodeToString(hash[:])
			created, submitted := false, false
			server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
				if strings.HasPrefix(name, "long_") || name == "space_info" {
					return "Unknown tool: " + name, true
				}
				switch name {
				case "memory_list":
					return `{"status":"ok","memories":[]}`, false
				case "memory_create":
					if len(args) != 3 || args["memory_id"] != "demo" || args["ontology"] != "technical" {
						t.Errorf("incorrect create args: %v", args)
					}
					created = true
					return `{"status":"created"}`, false
				case "ingest_job_list":
					return `{"status":"ok","jobs":[]}`, false
				case "document_list":
					if len(args) != 1 || args["memory_id"] != "demo" {
						t.Errorf("incorrect catalog args: %v", args)
					}
					return fmt.Sprintf(`{"status":"ok","documents":[{"sha256":%q,"ingestion_status":"failed"}]}`, expectedSHA), false
				case "memory_ingest_batch_async":
					if len(args) != 3 || args["memory_id"] != "demo" || args["replace_existing"] != false {
						t.Errorf("incorrect batch args: %v", args)
					}
					docs := args["documents"].([]interface{})
					doc := docs[0].(map[string]interface{})
					if doc["content_base64"] != base64.StdEncoding.EncodeToString(data) || doc["sha256"] != expectedSHA || doc["source_path"] != "doc.md" || doc["filename"] != "doc.md" {
						t.Errorf("bad payload: %v", doc)
					}
					submitted = true
					return fmt.Sprintf(`{"status":"ok","items":[{"source_path":"doc.md","job_id":"j1","status":%q}]}`, status), false
				default:
					t.Errorf("unexpected call %s", name)
					return "unexpected", true
				}
			})
			defer server.Close()
			engine := NewEngine(mcpclient.NewClient(server.URL, "", time.Second))
			result, err := engine.Run(context.Background(), IngestOptions{Path: dir, SpaceID: "demo", Ontology: "technical", CreateSpaceIfMissing: true, AllowedExtensions: []string{".md"}}, nil)
			wantSucceeded := 0
			if status == "succeeded" {
				wantSucceeded = 1
			}
			if err != nil || !created || !submitted || !result.Success || result.TotalSucceeded != wantSucceeded || result.TotalUploaded != 1 {
				t.Fatalf("incorrect result: %+v err=%v", result, err)
			}
		})
	}
}

func TestCatalogFailClosedAndMissingFallback(t *testing.T) {
	for _, missing := range []bool{false, true} {
		t.Run(fmt.Sprint(missing), func(t *testing.T) {
			calls := 0
			server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
				calls++
				if missing {
					return "Unknown tool: " + name, true
				}
				return `{"status":"error","message":"access denied"}`, false
			})
			defer server.Close()
			_, err := NewEngine(mcpclient.NewClient(server.URL, "", time.Second)).FetchKnownHashes(context.Background(), "demo")
			if missing && (err != nil || calls != 2) {
				t.Fatalf("missing tool fallback: %d %v", calls, err)
			}
			if !missing && (err == nil || calls != 1) {
				t.Fatalf("real error retried or masked: %d %v", calls, err)
			}
		})
	}
}

func TestPollJobFallbackAndErrors(t *testing.T) {
	for _, test := range []struct {
		name, status string
		missing      bool
		wantErr      bool
	}{
		{"compatibility", "completed", true, false}, {"failure", "error", false, true}, {"unknown", "mystery", false, true}, {"cancelled", "cancelled", false, true}, {"skip", "changed_skipped", false, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			calls := 0
			server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
				calls++
				if test.missing && name != "ingest_job_status" {
					return "Unknown tool: " + name, true
				}
				if name == "ingest_job_status" && len(args) != 1 {
					t.Errorf("standalone status args: %v", args)
				}
				return fmt.Sprintf(`{"status":%q,"message":"test"}`, test.status), false
			})
			defer server.Close()
			_, err := NewEngine(mcpclient.NewClient(server.URL, "", time.Second)).PollJob(context.Background(), "demo", "j1", time.Second)
			if (err != nil) != test.wantErr {
				t.Fatalf("wrong error: %v", err)
			}
			wantCalls := 1
			if test.missing {
				wantCalls = 3
			}
			if calls != wantCalls {
				t.Fatalf("calls=%d want %d", calls, wantCalls)
			}
		})
	}
}
