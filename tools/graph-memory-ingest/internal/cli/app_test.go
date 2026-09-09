package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"graph-memory-ingest/internal/config"
	"graph-memory-ingest/internal/mcpclient"
	"graph-memory-ingest/internal/tui"
)

func TestAppCLIEndToEnd(t *testing.T) {
	tempDir := t.TempDir()
	docFile := filepath.Join(tempDir, "manual.md")
	_ = os.WriteFile(docFile, []byte("# Project Manual\nArchitecture guide"), 0644)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req mcpclient.JSONRPCRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
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

		params, _ := req.Params.(map[string]interface{})
		name, _ := params["name"].(string)

		var resBody string
		switch name {
		case "system_whoami":
			resBody = `{"status":"ok","user":"ci-runner"}`
		case "space_info":
			resBody = `{"status":"ok","space_id":"test-space"}`
		case "space_create":
			resBody = `{"status":"created"}`
		case "space_delete":
			resBody = `{"status":"ok"}`
		case "long_ingest_list", "long_document_list":
			resBody = `{"status":"ok","documents":[]}`
		case "long_ingest_async", "long_ingest_document":
			resBody = `{"status":"ok","batch_id":"batch-1","total":1,"counts":{"queued":1},"items":[{"index":0,"source_path":"manual.md","job_id":"job-test-1","status":"queued"}],"errors":[]}`
		case "long_ingest_status", "long_ingest_job_status":
			resBody = `{"status":"succeeded","job_id":"job-test-1"}`
		case "ontology_validate":
			resBody = `{"status":"ok","valid":true}`
		case "long_status":
			resBody = `{"status":"ok","graph_stats":{"entities_count":2,"entity_types":{"Document":1,"Concept":1}}}`
		case "long_test_ontology":
			resBody = `{"status":"ok","entities":[{"name":"Project Manual","type":"Document"},{"name":"Architecture","type":"Concept"}],"relations":[]}`
		default:
			resBody = `{"status":"ok"}`
		}

		resp := mcpclient.JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result:  json.RawMessage(`{"content":[{"type":"text","text":` + string(mustJSON(resBody)) + `}],"isError":false}`),
		}
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	cfg := &config.Config{
		Endpoint:          server.URL,
		Token:             "ci-token",
		SpaceID:           "test-space",
		BatchSizeMB:       50,
		TimeoutSeconds:    10,
		WatchJobs:         true,
		ThresholdOther:    25,
		AllowedExtensions: []string{".md"},
	}

	var in bytes.Buffer
	var out bytes.Buffer
	ui := tui.NewUI(&in, &out)
	app := NewApp(ui, cfg)

	// 1. Test config test (code 0)
	out.Reset()
	code := app.Run(context.Background(), []string{"config", "test", "--json"})
	if code != ExitSuccess {
		t.Fatalf("config test failed with exit code %d, output: %s", code, out.String())
	}
	if !strings.Contains(out.String(), "ci-runner") {
		t.Errorf("expected output to contain ci-runner, got %s", out.String())
	}

	// 2. Test test-ontology (code 0)
	out.Reset()
	code = app.Run(context.Background(), []string{"test-ontology", "--path", tempDir, "--ontology", "software", "--json"})
	if code != ExitSuccess {
		t.Fatalf("test-ontology failed with exit code %d, output: %s", code, out.String())
	}
	if !strings.Contains(out.String(), `"passed_threshold": true`) {
		t.Errorf("expected passed_threshold true, got %s", out.String())
	}

	// 3. Test run dry-run (code 0)
	out.Reset()
	code = app.Run(context.Background(), []string{"run", "--path", tempDir, "--space", "test-space", "--dry-run", "--json"})
	if code != ExitSuccess {
		t.Fatalf("run --dry-run failed with code %d, output: %s", code, out.String())
	}
	if !strings.Contains(out.String(), `"total_scanned": 1`) {
		t.Errorf("expected total_scanned 1, got %s", out.String())
	}

	// 4. Test run real ingest with timeout flag (code 0)
	out.Reset()
	code = app.Run(context.Background(), []string{"run", "--path", tempDir, "--space", "test-space", "--timeout", "5", "--json"})
	if code != ExitSuccess {
		t.Fatalf("run failed with code %d, output: %s", code, out.String())
	}
	if !strings.Contains(out.String(), `"total_succeeded": 1`) {
		t.Errorf("expected total_succeeded 1, got %s", out.String())
	}

	// 5. Test validation error (code 1)
	out.Reset()
	code = app.Run(context.Background(), []string{"run", "--invalid-flag-123"})
	if code != ExitValidationError {
		t.Errorf("expected ExitValidationError (1) on invalid flag, got %d", code)
	}

	// 6. Test network error (code 2)
	out.Reset()
	code = app.Run(context.Background(), []string{"run", "--path", tempDir, "--space", "test-space", "--endpoint", "http://127.0.0.1:54321/down", "--non-interactive", "--json"})
	if code != ExitNetworkError {
		t.Errorf("expected ExitNetworkError (2) on network failure, got %d", code)
	}
}

func mustJSON(s string) []byte {
	b, _ := json.Marshal(s)
	return b
}
