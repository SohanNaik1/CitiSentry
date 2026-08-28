package models

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestParseTelemetryEvent(t *testing.T) {
	// Path to the sample relative to services/core-broker/pkg/models
	path := filepath.Join("..", "..", "..", "..", "contracts", "sample_payloads", "telemetry_event.sample.json")
	
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("Failed to read sample file: %v", err)
	}

	event, err := ParseTelemetryEvent(data)
	if err != nil {
		t.Fatalf("ParseTelemetryEvent returned error: %v", err)
	}

	if event.EventID == "" {
		t.Errorf("Expected EventID to be populated")
	}
	if event.CameraID == "" {
		t.Errorf("Expected CameraID to be populated")
	}
	if len(event.BoundingBox) != 4 {
		t.Errorf("Expected BoundingBox to have 4 elements, got %d", len(event.BoundingBox))
	}
	if len(event.ReIDEmbeddings) != 128 {
		t.Errorf("Expected ReIDEmbeddings to have 128 elements, got %d", len(event.ReIDEmbeddings))
	}
}

func TestParseCameraNode(t *testing.T) {
	path := filepath.Join("..", "..", "..", "..", "contracts", "sample_payloads", "camera_node.sample.json")
	
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("Failed to read sample file: %v", err)
	}

	var node CameraNode
	err = json.Unmarshal(data, &node)
	if err != nil {
		t.Fatalf("Failed to unmarshal CameraNode: %v", err)
	}

	if node.CameraID == "" {
		t.Errorf("Expected CameraID to be populated")
	}
	if node.StreamURL == "" {
		t.Errorf("Expected StreamURL to be populated")
	}
}

func TestParseAlertEvent(t *testing.T) {
	path := filepath.Join("..", "..", "..", "..", "contracts", "sample_payloads", "alert_event.sample.json")
	
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("Failed to read sample file: %v", err)
	}

	var alert AlertEvent
	err = json.Unmarshal(data, &alert)
	if err != nil {
		t.Fatalf("Failed to unmarshal AlertEvent: %v", err)
	}

	if alert.AlertID == "" {
		t.Errorf("Expected AlertID to be populated")
	}
	if alert.AlertType == "" {
		t.Errorf("Expected AlertType to be populated")
	}
}
