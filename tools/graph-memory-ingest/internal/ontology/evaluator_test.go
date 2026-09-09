package ontology

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

func TestEvaluator(t *testing.T) {
	tempDir := t.TempDir()
	docPath := filepath.Join(tempDir, "doc.md")
	_ = os.WriteFile(docPath, []byte("# Software Spec\nServer and Database"), 0644)

	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		switch name {
		case "ontology_validate":
			return `{"status":"ok","valid":true}`, false
		case "space_create":
			return `{"status":"created"}`, false
		case "long_ingest_async":
			return `{"status":"ok","batch_id":"batch-eval-1","total":1,"counts":{"queued":1},"items":[{"index":0,"source_path":"doc.md","job_id":"job-123","status":"queued"}],"errors":[]}`, false
		case "long_ingest_status":
			return `{"status":"succeeded"}`, false
		case "long_status":
			return `{"status":"ok","graph_stats":{"entities_count":3,"entity_types":{"Component":1,"Database":1,"Other":1}},"top_entities":[{"name":"Misc","type":"Other"}]}`, false
		case "space_delete":
			return `{"status":"ok"}`, false
		default:
			return `{"status":"ok"}`, false
		}
	})
	defer server.Close()

	client := mcpclient.NewClient(server.URL, "tok", 10*time.Second)
	eval := NewEvaluator(client)

	opts := EvalOptions{
		Ontology:       "entities:\n  - name: Component",
		SampleSize:     1,
		ThresholdOther: 40, // 1 Other out of 3 = 33.3% -> passes
	}

	res, err := eval.TestOntology(context.Background(), tempDir, opts)
	if err != nil {
		t.Fatalf("TestOntology failed: %v", err)
	}

	if !res.PassedThreshold {
		t.Errorf("expected PassedThreshold true, got false")
	}
	if res.TotalEntities != 3 {
		t.Errorf("expected 3 entities, got %d", res.TotalEntities)
	}
	if res.OtherEntities != 1 {
		t.Errorf("expected 1 other entity, got %d", res.OtherEntities)
	}
	if len(res.UnclassifiedConcepts) != 1 || res.UnclassifiedConcepts[0].Name != "Misc" {
		t.Errorf("expected 1 unclassified concept 'Misc', got %+v", res.UnclassifiedConcepts)
	}

	// Test failing threshold
	opts.ThresholdOther = 20 // 33.3% > 20% -> fails
	res2, err := eval.TestOntology(context.Background(), tempDir, opts)
	if err != nil {
		t.Fatalf("TestOntology2 failed: %v", err)
	}
	if res2.PassedThreshold {
		t.Errorf("expected PassedThreshold false, got true")
	}
}

func TestEvaluatorFailClosedOnServerError(t *testing.T) {
	tempDir := t.TempDir()
	docPath := filepath.Join(tempDir, "doc.md")
	_ = os.WriteFile(docPath, []byte("# Content"), 0644)

	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		return `{"status":"error","message":"LLM rate limit reached"}`, false
	})
	defer server.Close()

	client := NewEvaluator(mcpclient.NewClient(server.URL, "tok", 10*time.Second))
	_, err := client.TestOntology(context.Background(), tempDir, EvalOptions{
		Ontology:       "entities:\n  - name: Server",
		SampleSize:     1,
		ThresholdOther: 25,
	})
	if err == nil {
		t.Fatal("expected TestOntology to fail closed on server error, got nil")
	}
}

func TestEvaluatorRejectsInvalidYAML(t *testing.T) {
	tempDir := t.TempDir()
	docPath := filepath.Join(tempDir, "doc.md")
	_ = os.WriteFile(docPath, []byte("# Content"), 0644)

	server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
		return `{"status":"ok","valid":false,"errors":["missing entities section"]}`, false
	})
	defer server.Close()

	client := NewEvaluator(mcpclient.NewClient(server.URL, "tok", 10*time.Second))
	_, err := client.TestOntology(context.Background(), tempDir, EvalOptions{
		Ontology:       "invalid-yaml",
		SampleSize:     1,
		ThresholdOther: 25,
	})
	if err == nil {
		t.Fatal("expected TestOntology to fail closed on invalid YAML, got nil")
	}
}

func TestEvaluatorRejectsInvalidThreshold(t *testing.T) {
	client := NewEvaluator(mcpclient.NewClient("http://mock", "tok", 10*time.Second))
	_, err := client.TestOntology(context.Background(), ".", EvalOptions{
		ThresholdOther: 150, // Invalid > 100
	})
	if err == nil {
		t.Fatal("expected error on threshold > 100, got nil")
	}
}

func mustJSON(s string) []byte {
	b, _ := json.Marshal(s)
	return b
}
