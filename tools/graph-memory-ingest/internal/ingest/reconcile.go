package ingest

import (
	"fmt"
	"strings"

	"graph-memory-ingest/internal/scanner"
)

// ReconcileBatch requires exactly one outcome per submitted file and unique job IDs.
// errors[] may supplement a failed item, but cannot contradict an accepted item.
func ReconcileBatch(files []scanner.FileItem, res map[string]interface{}) ([]*JobRecord, error) {
	fileMap := make(map[string]scanner.FileItem, len(files))
	for _, f := range files {
		if _, duplicate := fileMap[f.RelPath]; duplicate || f.RelPath == "" {
			return nil, fmt.Errorf("duplicate or empty submitted source_path %q", f.RelPath)
		}
		fileMap[f.RelPath] = f
	}
	resolve := func(item map[string]interface{}) (string, error) {
		if path, _ := item["source_path"].(string); path != "" {
			if _, exists := fileMap[path]; !exists {
				return "", fmt.Errorf("unknown source_path %q in batch response", path)
			}
			return path, nil
		}
		name, _ := item["filename"].(string)
		path := ""
		for _, f := range files {
			if name != "" && (f.Filename == name || f.RelPath == name) {
				if path != "" {
					return "", fmt.Errorf("ambiguous filename %q in batch response", name)
				}
				path = f.RelPath
			}
		}
		if path == "" {
			return "", fmt.Errorf("unidentified file in batch response")
		}
		return path, nil
	}
	readArray := func(key string) ([]interface{}, error) {
		raw, exists := res[key]
		if !exists {
			return nil, nil
		}
		items, ok := raw.([]interface{})
		if !ok {
			return nil, fmt.Errorf("invalid %s array in batch response", key)
		}
		return items, nil
	}
	items, err := readArray("items")
	if err != nil {
		return nil, err
	}
	jobs, err := readArray("jobs")
	if err != nil {
		return nil, err
	}
	if len(items) > 0 && len(jobs) > 0 {
		return nil, fmt.Errorf("ambiguous items and jobs arrays")
	}
	if len(items) == 0 {
		items = jobs
	}
	if id, _ := res["job_id"].(string); id != "" {
		if len(files) != 1 || len(items) != 0 {
			return nil, fmt.Errorf("single job_id cannot identify this batch")
		}
		items = []interface{}{map[string]interface{}{"source_path": files[0].RelPath, "job_id": id, "status": res["status"]}}
	}
	errItems, err := readArray("errors")
	if err != nil {
		return nil, err
	}
	errorsByPath := make(map[string]string)
	for _, raw := range errItems {
		item, ok := raw.(map[string]interface{})
		if !ok {
			return nil, fmt.Errorf("invalid batch error entry")
		}
		path, err := resolve(item)
		if err != nil {
			return nil, err
		}
		if _, duplicate := errorsByPath[path]; duplicate {
			return nil, fmt.Errorf("duplicate error for %s", path)
		}
		message, _ := item["error"].(string)
		if message == "" {
			message, _ = item["message"].(string)
		}
		if message == "" {
			return nil, fmt.Errorf("missing error detail for %s", path)
		}
		errorsByPath[path] = message
	}
	records := make(map[string]*JobRecord, len(files))
	jobIDs := make(map[string]bool)
	for _, raw := range items {
		item, ok := raw.(map[string]interface{})
		if !ok {
			return nil, fmt.Errorf("invalid batch item")
		}
		path, err := resolve(item)
		if err != nil {
			return nil, err
		}
		if records[path] != nil {
			return nil, fmt.Errorf("duplicate outcome for %s", path)
		}
		id, _ := item["job_id"].(string)
		if id != "" && jobIDs[id] {
			return nil, fmt.Errorf("duplicate job_id %s", id)
		}
		if id != "" {
			jobIDs[id] = true
		}
		status, _ := item["status"].(string)
		status = strings.ToLower(status)
		rec := &JobRecord{Filename: path, SHA256: fileMap[path].SHA256, JobID: id, Status: status}
		switch status {
		case "succeeded", "completed", "skipped", "changed_skipped":
		case "queued", "running", "pending", "processing", "in_progress":
			if id == "" {
				return nil, fmt.Errorf("pending file %s without job_id", path)
			}
		case "failed", "error", "queue_full", "cancelled", "rejected":
			rec.Error, _ = item["error"].(string)
			if rec.Error == "" {
				rec.Error, _ = item["message"].(string)
			}
			if rec.Error == "" {
				rec.Error = errorsByPath[path]
			}
			if rec.Error == "" {
				rec.Error = "ingestion " + status
			}
		default:
			return nil, fmt.Errorf("unrecognized status %q for %s", status, path)
		}
		if errorsByPath[path] != "" && rec.Error == "" {
			return nil, fmt.Errorf("contradictory error and accepted outcome for %s", path)
		}
		records[path] = rec
	}
	ordered := make([]*JobRecord, 0, len(files))
	for _, file := range files {
		rec := records[file.RelPath]
		if rec == nil {
			message := errorsByPath[file.RelPath]
			if message == "" {
				return nil, fmt.Errorf("file %s unacknowledged in batch response", file.RelPath)
			}
			rec = &JobRecord{Filename: file.RelPath, SHA256: file.SHA256, Status: "failed", Error: message}
		}
		ordered = append(ordered, rec)
	}
	return ordered, nil
}
