package mcpclient

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func handleMockMCP(w http.ResponseWriter, r *http.Request, toolHandler func(req JSONRPCRequest) (json.RawMessage, bool, *JSONRPCError)) {
	var req JSONRPCRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}

	w.Header().Set("Content-Type", "application/json")

	if req.Method == "initialize" {
		w.Header().Set("mcp-session-id", "mock-session-12345")
		w.Header().Set("mcp-protocol-version", "2024-11-05")
		resp := JSONRPCResponse{
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
		res, _, rpcErr := toolHandler(req)
		if rpcErr != nil {
			resp := JSONRPCResponse{
				JSONRPC: "2.0",
				ID:      req.ID,
				Error:   rpcErr,
			}
			_ = json.NewEncoder(w).Encode(resp)
			return
		}
		resp := JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result:  res,
		}
		_ = json.NewEncoder(w).Encode(resp)
		return
	}

	resp := JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result:  json.RawMessage(`{"status":"ok"}`),
	}
	_ = json.NewEncoder(w).Encode(resp)
}

func TestClientCallToolSuccess(t *testing.T) {
	sessionReceived := false
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Errorf("missing or invalid Authorization header: %s", r.Header.Get("Authorization"))
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("invalid Content-Type: %s", r.Header.Get("Content-Type"))
		}

		if r.Header.Get("mcp-session-id") == "mock-session-12345" {
			sessionReceived = true
		}

		handleMockMCP(w, r, func(req JSONRPCRequest) (json.RawMessage, bool, *JSONRPCError) {
			return json.RawMessage(`{"content":[{"type":"text","text":"{\"status\":\"ok\",\"user\":\"operator\"}"}],"isError":false}`), false, nil
		})
	}))
	defer server.Close()

	client := NewClient(server.URL, "test-token", 10*time.Second)
	res, err := client.CallTool(context.Background(), "system_whoami", nil)
	if err != nil {
		t.Fatalf("CallTool failed: %v", err)
	}

	if res["status"] != "ok" {
		t.Errorf("expected status ok, got %v", res["status"])
	}
	if res["user"] != "operator" {
		t.Errorf("expected user operator, got %v", res["user"])
	}
	if !sessionReceived {
		t.Errorf("expected mcp-session-id header to be sent on tool calls after initialize")
	}
}

func TestClientCallToolServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handleMockMCP(w, r, func(req JSONRPCRequest) (json.RawMessage, bool, *JSONRPCError) {
			return nil, true, &JSONRPCError{
				Code:    -32000,
				Message: "Internal tool failure",
			}
		})
	}))
	defer server.Close()

	client := NewClient(server.URL, "test-token", 10*time.Second)
	_, err := client.CallTool(context.Background(), "fail_tool", nil)
	if err == nil {
		t.Fatalf("expected error from failed tool call, got nil")
	}
}

func TestClientCallToolIsError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handleMockMCP(w, r, func(req JSONRPCRequest) (json.RawMessage, bool, *JSONRPCError) {
			return json.RawMessage(`{"content":[{"type":"text","text":"Failed extraction on invalid document"}],"isError":true}`), true, nil
		})
	}))
	defer server.Close()

	client := NewClient(server.URL, "test-token", 10*time.Second)
	res, err := client.CallTool(context.Background(), "long_ingest_async", nil)
	if err != nil {
		t.Fatalf("unexpected transport error: %v", err)
	}
	if res["status"] != "error" || res["isError"] != true {
		t.Errorf("expected status=error and isError=true, got %+v", res)
	}
}

func TestClientCallToolEmptyContentIsError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handleMockMCP(w, r, func(req JSONRPCRequest) (json.RawMessage, bool, *JSONRPCError) {
			return json.RawMessage(`{"content":[],"isError":true}`), true, nil
		})
	}))
	defer server.Close()

	client := NewClient(server.URL, "test-token", 10*time.Second)
	res, err := client.CallTool(context.Background(), "some_tool", nil)
	if err != nil {
		t.Fatalf("unexpected transport error: %v", err)
	}
	if res["status"] != "error" || res["isError"] != true {
		t.Errorf("expected status=error and isError=true for empty content error, got %+v", res)
	}
}

func TestClientCallToolIDMismatch(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req JSONRPCRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		w.Header().Set("Content-Type", "application/json")
		if req.Method == "initialize" {
			resp := JSONRPCResponse{
				JSONRPC: "2.0",
				ID:      req.ID,
				Result:  json.RawMessage(`{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"test","version":"1.0"}}`),
			}
			_ = json.NewEncoder(w).Encode(resp)
			return
		}
		resp := JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      99999, // Mismatched ID
			Result:  json.RawMessage(`{"status":"ok"}`),
		}
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client := NewClient(server.URL, "test-token", 10*time.Second)
	_, err := client.CallTool(context.Background(), "some_tool", nil)
	if err == nil {
		t.Fatalf("expected ID mismatch error, got nil")
	}
}

func TestClientInitializeIncompatibleVersion(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req JSONRPCRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		w.Header().Set("Content-Type", "application/json")
		resp := JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result:  json.RawMessage(`{"protocolVersion":"1.0.0-legacy","capabilities":{"tools":{}},"serverInfo":{"name":"test","version":"1.0"}}`),
		}
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client := NewClient(server.URL, "test-token", 10*time.Second)
	_, err := client.CallTool(context.Background(), "some_tool", nil)
	if err == nil {
		t.Fatalf("expected incompatible protocol version error, got nil")
	}
	if !strings.Contains(err.Error(), "unsupported mcp protocol version") {
		t.Errorf("expected unsupported protocol version error message, got %v", err)
	}
}

func TestClientInitializeMissingToolsCapability(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req JSONRPCRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		w.Header().Set("Content-Type", "application/json")
		resp := JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result:  json.RawMessage(`{"protocolVersion":"2024-11-05","capabilities":{},"serverInfo":{"name":"test","version":"1.0"}}`),
		}
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client := NewClient(server.URL, "test-token", 10*time.Second)
	_, err := client.CallTool(context.Background(), "some_tool", nil)
	if err == nil {
		t.Fatalf("expected missing tools capability error, got nil")
	}
	if !strings.Contains(err.Error(), "does not declare 'tools' capability") {
		t.Errorf("expected missing tools capability error message, got %v", err)
	}
}

func TestClientInitializeNotificationRejected(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req JSONRPCRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		w.Header().Set("Content-Type", "application/json")
		if req.Method == "initialize" {
			resp := JSONRPCResponse{
				JSONRPC: "2.0",
				ID:      req.ID,
				Result:  json.RawMessage(`{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"test","version":"1.0"}}`),
			}
			_ = json.NewEncoder(w).Encode(resp)
			return
		}
		if req.Method == "notifications/initialized" {
			http.Error(w, "internal server error", http.StatusInternalServerError)
			return
		}
		resp := JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result:  json.RawMessage(`{"status":"ok"}`),
		}
		_ = json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client := NewClient(server.URL, "test-token", 10*time.Second)
	_, err := client.CallTool(context.Background(), "some_tool", nil)
	if err == nil {
		t.Fatalf("expected rejected notification error, got nil")
	}
	if !strings.Contains(err.Error(), "notifications/initialized rejected") {
		t.Errorf("expected rejected notification error message, got %v", err)
	}
}

func TestClientCallToolOversizedResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		// Write 17MB response (exceeding 16MB limit)
		chunk := strings.Repeat("A", 1024*1024)
		for i := 0; i < 17; i++ {
			_, _ = w.Write([]byte(chunk))
		}
	}))
	defer server.Close()

	client := NewClient(server.URL, "test-token", 10*time.Second)
	_, err := client.CallTool(context.Background(), "oversized_tool", nil)
	if err == nil {
		t.Fatalf("expected oversized response error, got nil")
	}
	if !strings.Contains(err.Error(), "exceeded maximum allowed size") {
		t.Errorf("expected maximum allowed size error, got %v", err)
	}
}

func TestClientCallToolSSEStreamResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req JSONRPCRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		if req.Method == "initialize" {
			w.Header().Set("Content-Type", "application/json")
			resp := JSONRPCResponse{
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
		w.Header().Set("Content-Type", "text/event-stream")
		sseData := fmt.Sprintf("event: message\ndata: {\"jsonrpc\":\"2.0\",\"id\":%d,\"result\":{\"status\":\"ok\",\"job_id\":\"job-sse-123\"}}\n\n", req.ID)
		_, _ = w.Write([]byte(sseData))
	}))
	defer server.Close()

	client := NewClient(server.URL, "test-token", 10*time.Second)
	res, err := client.CallTool(context.Background(), "test_sse", nil)
	if err != nil {
		t.Fatalf("unexpected error calling SSE tool: %v", err)
	}
	if res["status"] != "ok" || res["job_id"] != "job-sse-123" {
		t.Fatalf("unexpected result from SSE tool: %+v", res)
	}
}
