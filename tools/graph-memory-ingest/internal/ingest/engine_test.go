package ingest

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"graph-memory-ingest/internal/mcpclient"
	"graph-memory-ingest/internal/scanner"
)

func newMockServer(toolHandler func(name string, args map[string]interface{}) (string, bool)) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req mcpclient.JSONRPCRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")

		if req.Method == "initialize" {
			w.Header().Set("mcp-session-id", "mock-session-id")
			w.Header().Set("mcp-protocol-version", "2024-11-05")
			resp := mcpclient.JSONRPCResponse{
				JSONRPC: "2.0",
				ID:      req.ID,
				Result:  json.RawMessage(`{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"test","version":"1.0"}}`),
			}
			_ = json.NewEncoder(w).Encode(resp)
			return
		}

		if req.Method == "notifications/initialized" {
			w.WriteHeader(http.StatusOK)
			return
		}

		if req.Method == "tools/call" {
			params, _ := req.Params.(map[string]interface{})
			name, _ := params["name"].(string)
			args, _ := params["arguments"].(map[string]interface{})
			resBody, isErr := toolHandler(name, args)
			resp := mcpclient.JSONRPCResponse{
				JSONRPC: "2.0",
				ID:      req.ID,
				Result:  json.RawMessage(`{"content":[{"type":"text","text":` + string(mustJSON(resBody)) + `}],"isError":` + fmt.Sprintf("%t", isErr) + `}`),
			}
			_ = json.NewEncoder(w).Encode(resp)
			return
		}

		resp := mcpclient.JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result:  json.RawMessage(`{"status":"ok"}`),
		}
		_ = json.NewEncoder(w).Encode(resp)
	}))
}

func TestEngineRunSuccess(t *testing.T) {
	tempDir := t.TempDir()
	docPath := filepath.Join(tempDir, "sample.md")
	_ = os.WriteFile(docPath, []byte("# Test Document\nSome content"), 0644)

	jobPollCount := 0
	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		switch name {
		case "space_info":
			return `{"status":"ok","space_id":"demo-space"}`, false
		case "long_ingest_list", "long_document_list":
			return `{"status":"ok","documents":[]}`, false
		case "long_ingest_async":
			return `{"status":"ok","batch_id":"batch-123","total":1,"counts":{"queued":1},"items":[{"index":0,"source_path":"sample.md","job_id":"job-12345","status":"queued"}],"errors":[]}`, false
		case "long_ingest_status", "long_ingest_job_status":
			jobPollCount++
			if jobPollCount >= 2 {
				return `{"status":"succeeded","job_id":"job-12345"}`, false
			}
			return `{"status":"running","job_id":"job-12345"}`, false
		default:
			return `{"status":"ok"}`, false
		}
	})
	defer server.Close()

	client := mcpclient.NewClient(server.URL, "tok", 10*time.Second)
	engine := NewEngine(client)

	opts := IngestOptions{
		Path:              tempDir,
		SpaceID:           "demo-space",
		AllowedExtensions: []string{".md"},
		WatchJobs:         true,
		Timeout:           5 * time.Second,
	}

	res, err := engine.Run(context.Background(), opts, nil)
	if err != nil {
		t.Fatalf("engine.Run failed: %v", err)
	}

	if !res.Success {
		t.Errorf("expected success true, got false")
	}
	if res.TotalUploaded != 1 {
		t.Errorf("expected 1 uploaded file, got %d", res.TotalUploaded)
	}
	if res.TotalSucceeded != 1 {
		t.Errorf("expected 1 succeeded file, got %d", res.TotalSucceeded)
	}
}

func TestEngineAsyncJobFailure(t *testing.T) {
	tempDir := t.TempDir()
	docPath := filepath.Join(tempDir, "corrupted.md")
	_ = os.WriteFile(docPath, []byte("# Corrupted Document"), 0644)

	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		switch name {
		case "space_info":
			return `{"status":"ok","space_id":"demo-space"}`, false
		case "long_ingest_list", "long_document_list":
			return `{"status":"ok","documents":[]}`, false
		case "long_ingest_async":
			return `{"status":"ok","batch_id":"batch-123","total":1,"counts":{"queued":1},"items":[{"index":0,"source_path":"corrupted.md","job_id":"job-fail-99","status":"queued"}],"errors":[]}`, false
		case "long_ingest_status", "long_ingest_job_status":
			return `{"status":"failed","job_id":"job-fail-99","error":"graph extraction memory limit exceeded"}`, false
		default:
			return `{"status":"ok"}`, false
		}
	})
	defer server.Close()

	client := mcpclient.NewClient(server.URL, "tok", 10*time.Second)
	engine := NewEngine(client)

	opts := IngestOptions{
		Path:              tempDir,
		SpaceID:           "demo-space",
		AllowedExtensions: []string{".md"},
		WatchJobs:         true,
		Timeout:           5 * time.Second,
	}

	res, err := engine.Run(context.Background(), opts, nil)
	if err != nil {
		t.Fatalf("engine.Run should not error at top-level on partial job failure, got: %v", err)
	}

	if res.Success {
		t.Errorf("expected success false on failed job, got true")
	}
	if res.TotalFailed != 1 {
		t.Errorf("expected 1 failed job, got %d", res.TotalFailed)
	}
	if len(res.Jobs) != 1 || res.Jobs[0].Error != "graph extraction memory limit exceeded" {
		t.Errorf("expected job error captured, got: %+v", res.Jobs)
	}
}

func TestEngineDeduplicationAndForceReplace(t *testing.T) {
	tempDir := t.TempDir()
	docPath := filepath.Join(tempDir, "existing.md")
	content := []byte("# Existing Document")
	_ = os.WriteFile(docPath, content, 0644)

	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		switch name {
		case "space_info":
			return `{"status":"ok","space_id":"demo-space"}`, false
		case "long_ingest_list", "long_document_list":
			// Valid 64-char SHA-256 of "# Existing Document"
			return `{"status":"ok","documents":[{"filename":"existing.md","sha256":"88e62a89c10acc7f3ec78ff2df1b2a47386b7a36310a1372ee50a95125857486"}]}`, false
		case "long_ingest_async":
			return `{"status":"ok","batch_id":"batch-123","total":1,"counts":{"queued":1},"items":[{"index":0,"source_path":"existing.md","job_id":"job-replace","status":"queued"}],"errors":[]}`, false
		case "long_ingest_status":
			return `{"status":"succeeded","job_id":"job-replace"}`, false
		default:
			return `{"status":"ok"}`, false
		}
	})
	defer server.Close()

	client := mcpclient.NewClient(server.URL, "tok", 10*time.Second)
	engine := NewEngine(client)

	// 1. Without ForceReplace: should be skipped
	opts := IngestOptions{
		Path:              tempDir,
		SpaceID:           "demo-space",
		AllowedExtensions: []string{".md"},
		ForceReplace:      false,
	}
	res, err := engine.Run(context.Background(), opts, nil)
	if err != nil {
		t.Fatalf("Run failed: %v", err)
	}
	if res.TotalSkipped != 1 {
		t.Errorf("expected 1 skipped file, got %d", res.TotalSkipped)
	}
	if res.TotalUploaded != 0 {
		t.Errorf("expected 0 uploaded files, got %d", res.TotalUploaded)
	}

	// 2. With ForceReplace: should upload even if hash is known
	opts.ForceReplace = true
	res2, err := engine.Run(context.Background(), opts, nil)
	if err != nil {
		t.Fatalf("Run with ForceReplace failed: %v", err)
	}
	if res2.TotalUploaded != 1 {
		t.Errorf("expected 1 uploaded file with ForceReplace, got %d", res2.TotalUploaded)
	}
}

func TestEngineMissingSpaceFailClosed(t *testing.T) {
	tempDir := t.TempDir()
	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		return `{"status":"not_found","message":"space not found"}`, false
	})
	defer server.Close()

	client := mcpclient.NewClient(server.URL, "tok", 10*time.Second)
	engine := NewEngine(client)

	opts := IngestOptions{
		Path:                 tempDir,
		SpaceID:              "non-existent-space",
		CreateSpaceIfMissing: false,
	}

	_, err := engine.Run(context.Background(), opts, nil)
	if err == nil {
		t.Fatal("expected error on missing space when CreateSpaceIfMissing is false, got nil")
	}
}

func TestEngineAuthErrorDoesNotCreateSpace(t *testing.T) {
	tempDir := t.TempDir()
	spaceCreateCalled := false

	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		if name == "space_create" {
			spaceCreateCalled = true
		}
		return `{"status":"error","message":"Access denied to space 'secret-space'"}`, false
	})
	defer server.Close()

	client := mcpclient.NewClient(server.URL, "tok", 10*time.Second)
	engine := NewEngine(client)

	opts := IngestOptions{
		Path:                 tempDir,
		SpaceID:              "secret-space",
		CreateSpaceIfMissing: true, // Even if requested, must fail closed on auth error without calling space_create
	}

	_, err := engine.Run(context.Background(), opts, nil)
	if err == nil {
		t.Fatal("expected error on auth denied space, got nil")
	}
	if spaceCreateCalled {
		t.Fatal("space_create was called on auth error; expected fail-closed behavior")
	}
}

func TestEngineSpaceCreatePartialFails(t *testing.T) {
	tempDir := t.TempDir()
	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		switch name {
		case "space_info":
			return `{"status":"not_found","message":"space does not exist"}`, false
		case "space_create":
			// Return partial status (recovery required)
			return `{"status":"partial","message":"Space creation incomplete, recovery required"}`, false
		default:
			return `{"status":"ok"}`, false
		}
	})
	defer server.Close()

	client := mcpclient.NewClient(server.URL, "tok", 10*time.Second)
	engine := NewEngine(client)

	opts := IngestOptions{
		Path:                 tempDir,
		SpaceID:              "partial-space",
		CreateSpaceIfMissing: true,
	}

	_, err := engine.Run(context.Background(), opts, nil)
	if err == nil {
		t.Fatal("expected Run to fail when space_create returns status: partial, got nil")
	}
}

func TestEngineMalformedCatalogEntryFailClosed(t *testing.T) {
	tempDir := t.TempDir()
	docPath := filepath.Join(tempDir, "doc.md")
	_ = os.WriteFile(docPath, []byte("# Doc"), 0644)

	ingestCalled := false
	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		switch name {
		case "space_info":
			return `{"status":"ok","space_id":"demo-space"}`, false
		case "long_ingest_list", "long_document_list":
			// Catalog entry with invalid (non-64 hex) sha256 checksum
			return `{"status":"ok","documents":[{"filename":"bad.md","sha256":"invalid_short_hash"}]}`, false
		case "long_ingest_async":
			ingestCalled = true
			return `{"status":"ok"}`, false
		default:
			return `{"status":"ok"}`, false
		}
	})
	defer server.Close()

	client := mcpclient.NewClient(server.URL, "tok", 10*time.Second)
	engine := NewEngine(client)

	opts := IngestOptions{
		Path:    tempDir,
		SpaceID: "demo-space",
	}

	_, err := engine.Run(context.Background(), opts, nil)
	if err == nil {
		t.Fatal("expected Run to fail closed on malformed catalog sha256, got nil")
	}
	if ingestCalled {
		t.Fatal("long_ingest_async was called despite malformed catalog SHA256; expected fail-closed")
	}
}

func TestEngineBatchIngestionContractItemsAndErrors(t *testing.T) {
	tempDir := t.TempDir()
	doc1 := filepath.Join(tempDir, "ok.md")
	doc2 := filepath.Join(tempDir, "fail.md")
	_ = os.WriteFile(doc1, []byte("# OK file"), 0644)
	_ = os.WriteFile(doc2, []byte("# Fail file"), 0644)

	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		if name == "long_ingest_async" {
			// Verify payload contains content_base64
			docs, _ := args["documents"].([]interface{})
			if len(docs) != 2 {
				return fmt.Sprintf(`{"status":"error","message":"expected 2 docs, got %d"}`, len(docs)), false
			}
			for _, dRaw := range docs {
				d, _ := dRaw.(map[string]interface{})
				if d["content_base64"] == nil || d["content_base64"] == "" {
					return `{"status":"error","message":"missing content_base64 in document payload"}`, false
				}
			}

			// Return canonical memory_ingest_batch_async response with mixed items & errors
			return `{
				"status": "ok",
				"batch_id": "batch-mix",
				"total": 2,
				"counts": {"queued": 1, "failed": 1},
				"items": [
					{"index": 0, "source_path": "ok.md", "job_id": "job-ok-1", "status": "queued"},
					{"index": 1, "source_path": "fail.md", "status": "error", "message": "unsupported binary format"}
				],
				"errors": [
					{"source_path": "fail.md", "filename": "fail.md", "error": "unsupported binary format"}
				]
			}`, false
		}
		return `{"status":"ok"}`, false
	})
	defer server.Close()

	client := mcpclient.NewClient(server.URL, "tok", 10*time.Second)
	engine := NewEngine(client)

	batch := scanner.Batch{
		Files: []scanner.FileItem{
			{Path: doc1, RelPath: "ok.md", Filename: "ok.md", SHA256: "abc1"},
			{Path: doc2, RelPath: "fail.md", Filename: "fail.md", SHA256: "abc2"},
		},
	}

	records, err := engine.IngestBatch(context.Background(), "demo-space", batch, "", 10*1024*1024, false)
	if err != nil {
		t.Fatalf("IngestBatch failed: %v", err)
	}

	if len(records) != 2 {
		t.Fatalf("expected 2 job records, got %d", len(records))
	}

	var okRec, failRec *JobRecord
	for _, r := range records {
		if r.Filename == "ok.md" {
			okRec = r
		} else if r.Filename == "fail.md" {
			failRec = r
		}
	}

	if okRec == nil || okRec.JobID != "job-ok-1" || okRec.Status != "queued" {
		t.Errorf("okRec mismatch: %+v", okRec)
	}
	if failRec == nil || failRec.Status != "error" || failRec.Error != "unsupported binary format" {
		t.Errorf("failRec mismatch: %+v", failRec)
	}
}

func mustJSON(s string) []byte {
	b, _ := json.Marshal(s)
	return b
}
