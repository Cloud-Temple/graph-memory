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

func TestSSEStopsAtResponseAfterNotifications(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req JSONRPCRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		if req.Method == "notifications/initialized" {
			w.WriteHeader(202)
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		result := `{"content":[],"structuredContent":{"status":"ok","value":42}}`
		if req.Method == "initialize" {
			w.Header().Set("Mcp-Session-Id", "sse-session")
			w.Header().Set("Mcp-Protocol-Version", "2024-10-07")
			result = `{"protocolVersion":"2024-10-07","capabilities":{"tools":{}},"serverInfo":{"name":"test"}}`
		} else if r.Header.Get("Mcp-Session-Id") != "sse-session" || r.Header.Get("Mcp-Protocol-Version") != "2024-10-07" {
			t.Error("negotiated headers missing")
		}
		fmt.Fprint(w, ": heartbeat\r\ndata: {\"jsonrpc\":\"2.0\",\"method\":\"notifications/message\"}\r\n\r\n")
		fmt.Fprintf(w, "event: message\r\ndata: {\"jsonrpc\":\"2.0\",\"id\":%d,\r\ndata: \"result\":%s}\r\n\r\n", req.ID, result)
		w.(http.Flusher).Flush()
		// Stream stays open: waiting for EOF instead of the response would time out.
		<-r.Context().Done()
	}))
	defer server.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	result, err := NewClient(server.URL, "", time.Second).CallTool(ctx, "example", map[string]interface{}{})
	if err != nil || result["value"] != float64(42) {
		t.Fatalf("result=%v err=%v", result, err)
	}
}

func TestMissingToolDoesNotMaskOperationalErrors(t *testing.T) {
	for _, message := range []string{"access denied", "Unknown tool: another_tool", "long_document_list backend not found", "database error: unknown tool: long_document_list is unavailable"} {
		if IsToolMissing(map[string]interface{}{"status": "error", "message": message}, nil, "long_document_list") {
			t.Errorf("masked %s", message)
		}
	}
	_, err := readJSONRPCResponse("text/event-stream", strings.NewReader("data: {\"jsonrpc\":\"2.0\",\"id\":9,\"result\":{}}\n\n"), 2)
	if err == nil {
		t.Fatal("accepted wrong SSE response id")
	}
}
