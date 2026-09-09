package ontology

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"math"
	"math/big"
	"os"
	"strings"
	"time"

	"graph-memory-ingest/internal/ingest"
	"graph-memory-ingest/internal/mcpclient"
	"graph-memory-ingest/internal/scanner"
)

// EvalOptions configures the ontology adequacy evaluation
type EvalOptions struct {
	RootPath          string   `json:"root_path"`
	SpaceID           string   `json:"space_id"`
	Ontology          string   `json:"ontology"`
	SampleSize        int      `json:"sample_size"`
	ThresholdOther    int      `json:"threshold_other"`
	KeepMemory        bool     `json:"keep_memory"`
	AllowedExtensions []string `json:"allowed_extensions"`
	AllowedExts       []string `json:"allowed_exts"` // alias
	MaxFileBytes      int64    `json:"max_file_bytes"`
}

// UnclassifiedConcept holds information about an untyped entity
type UnclassifiedConcept struct {
	Name      string   `json:"name"`
	Frequency int      `json:"frequency,omitempty"`
	Sources   []string `json:"sources,omitempty"`
}

// EvalResult contains the complete adequacy assessment and actionable report
type EvalResult struct {
	OntologyPath         string                `json:"ontology_path"`
	SpaceID              string                `json:"space_id"`
	IsTemporarySpace     bool                  `json:"is_temporary_space"`
	SampleCount          int                   `json:"sample_count"`
	SampleFiles          []string              `json:"sample_files"`
	TotalEntities        int                   `json:"total_entities"`
	TypedEntities        int                   `json:"typed_entities"`
	OtherEntities        int                   `json:"other_entities"`
	OtherPercentage      float64               `json:"other_percentage"`
	RelevanceTier        string                `json:"relevance_tier"` // Excellent (<1%), Very Good (<5%), Moderate (<10%), Inadequate (>=10%)
	EntityTypesBreakdown map[string]int        `json:"entity_types_breakdown,omitempty"`
	UnclassifiedConcepts []UnclassifiedConcept `json:"unclassified_concepts,omitempty"`
	ThresholdOther       int                   `json:"threshold_other"`
	PassedThreshold      bool                  `json:"passed_threshold"`
	ExtractionStatus     string                `json:"extraction_status"`
	Message              string                `json:"message"`
	Suggestions          []string              `json:"suggestions,omitempty"`
}

// Evaluator evaluates ontology fit against document samples
type Evaluator struct {
	client *mcpclient.Client
}

// NewEvaluator creates a new Evaluator instance
func NewEvaluator(client *mcpclient.Client) *Evaluator {
	return &Evaluator{client: client}
}

// TestOntology is the primary entry point for ontology evaluation
func (e *Evaluator) TestOntology(ctx context.Context, rootPath string, opts EvalOptions) (*EvalResult, error) {
	opts.RootPath = rootPath
	if len(opts.AllowedExtensions) == 0 && len(opts.AllowedExts) > 0 {
		opts.AllowedExtensions = opts.AllowedExts
	}
	return e.Evaluate(ctx, opts)
}

// Evaluate performs real end-to-end evaluation using an ephemeral space and graph_status
func (e *Evaluator) Evaluate(ctx context.Context, opts EvalOptions) (result *EvalResult, resultErr error) {
	if opts.SampleSize <= 0 {
		opts.SampleSize = 5
	}
	if opts.ThresholdOther < 0 || opts.ThresholdOther > 100 {
		return nil, fmt.Errorf("threshold-other must be between 0 and 100, got %d", opts.ThresholdOther)
	}

	// 1. Read ontology YAML (from file path or raw string)
	var ontologyYAML string
	if opts.Ontology != "" {
		if fileInfo, err := os.Stat(opts.Ontology); err == nil && fileInfo.Mode().IsRegular() {
			data, err := os.ReadFile(opts.Ontology)
			if err != nil {
				return nil, fmt.Errorf("failed to read ontology YAML file %s: %w", opts.Ontology, err)
			}
			ontologyYAML = string(data)
		} else {
			ontologyYAML = opts.Ontology
		}
	}

	allowedExts := opts.AllowedExtensions
	if len(allowedExts) == 0 && len(opts.AllowedExts) > 0 {
		allowedExts = opts.AllowedExts
	}

	// 2. Discover sample documents in the path
	scanRes, err := scanner.Scan(scanner.ScanOptions{
		RootPath:          opts.RootPath,
		AllowedExtensions: allowedExts,
		BatchSizeMB:       50,
		MaxFileBytes:      opts.MaxFileBytes,
		ForceReplace:      true,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to scan path %s: %w", opts.RootPath, err)
	}

	if scanRes.TotalFiles == 0 {
		return nil, fmt.Errorf("no valid files found in path %s for ontology evaluation", opts.RootPath)
	}

	// Select sample files
	var sampleItems []scanner.FileItem
	var sampleNames []string
	for _, b := range scanRes.Batches {
		for _, f := range b.Files {
			sampleItems = append(sampleItems, f)
			sampleNames = append(sampleNames, f.RelPath)
			if len(sampleItems) >= opts.SampleSize {
				break
			}
		}
		if len(sampleItems) >= opts.SampleSize {
			break
		}
	}

	// 3. Create target space (ephemeral by default)
	targetSpace := opts.SpaceID
	isTemp := false
	if targetSpace == "" {
		isTemp = true
		for attempt := 0; attempt < 5; attempt++ {
			rVal, err := rand.Int(rand.Reader, big.NewInt(100000))
			if err != nil {
				return nil, err
			}
			candidate := fmt.Sprintf("tmp-eval-%d-%05d", time.Now().Unix(), rVal.Int64())
			createRes, err := e.client.CallTool(ctx, "space_create", map[string]interface{}{
				"space_id":    candidate,
				"description": fmt.Sprintf("Ephemeral ontology evaluation space for %s", opts.RootPath),
				"rules":       "",
			})
			if mcpclient.IsToolMissing(createRes, err, "space_create") {
				return nil, fmt.Errorf("ontology evaluation requires Hivemind space_create, ontology_validate and long_status; Graph Memory standalone does not expose this workflow")
			}
			if err != nil {
				return nil, fmt.Errorf("space_create failed for %s: %w", candidate, err)
			}
			if createRes["status"] == "created" && createRes["isError"] != true {
				targetSpace = candidate
				break
			}
			if createRes["status"] != "already_exists" {
				return nil, fmt.Errorf("space_create failed: %v", createRes["message"])
			}
		}
		if targetSpace == "" {
			return nil, fmt.Errorf("failed to create unique ephemeral space after multiple attempts")
		}
	} else {
		createRes, err := e.client.CallTool(ctx, "space_create", map[string]interface{}{
			"space_id":    targetSpace,
			"description": fmt.Sprintf("Evaluation space for %s", opts.RootPath),
			"rules":       "",
		})
		if err != nil {
			return nil, fmt.Errorf("failed to create evaluation space %s: %w", targetSpace, err)
		}
		createStatus, _ := createRes["status"].(string)
		if createStatus != "created" || createRes["isError"] == true {
			return nil, fmt.Errorf("evaluation requires a new, empty space; space %s returned status '%s': %v", targetSpace, createStatus, createRes["message"])
		}
	}

	// Install cleanup hook immediately upon space creation
	defer func() {
		if !opts.KeepMemory {
			cleanCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			cleanRes, cleanErr := e.client.CallTool(cleanCtx, "space_delete", map[string]interface{}{
				"space_id": targetSpace,
				"confirm":  true,
			})
			if cleanErr == nil && (cleanRes["isError"] == true || (cleanRes["status"] != "ok" && cleanRes["status"] != "deleted")) {
				cleanErr = fmt.Errorf("%v", cleanRes["message"])
			}
			if cleanErr != nil {
				resultErr = errors.Join(resultErr, fmt.Errorf("cleanup failed for space %s: %w", targetSpace, cleanErr))
			}
		}
	}()

	// Validate ontology YAML with ontology_validate in context of the created space
	if ontologyYAML != "" {
		valRes, err := e.client.CallTool(ctx, "ontology_validate", map[string]interface{}{
			"space_id":     targetSpace,
			"content_yaml": ontologyYAML,
		})
		if err != nil {
			return nil, fmt.Errorf("ontology validation request failed: %w", err)
		}
		if valRes["status"] == "error" || valRes["isError"] == true {
			return nil, fmt.Errorf("invalid ontology YAML: %v", valRes["message"])
		}
		if valid, ok := valRes["valid"].(bool); !ok || !valid {
			return nil, fmt.Errorf("ontology schema is invalid: %v", valRes["errors"])
		}
	}

	// 4. Load sample contents and submit ingestion
	var docPayloads []map[string]interface{}
	for _, item := range sampleItems {
		contentObj, err := scanner.LoadFileContent(item.Path, opts.MaxFileBytes)
		if err != nil {
			return nil, fmt.Errorf("failed to load sample %s: %w", item.Path, err)
		}

		doc := map[string]interface{}{
			"source_path":    item.RelPath,
			"filename":       item.Filename,
			"sha256":         contentObj.SHA256,
			"content_base64": contentObj.Base64Data,
			"metadata": map[string]interface{}{
				"content_type": item.ContentType,
			},
		}
		docPayloads = append(docPayloads, doc)
	}

	ingestOpts := map[string]interface{}{}
	if ontologyYAML != "" {
		ingestOpts["ontology_yaml"] = ontologyYAML
	}

	ingestRes, err := e.client.CallTool(ctx, "long_ingest_async", map[string]interface{}{
		"space_id":  targetSpace,
		"documents": docPayloads,
		"options":   ingestOpts,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to submit sample ingestion: %w", err)
	}
	if ingestRes["status"] == "error" || ingestRes["isError"] == true {
		return nil, fmt.Errorf("ingestion error on evaluation: %v", ingestRes["message"])
	}

	records, err := ingest.ReconcileBatch(sampleItems, ingestRes)
	if err != nil {
		return nil, fmt.Errorf("invalid sample ingestion response: %w", err)
	}
	engine := ingest.NewEngine(e.client)
	for _, job := range records {
		if job.Error != "" {
			return nil, fmt.Errorf("sample ingestion failed for %s: %s", job.Filename, job.Error)
		}
		switch job.Status {
		case "succeeded", "completed", "skipped", "changed_skipped":
		default:
			if _, err := engine.PollJob(ctx, targetSpace, job.JobID, 0); err != nil {
				return nil, fmt.Errorf("sample ingestion job %s failed: %w", job.JobID, err)
			}
		}
	}

	// 5. Read graph statistics directly from long_status
	statusRes, err := e.client.CallTool(ctx, "long_status", map[string]interface{}{
		"space_id":      targetSpace,
		"include_graph": true,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to fetch graph status for evaluation: %w", err)
	}
	if statusRes["status"] != "ok" || statusRes["isError"] == true {
		return nil, fmt.Errorf("failed to get valid graph status: %v", statusRes["message"])
	}

	res := &EvalResult{
		OntologyPath:         opts.Ontology,
		SpaceID:              targetSpace,
		IsTemporarySpace:     isTemp,
		SampleCount:          len(sampleItems),
		SampleFiles:          sampleNames,
		ThresholdOther:       opts.ThresholdOther,
		EntityTypesBreakdown: make(map[string]int),
		Suggestions:          make([]string, 0),
	}

	// Extract graph stats (supports document_count, entity_count/entities_count, relation_count)
	if statsMap, ok := statusRes["graph_stats"].(map[string]interface{}); ok {
		if totalEnts, ok := statsMap["entity_count"].(float64); ok {
			res.TotalEntities = int(totalEnts)
		} else if totalEnts, ok := statsMap["entities_count"].(float64); ok {
			res.TotalEntities = int(totalEnts)
		} else if totalEntsInt, ok := statsMap["entity_count"].(int); ok {
			res.TotalEntities = totalEntsInt
		}

		if typeDist, ok := statsMap["entity_types"].(map[string]interface{}); ok {
			for typeName, countRaw := range typeDist {
				c := 0
				if cFloat, ok := countRaw.(float64); ok {
					if cFloat < 0 || cFloat != math.Trunc(cFloat) {
						return nil, fmt.Errorf("invalid entity count for %s", typeName)
					}
					c = int(cFloat)
				} else if cInt, ok := countRaw.(int); ok {
					if cInt < 0 {
						return nil, fmt.Errorf("invalid entity count for %s", typeName)
					}
					c = cInt
				} else {
					return nil, fmt.Errorf("invalid entity count for %s", typeName)
				}
				res.EntityTypesBreakdown[typeName] = c
				if strings.EqualFold(typeName, "Other") || strings.EqualFold(typeName, "Generic") {
					res.OtherEntities += c
				} else {
					res.TypedEntities += c
				}
			}
		}
	}

	// Extract top unclassified entities
	if topEnts, ok := statusRes["top_entities"].([]interface{}); ok {
		for _, entRaw := range topEnts {
			if entMap, ok := entRaw.(map[string]interface{}); ok {
				eType, _ := entMap["type"].(string)
				eName, _ := entMap["name"].(string)
				if eName == "" {
					eName, _ = entMap["entity"].(string)
				}
				if strings.EqualFold(eType, "Other") || strings.EqualFold(eType, "Generic") {
					res.UnclassifiedConcepts = append(res.UnclassifiedConcepts, UnclassifiedConcept{
						Name: eName,
					})
				}
			}
		}
	}

	// If TotalEntities is derived from sum
	if res.TotalEntities == 0 {
		res.TotalEntities = res.TypedEntities + res.OtherEntities
	}

	if res.TotalEntities == 0 {
		return nil, fmt.Errorf("no entities were extracted from the sample documents during ontology evaluation")
	}

	if len(res.EntityTypesBreakdown) == 0 || res.TotalEntities != res.TypedEntities+res.OtherEntities {
		return nil, fmt.Errorf("long_status lacks a complete entity_types distribution; ontology evaluation cannot be scored reliably")
	}

	res.OtherPercentage = (float64(res.OtherEntities) / float64(res.TotalEntities)) * 100.0

	// Determine relevance tier
	switch {
	case res.OtherPercentage < 1.0:
		res.RelevanceTier = "Excellent (<1%)"
	case res.OtherPercentage < 5.0:
		res.RelevanceTier = "Very Good (<5%)"
	case res.OtherPercentage < 10.0:
		res.RelevanceTier = "Moderate (<10%)"
	default:
		res.RelevanceTier = "Inadequate (>=10%)"
	}

	if res.OtherPercentage > float64(opts.ThresholdOther) {
		res.PassedThreshold = false
		res.ExtractionStatus = "warning"
		res.Message = fmt.Sprintf("Ontology adequacy alert: %.1f%% of extracted entities are unclassified 'Other' (threshold: %d%%).", res.OtherPercentage, opts.ThresholdOther)
		res.Suggestions = append(res.Suggestions, "Enrich ontology YAML with dedicated entity types for the unclassified concepts listed in the report.")
	} else {
		res.PassedThreshold = true
		res.ExtractionStatus = "success"
		res.Message = fmt.Sprintf("Ontology adequacy verified: %.1f%% unclassified entities (Tier: %s, threshold: %d%%).", res.OtherPercentage, res.RelevanceTier, opts.ThresholdOther)
	}

	return res, nil
}
