package tui

import (
	"bytes"
	"strings"
	"testing"
)

func TestUIFormatting(t *testing.T) {
	var in bytes.Buffer
	var out bytes.Buffer

	ui := NewUI(&in, &out)

	// Test styles
	bold := ui.Bold("hello")
	if !strings.Contains(bold, "hello") {
		t.Errorf("expected string to contain hello, got %s", bold)
	}

	// Test Banner
	ui.Banner()
	if !strings.Contains(strings.ToUpper(out.String()), "GRAPH MEMORY") {
		t.Errorf("expected banner to contain GRAPH MEMORY, got %s", out.String())
	}

	// Test JSON
	data := map[string]string{"key": "value"}
	out.Reset()
	_ = ui.PrintJSON(data)
	if !strings.Contains(out.String(), `"key": "value"`) {
		t.Errorf("expected json output, got %s", out.String())
	}

	// Test ProgressBar (headless)
	out.Reset()
	ui.ProgressBar(5, 10, "processing")
	if !strings.Contains(out.String(), "[5/10]") {
		t.Errorf("expected progress bar output, got %s", out.String())
	}
}

func TestUIPromptAndConfirm(t *testing.T) {
	in := bytes.NewBufferString("custom-val\ny\n")
	var out bytes.Buffer

	ui := NewUI(in, &out)

	val, err := ui.Prompt("Enter name", "default-name")
	if err != nil {
		t.Fatalf("Prompt failed: %v", err)
	}
	if val != "custom-val" {
		t.Errorf("expected custom-val, got %s", val)
	}

	confirmed, err := ui.Confirm("Are you sure?", false)
	if err != nil {
		t.Fatalf("Confirm failed: %v", err)
	}
	if !confirmed {
		t.Errorf("expected confirmed true, got false")
	}
}
