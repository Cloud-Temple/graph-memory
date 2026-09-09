package ontology

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"graph-memory-ingest/internal/mcpclient"
)

func TestEvaluationCleanupAndFailClosed(t *testing.T) {
	for _, tc := range []struct {
		name      string
		keep      bool
		badStage  string
		wantError bool
	}{
		{"success", false, "", false}, {"keep", true, "", false},
		{"invalid YAML", false, "ontology_validate", true}, {"missing breakdown", false, "long_status", true},
		{"duplicate outcome", false, "long_ingest_async", true}, {"cleanup failure", false, "space_delete", true},
		{"creation denied", false, "space_create", true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			dir := t.TempDir()
			if err := os.WriteFile(filepath.Join(dir, "doc.md"), []byte("evaluation"), 0600); err != nil {
				t.Fatal(err)
			}
			deleted, created := 0, 0
			yaml := "entities:\n  - name: Server"
			server := newMockServer(func(name string, args map[string]interface{}) (string, bool) {
				if name == "space_create" {
					created++
					if !strings.HasPrefix(args["space_id"].(string), "tmp-eval-") {
						t.Error("space is not ephemeral")
					}
				}
				if name == "space_delete" {
					deleted++
				}
				if name == tc.badStage {
					switch name {
					case "ontology_validate":
						return `{"status":"ok","valid":false,"errors":["bad YAML"]}`, false
					case "long_status":
						return `{"status":"ok","graph_stats":{"entity_count":2}}`, false
					case "long_ingest_async":
						return `{"status":"ok","items":[{"source_path":"doc.md","status":"succeeded"},{"source_path":"doc.md","status":"succeeded"}]}`, false
					default:
						return `{"status":"error","message":"denied"}`, false
					}
				}
				switch name {
				case "space_create":
					return `{"status":"created"}`, false
				case "ontology_validate":
					if args["content_yaml"] != yaml {
						t.Error("YAML not passed to validator")
					}
					return `{"status":"ok","valid":true}`, false
				case "long_ingest_async":
					if args["options"].(map[string]interface{})["ontology_yaml"] != yaml {
						t.Error("YAML not passed to ingestion")
					}
					return `{"status":"ok","items":[{"source_path":"doc.md","status":"completed"}]}`, false
				case "long_status":
					return `{"status":"ok","graph_stats":{"entity_count":4,"entity_types":{"Server":2,"Other":1,"Generic":1}}}`, false
				case "space_delete":
					return `{"status":"deleted"}`, false
				default:
					t.Errorf("unexpected call %s", name)
					return "unexpected", true
				}
			})
			defer server.Close()
			res, err := NewEvaluator(mcpclient.NewClient(server.URL, "", time.Second)).Evaluate(context.Background(), EvalOptions{RootPath: dir, Ontology: yaml, ThresholdOther: 50, KeepMemory: tc.keep})
			if (err != nil) != tc.wantError {
				t.Fatalf("result=%+v err=%v", res, err)
			}
			if !tc.wantError && (res.OtherPercentage != 50 || !res.PassedThreshold || res.OtherEntities != 2) {
				t.Fatalf("wrong ratio %+v", res)
			}
			wantDeletes := 1
			if tc.keep || tc.badStage == "space_create" {
				wantDeletes = 0
			}
			if deleted != wantDeletes || created != 1 {
				t.Fatalf("created=%d deleted=%d want deletes=%d", created, deleted, wantDeletes)
			}
			if tc.badStage == "space_delete" && !strings.Contains(fmt.Sprint(err), "cleanup failed for space tmp-eval-") {
				t.Fatal("missing cleanup recovery information")
			}
		})
	}
}
