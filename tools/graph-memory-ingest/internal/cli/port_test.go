package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"graph-memory-ingest/internal/config"
	"graph-memory-ingest/internal/mcpclient"
	"graph-memory-ingest/internal/tui"
)

func TestHelpDoesNotExposeConfiguredToken(t *testing.T) {
	cfg := config.DefaultConfig()
	cfg.Token = "secret-that-must-not-appear"
	var output bytes.Buffer
	app := NewApp(tui.NewUI(strings.NewReader(""), &output), cfg)
	file, err := os.CreateTemp(t.TempDir(), "stderr")
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	original := os.Stderr
	os.Stderr = file
	defer func() { os.Stderr = original }()
	app.Run(context.Background(), []string{"run", "--help"})
	data, err := os.ReadFile(file.Name())
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(data)+output.String(), cfg.Token) {
		t.Fatal("help leaked the configured token")
	}
}

func TestConfigTestRejectsToolError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req mcpclient.JSONRPCRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		if req.Method == "notifications/initialized" {
			w.WriteHeader(202)
			return
		}
		result := json.RawMessage(`{"content":[{"type":"text","text":"denied"}],"isError":true}`)
		if req.Method == "initialize" {
			result = json.RawMessage(`{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"test"}}`)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(mcpclient.JSONRPCResponse{JSONRPC: "2.0", ID: req.ID, Result: result})
	}))
	defer server.Close()
	cfg := config.DefaultConfig()
	cfg.Endpoint = server.URL
	var output bytes.Buffer
	code := NewApp(tui.NewUI(strings.NewReader(""), &output), cfg).Run(context.Background(), []string{"config", "test", "--json"})
	if code != ExitNetworkError || !strings.Contains(output.String(), `"status": "error"`) {
		t.Fatalf("false positive connection test: code=%d %s", code, output.String())
	}
}
