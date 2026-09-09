package ingest

import (
	"context"
	"fmt"
	"strings"
	"time"

	"graph-memory-ingest/internal/mcpclient"
	"graph-memory-ingest/internal/scanner"
)

// ProgressCallback is invoked during scanning and ingestion for TUI/CLI updates
type ProgressCallback func(stage string, message string, current int, total int, file string, jobID string, status string, errStr string)

// IngestOptions configures an ingestion run
type IngestOptions struct {
	Path                 string
	SpaceID              string
	Ontology             string
	BatchSizeMB          int
	MaxFileBytes         int64
	AllowedExtensions    []string
	DryRun               bool
	ForceReplace         bool
	CreateSpaceIfMissing bool
	RulesTemplate        string
	WatchJobs            bool
	Timeout              time.Duration
	NonInteractive       bool
}

// IngestResult captures the overall outcome of an ingestion execution
type IngestResult struct {
	SpaceID        string       `json:"space_id"`
	TotalScanned   int          `json:"total_scanned"`
	TotalUploaded  int          `json:"total_uploaded"`
	TotalSkipped   int          `json:"total_skipped"`
	TotalSucceeded int          `json:"total_succeeded"`
	TotalFailed    int          `json:"total_failed"`
	BatchesCount   int          `json:"batches_count"`
	DurationMs     int64        `json:"duration_ms"`
	Jobs           []*JobRecord `json:"jobs"`
	Success        bool         `json:"success"`
}

// JobRecord represents the status of an ingested file/job
type JobRecord struct {
	JobID    string `json:"job_id"`
	Filename string `json:"filename"`
	SHA256   string `json:"sha256"`
	Status   string `json:"status"` // queued, running, succeeded, failed, skipped
	Error    string `json:"error,omitempty"`
}

// Engine coordinates scanning, space verification, batching, and async ingestion
type Engine struct {
	client *mcpclient.Client
}

// NewEngine creates a new Engine instance
func NewEngine(client *mcpclient.Client) *Engine {
	return &Engine{client: client}
}

// Run executes the ingestion workflow
func (e *Engine) Run(ctx context.Context, opts IngestOptions, callback ProgressCallback) (*IngestResult, error) {
	start := time.Now()
	res := &IngestResult{
		SpaceID: opts.SpaceID,
		Jobs:    make([]*JobRecord, 0),
	}

	report := func(stage, msg string, current, total int, file, jobID, status, errStr string) {
		if callback != nil {
			callback(stage, msg, current, total, file, jobID, status, errStr)
		}
	}

	// 1. Dry-run is 100% offline and local
	if opts.DryRun {
		report("scanning", fmt.Sprintf("Scanning %s locally (dry-run mode)...", opts.Path), 0, 0, "", "", "", "")
		scanRes, err := scanner.Scan(scanner.ScanOptions{
			RootPath:          opts.Path,
			AllowedExtensions: opts.AllowedExtensions,
			BatchSizeMB:       opts.BatchSizeMB,
			MaxFileBytes:      opts.MaxFileBytes,
			ForceReplace:      opts.ForceReplace,
		})
		if err != nil {
			return nil, fmt.Errorf("scanning failed: %w", err)
		}

		res.TotalScanned = scanRes.TotalFiles + scanRes.SkippedCount
		res.TotalSkipped = scanRes.SkippedCount
		res.BatchesCount = len(scanRes.Batches)

		for _, skippedPath := range scanRes.SkippedFiles {
			res.Jobs = append(res.Jobs, &JobRecord{
				Filename: skippedPath,
				Status:   "skipped",
			})
		}
		for _, b := range scanRes.Batches {
			for _, f := range b.Files {
				res.Jobs = append(res.Jobs, &JobRecord{
					Filename: f.RelPath,
					SHA256:   f.SHA256,
					Status:   "dry_run",
				})
			}
		}

		res.Success = true
		res.DurationMs = time.Since(start).Milliseconds()
		report("dry_run", fmt.Sprintf("Dry-run complete. Discovered %d files in %d batches.", scanRes.TotalFiles, len(scanRes.Batches)), scanRes.TotalFiles, scanRes.TotalFiles, "", "", "dry_run", "")
		return res, nil
	}

	// 2. Ensure space exists or auto-create if requested
	report("verifying_space", fmt.Sprintf("Verifying space '%s'...", opts.SpaceID), 0, 0, "", "", "", "")
	if err := e.EnsureSpace(ctx, opts.SpaceID, opts.CreateSpaceIfMissing, opts.RulesTemplate, opts.Ontology); err != nil {
		return nil, fmt.Errorf("space verification failed: %w", err)
	}

	// 3. Inspect active running jobs in space to notify operator
	activeJobs, _ := e.FetchActiveJobs(ctx, opts.SpaceID)
	if activeJobs > 0 {
		report("active_jobs", fmt.Sprintf("Notice: %d active ingestion job(s) in space '%s'.", activeJobs, opts.SpaceID), 0, 0, "", "", "", "")
	}

	// 4. Fetch known hashes for deduplication (unless force replace is specified)
	var knownHashes map[string]bool
	if !opts.ForceReplace {
		report("fetching_hashes", "Checking remote document catalog for SHA-256 deduplication...", 0, 0, "", "", "", "")
		hashes, err := e.FetchKnownHashes(ctx, opts.SpaceID)
		if err != nil {
			return nil, fmt.Errorf("failed to fetch remote document catalog: %w", err)
		}
		if len(hashes) > 0 {
			knownHashes = hashes
			report("hashes_loaded", fmt.Sprintf("Loaded %d existing document fingerprint(s).", len(hashes)), 0, 0, "", "", "", "")
		}
	}

	// 5. Scan directory
	report("scanning", fmt.Sprintf("Scanning %s...", opts.Path), 0, 0, "", "", "", "")
	scanRes, err := scanner.Scan(scanner.ScanOptions{
		RootPath:          opts.Path,
		AllowedExtensions: opts.AllowedExtensions,
		BatchSizeMB:       opts.BatchSizeMB,
		MaxFileBytes:      opts.MaxFileBytes,
		KnownHashes:       knownHashes,
		ForceReplace:      opts.ForceReplace,
	})
	if err != nil {
		return nil, fmt.Errorf("scanning failed: %w", err)
	}

	res.TotalScanned = scanRes.TotalFiles + scanRes.SkippedCount
	res.TotalSkipped = scanRes.SkippedCount
	res.BatchesCount = len(scanRes.Batches)

	for _, skippedPath := range scanRes.SkippedFiles {
		res.Jobs = append(res.Jobs, &JobRecord{
			Filename: skippedPath,
			Status:   "skipped",
		})
	}

	report("scanned", fmt.Sprintf("Discovered %d new files to ingest (%d skipped as unchanged).", scanRes.TotalFiles, scanRes.SkippedCount), scanRes.TotalFiles, scanRes.TotalFiles, "", "", "", "")

	if scanRes.TotalFiles == 0 {
		res.Success = true
		res.DurationMs = time.Since(start).Milliseconds()
		report("done", "No new files to ingest. Everything is up to date.", 0, 0, "", "", "finished", "")
		return res, nil
	}

	// 6. Ingestion per batch
	totalProcessed := 0
	for batchIdx, batch := range scanRes.Batches {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		default:
		}

		report("batch_starting", fmt.Sprintf("Processing batch [%d/%d] (%d files)...", batchIdx+1, len(scanRes.Batches), len(batch.Files)), totalProcessed, scanRes.TotalFiles, "", "", "uploading", "")

		batchJobs, err := e.IngestBatch(ctx, opts.SpaceID, batch, opts.Ontology, opts.MaxFileBytes, opts.ForceReplace)
		if err != nil {
			for _, file := range batch.Files {
				totalProcessed++
				res.TotalFailed++
				rec := &JobRecord{
					Filename: file.RelPath,
					SHA256:   file.SHA256,
					Status:   "failed",
					Error:    err.Error(),
				}
				res.Jobs = append(res.Jobs, rec)
				report("upload_failed", fmt.Sprintf("Failed batch on %s: %v", file.RelPath, err), totalProcessed, scanRes.TotalFiles, file.RelPath, "", "failed", err.Error())
			}
			continue
		}

		for _, jobRec := range batchJobs {
			totalProcessed++
			st := strings.ToLower(jobRec.Status)
			switch st {
			case "failed", "error", "queue_full", "cancelled", "rejected":
				jobRec.Status = "failed"
				res.TotalFailed++
				res.Jobs = append(res.Jobs, jobRec)
				report("upload_failed", fmt.Sprintf("Failed to upload %s: %s", jobRec.Filename, jobRec.Error), totalProcessed, scanRes.TotalFiles, jobRec.Filename, "", "failed", jobRec.Error)
			case "skipped", "changed_skipped":
				jobRec.Status = st
				res.TotalSkipped++
				res.Jobs = append(res.Jobs, jobRec)
				report("skipped", fmt.Sprintf("Skipped %s (%s)", jobRec.Filename, jobRec.Error), totalProcessed, scanRes.TotalFiles, jobRec.Filename, "", st, "")
			case "succeeded", "completed":
				jobRec.Status = "succeeded"
				res.TotalSucceeded++
				res.TotalUploaded++
				res.Jobs = append(res.Jobs, jobRec)
				report("uploaded", fmt.Sprintf("Uploaded %s", jobRec.Filename), totalProcessed, scanRes.TotalFiles, jobRec.Filename, jobRec.JobID, "succeeded", "")
			case "queued", "running", "processing", "pending", "in_progress":
				if jobRec.JobID == "" {
					jobRec.Status = "failed"
					jobRec.Error = "server returned pending status without job_id"
					res.TotalFailed++
					res.Jobs = append(res.Jobs, jobRec)
					report("upload_failed", fmt.Sprintf("Failed %s: missing job_id", jobRec.Filename), totalProcessed, scanRes.TotalFiles, jobRec.Filename, "", "failed", jobRec.Error)
				} else {
					res.TotalUploaded++
					res.Jobs = append(res.Jobs, jobRec)
					report("uploaded", fmt.Sprintf("Uploaded %s (Job ID: %s)", jobRec.Filename, jobRec.JobID), totalProcessed, scanRes.TotalFiles, jobRec.Filename, jobRec.JobID, jobRec.Status, "")
				}
			default:
				jobRec.Status = "failed"
				jobRec.Error = fmt.Sprintf("unrecognized job status '%s'", st)
				res.TotalFailed++
				res.Jobs = append(res.Jobs, jobRec)
				report("upload_failed", fmt.Sprintf("Failed %s: %s", jobRec.Filename, jobRec.Error), totalProcessed, scanRes.TotalFiles, jobRec.Filename, "", "failed", jobRec.Error)
			}
		}
	}

	// 7. Watch background jobs if requested
	if opts.WatchJobs && res.TotalUploaded > 0 {
		report("watching", "Monitoring background ingestion jobs...", 0, len(res.Jobs), "", "", "", "")
		for i, job := range res.Jobs {
			if job.Status == "skipped" || job.Status == "failed" || job.JobID == "" || job.Status == "succeeded" {
				continue
			}

			report("job_polling", fmt.Sprintf("Checking status for job %s (%s)...", job.JobID, job.Filename), i+1, len(res.Jobs), job.Filename, job.JobID, "polling", "")
			status, err := e.PollJob(ctx, opts.SpaceID, job.JobID, opts.Timeout)
			if err != nil {
				job.Status = "failed"
				job.Error = err.Error()
				res.TotalFailed++
				report("job_failed", fmt.Sprintf("Job %s failed: %v", job.JobID, err), i+1, len(res.Jobs), job.Filename, job.JobID, "failed", err.Error())
			} else {
				job.Status = status
				switch status {
				case "succeeded", "completed":
					res.TotalSucceeded++
					report("job_succeeded", fmt.Sprintf("Job %s succeeded (%s).", job.JobID, job.Filename), i+1, len(res.Jobs), job.Filename, job.JobID, "succeeded", "")
				case "skipped", "changed_skipped":
					res.TotalSkipped++
					report("skipped", fmt.Sprintf("Job %s skipped (%s).", job.JobID, job.Filename), i+1, len(res.Jobs), job.Filename, job.JobID, "skipped", "")
				default:
					res.TotalFailed++
					report("job_failed", fmt.Sprintf("Job %s ended with status: %s", job.JobID, status), i+1, len(res.Jobs), job.Filename, job.JobID, status, "")
				}
			}
		}
	}

	res.Success = res.TotalFailed == 0 && (!opts.WatchJobs || res.TotalSucceeded+res.TotalSkipped == res.TotalScanned)
	res.DurationMs = time.Since(start).Milliseconds()
	report("done", fmt.Sprintf("Run finished in %d ms (%d succeeded, %d failed).", res.DurationMs, res.TotalSucceeded, res.TotalFailed), res.TotalScanned, res.TotalScanned, "", "", "finished", "")
	return res, nil
}

// FetchActiveJobs inspects running and queued ingestion jobs on the space
func (e *Engine) FetchActiveJobs(ctx context.Context, spaceID string) (int, error) {
	res, err := e.client.CallTool(ctx, "long_ingest_list", map[string]interface{}{
		"space_id": spaceID,
		"status":   "running",
		"limit":    50,
	})
	if mcpclient.IsToolMissing(res, err, "long_ingest_list") {
		res, err = e.client.CallTool(ctx, "ingest_job_list", map[string]interface{}{"memory_id": spaceID, "status": "running"})
	}
	if err != nil || res["status"] == "error" || res["isError"] == true {
		return 0, nil
	}
	jobs, ok := res["jobs"].([]interface{})
	if !ok {
		return 0, nil
	}
	return len(jobs), nil
}

// EnsureSpace checks if space exists, creating it only on explicit not-found
func (e *Engine) EnsureSpace(ctx context.Context, spaceID string, createIfMissing bool, rulesTemplate string, ontology ...string) error {
	res, err := e.client.CallTool(ctx, "space_info", map[string]interface{}{"space_id": spaceID})
	if mcpclient.IsToolMissing(res, err, "space_info") {
		name := ""
		if len(ontology) > 0 {
			name = ontology[0]
		}
		return e.ensureGraphMemory(ctx, spaceID, createIfMissing, name)
	}
	if err == nil {
		if status, ok := res["status"].(string); ok && status == "ok" && res["isError"] != true {
			return nil
		}
		if status, ok := res["status"].(string); ok && status == "not_found" {
			if !createIfMissing {
				return fmt.Errorf("space %s does not exist (use --create-space-if-missing to create it automatically)", spaceID)
			}
			var rulesParam string
			if rulesTemplate != "" && rulesTemplate != "standard" {
				rulesParam = rulesTemplate
			}
			createRes, err := e.client.CallTool(ctx, "space_create", map[string]interface{}{
				"space_id":    spaceID,
				"description": fmt.Sprintf("Space for %s created by graph-memory-ingest", spaceID),
				"rules":       rulesParam,
			})
			if err != nil {
				return fmt.Errorf("space_create failed: %w", err)
			}
			createStatus, _ := createRes["status"].(string)
			if createRes["isError"] == true || (createStatus != "created" && createStatus != "already_exists") {
				return fmt.Errorf("space_create failed with status '%s': %v", createStatus, createRes["message"])
			}
			return nil
		}
		return fmt.Errorf("space verification returned status '%v': %v", res["status"], res["message"])
	}
	return fmt.Errorf("failed to verify space %s: %w", spaceID, err)
}

// FetchKnownHashes retrieves the list of SHA256 hashes already indexed in the space
func (e *Engine) FetchKnownHashes(ctx context.Context, spaceID string) (map[string]bool, error) {
	known := make(map[string]bool)
	limit := 100
	offset := 0
	standalone := false

	for {
		// Attempt to list documents using long_document_list (Issue #464)
		res, err := e.client.CallTool(ctx, "long_document_list", map[string]interface{}{
			"space_id": spaceID,
			"limit":    limit,
			"offset":   offset,
		})
		if mcpclient.IsToolMissing(res, err, "long_document_list") {
			standalone = true
			res, err = e.client.CallTool(ctx, "document_list", map[string]interface{}{"memory_id": spaceID})
			if mcpclient.IsToolMissing(res, err, "document_list") {
				return known, nil
			}
		}
		if err != nil {
			return nil, fmt.Errorf("failed to fetch document catalog: %w", err)
		}
		if res["status"] != "ok" || res["isError"] == true {
			return nil, fmt.Errorf("server error from document catalog: %v", res["message"])
		}

		rawDocs, ok := res["documents"].([]interface{})
		if !ok {
			return nil, fmt.Errorf("invalid or missing 'documents' array in space %s catalog response", spaceID)
		}
		if len(rawDocs) == 0 {
			break
		}

		for idx, item := range rawDocs {
			docMap, ok := item.(map[string]interface{})
			if !ok || docMap == nil {
				return nil, fmt.Errorf("malformed document entry at index %d in space %s catalog", idx, spaceID)
			}
			// Failed or unfinished documents must remain eligible for ingestion.
			if status, _ := docMap["ingestion_status"].(string); status != "" && status != "unknown" && status != "succeeded" && status != "completed" {
				continue
			}
			sha, ok := docMap["sha256"].(string)
			if standalone && sha == "" {
				sha, ok = docMap["hash"].(string)
			}
			if !ok || len(sha) != 64 || !isValidHex(sha) {
				return nil, fmt.Errorf("invalid sha256 checksum '%v' at index %d in space %s catalog", docMap["sha256"], idx, spaceID)
			}
			known[strings.ToLower(sha)] = true
		}

		if standalone || len(rawDocs) < limit {
			break
		}
		offset += len(rawDocs)
	}

	return known, nil
}

func isValidHex(s string) bool {
	for _, c := range s {
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')) {
			return false
		}
	}
	return true
}

// IngestBatch streams an entire batch of documents in a single long_ingest_async call
func (e *Engine) IngestBatch(ctx context.Context, spaceID string, batch scanner.Batch, ontology string, maxBytes int64, replace bool) ([]*JobRecord, error) {
	if len(batch.Files) == 0 {
		return nil, nil
	}

	docsPayload := make([]map[string]interface{}, 0, len(batch.Files))
	fileMap := make(map[string]scanner.FileItem)

	for _, file := range batch.Files {
		contentObj, err := scanner.LoadFileContent(file.Path, maxBytes)
		if err != nil {
			return nil, fmt.Errorf("failed to read file %s: %w", file.Path, err)
		}

		// Graph Memory backend strictly requires content_base64, filename, source_path, and sha256
		doc := map[string]interface{}{
			"source_path":    file.RelPath,
			"filename":       file.Filename,
			"sha256":         contentObj.SHA256,
			"content_base64": contentObj.Base64Data,
			"metadata": map[string]interface{}{
				"content_type": file.ContentType,
			},
		}

		docsPayload = append(docsPayload, doc)
		file.SHA256 = contentObj.SHA256
		fileMap[file.RelPath] = file
	}

	options := map[string]interface{}{
		"replace_existing": replace,
	}

	res, err := e.client.CallTool(ctx, "long_ingest_async", map[string]interface{}{
		"space_id":  spaceID,
		"documents": docsPayload,
		"options":   options,
	})
	if mcpclient.IsToolMissing(res, err, "long_ingest_async") {
		res, err = e.client.CallTool(ctx, "memory_ingest_batch_async", map[string]interface{}{
			"memory_id": spaceID, "documents": docsPayload, "replace_existing": replace,
		})
	}
	if err != nil {
		return nil, fmt.Errorf("long_ingest_async failed: %w", err)
	}

	if res["status"] == "error" || res["isError"] == true {
		msg, _ := res["message"].(string)
		if msg == "" {
			msg = "unknown error from long_ingest_async"
		}
		return nil, fmt.Errorf("%s", msg)
	}

	// Reconcile with the hashes of the bytes actually sent, even if a file changed after scanning.
	for i := range batch.Files {
		batch.Files[i] = fileMap[batch.Files[i].RelPath]
	}
	return ReconcileBatch(batch.Files, res)
}

// IngestFile streams a single file (used for single-file operations)
func (e *Engine) IngestFile(ctx context.Context, spaceID string, file scanner.FileItem, ontology string, maxBytes int64, replace bool) (*JobRecord, error) {
	batch := scanner.Batch{
		Files: []scanner.FileItem{file},
	}
	jobs, err := e.IngestBatch(ctx, spaceID, batch, ontology, maxBytes, replace)
	if err != nil {
		return nil, err
	}
	if len(jobs) == 0 {
		return nil, fmt.Errorf("no job returned for file %s", file.RelPath)
	}
	return jobs[0], nil
}

// PollJob monitors canonical terminal states. A real failure never triggers a compatibility retry.
func (e *Engine) PollJob(ctx context.Context, spaceID string, jobID string, timeout time.Duration) (string, error) {
	if timeout <= 0 {
		timeout = 10 * time.Minute
	}
	pollCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	for {
		args := map[string]interface{}{"space_id": spaceID, "job_id": jobID}
		res, err := e.client.CallTool(pollCtx, "long_ingest_status", args)
		if mcpclient.IsToolMissing(res, err, "long_ingest_status") {
			res, err = e.client.CallTool(pollCtx, "long_ingest_job_status", args)
			if mcpclient.IsToolMissing(res, err, "long_ingest_job_status") {
				res, err = e.client.CallTool(pollCtx, "ingest_job_status", map[string]interface{}{"job_id": jobID})
			}
		}
		if err != nil {
			return "failed", err
		}
		status, _ := res["status"].(string)
		if res["isError"] == true || status == "error" {
			return "failed", fmt.Errorf("job status error: %v", res["message"])
		}
		if state, _ := res["state"].(string); state != "" {
			status = state
		}
		switch strings.ToLower(status) {
		case "succeeded", "completed":
			return "succeeded", nil
		case "skipped", "changed_skipped":
			return status, nil
		case "failed", "error", "cancelled", "queue_full":
			message, _ := res["error"].(string)
			if message == "" {
				message, _ = res["message"].(string)
			}
			if message == "" {
				message = "ingestion job " + status
			}
			return status, fmt.Errorf("%s", message)
		case "queued", "running", "in_progress", "processing", "pending":
		default:
			return "failed", fmt.Errorf("unrecognized job status %q", status)
		}
		timer := time.NewTimer(time.Second)
		select {
		case <-pollCtx.Done():
			timer.Stop()
			return "cancelled", pollCtx.Err()
		case <-timer.C:
		}
	}
}

func (e *Engine) ensureGraphMemory(ctx context.Context, id string, create bool, ontology string) error {
	res, err := e.client.CallTool(ctx, "memory_list", map[string]interface{}{})
	if err != nil {
		return err
	}
	if res["status"] != "ok" || res["isError"] == true {
		return fmt.Errorf("memory_list failed: %v", res["message"])
	}
	memories, ok := res["memories"].([]interface{})
	if !ok {
		return fmt.Errorf("invalid memory_list response")
	}
	for _, raw := range memories {
		memory, ok := raw.(map[string]interface{})
		if !ok {
			return fmt.Errorf("invalid memory_list entry")
		}
		if memory["id"] == id {
			return nil
		}
	}
	if !create {
		return fmt.Errorf("memory %s not found (use --create-space-if-missing)", id)
	}
	if ontology == "" {
		return fmt.Errorf("--ontology is required to create a Graph Memory memory")
	}
	res, err = e.client.CallTool(ctx, "memory_create", map[string]interface{}{"memory_id": id, "name": id, "ontology": ontology})
	if err != nil {
		return err
	}
	if res["isError"] == true || (res["status"] != "created" && res["status"] != "already_exists") {
		return fmt.Errorf("memory_create failed: %v", res["message"])
	}
	return nil
}
