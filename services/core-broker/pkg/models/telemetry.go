package models

import (
	"encoding/json"
)

type CameraNode struct {
	CameraID  string  `json:"camera_id"`
	Name      string  `json:"name"`
	Lat       float64 `json:"lat"`
	Lng       float64 `json:"lng"`
	Status    string  `json:"status"` // "ONLINE", "OFFLINE", "DEGRADED"
	StreamURL string  `json:"stream_url"`
	FPS       int     `json:"fps"`
}

type LicensePlate struct {
	Text       string  `json:"text"`
	Confidence float64 `json:"confidence"`
	IsClean    bool    `json:"is_clean"`
}

type VehicleAttributes struct {
	Type            string  `json:"type"`             // "SEDAN", "SUV", "HATCHBACK", "TRUCK", "BUS", "MOTORCYCLE"
	Color           string  `json:"color"`            // "WHITE", "BLACK", "SILVER", "GREY", "RED", "BLUE", "OTHER"
	ColorConfidence float64 `json:"color_confidence"`
}

type TelemetryEvent struct {
	EventID           string            `json:"event_id"`
	CameraID          string            `json:"camera_id"`
	Timestamp         string            `json:"timestamp"`
	EpochMS           int64             `json:"epoch_ms"`
	LicensePlate      LicensePlate      `json:"license_plate"`
	// BoundingBox is in [xmin, ymin, xmax, ymax] format, normalized between 0.0 and 1.0
	BoundingBox       []float64         `json:"bounding_box"`
	VehicleAttributes VehicleAttributes `json:"vehicle_attributes"`
	SpeedKMH          float64           `json:"speed_kmh"`
	HeadingDegrees    float64           `json:"heading_degrees"`
	ReIDEmbeddings    []float64         `json:"reid_embeddings"`
}

type AlertEvent struct {
	AlertID        string `json:"alert_id"`
	AlertType      string `json:"alert_type"` // "HOTLIST_HIT", "CLONED_PLATE_SPOOF", "SPEED_VIOLATION", "BLIND_SPOT_DEVIATION"
	Severity       string `json:"severity"`   // "CRITICAL", "HIGH", "MEDIUM", "INFO"
	TargetPlate    string `json:"target_plate"`
	SourceCameraID string `json:"source_camera_id"`
	Details        string `json:"details"`
	CreatedAt      string `json:"created_at"`
}

// ParseTelemetryEvent unmarshals JSON data into a TelemetryEvent struct.
func ParseTelemetryEvent(data []byte) (*TelemetryEvent, error) {
	var event TelemetryEvent
	err := json.Unmarshal(data, &event)
	if err != nil {
		return nil, err
	}
	return &event, nil
}
