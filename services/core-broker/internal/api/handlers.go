package api

import (
	"citisentry-broker/internal/engine"
	"citisentry-broker/internal/store"
	"citisentry-broker/internal/ws"
	"citisentry-broker/pkg/models"
	"encoding/hex"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"strconv"
	"crypto/rand"
	"strings"
)

// APIHandler holds references to shared application state and provides
// HTTP handler methods for the broker's REST API surface.
type APIHandler struct {
	Store               *store.TelemetryStore
	Hub                 *ws.Hub
	Registry            *engine.SpatialRegistry
}

// NewAPIHandler creates a new APIHandler wired to the given TelemetryStore,
// WebSocket Hub, and SpatialRegistry for real-time anomaly detection.
func NewAPIHandler(s *store.TelemetryStore, hub *ws.Hub, registry *engine.SpatialRegistry) *APIHandler {
	return &APIHandler{Store: s, Hub: hub, Registry: registry}
}

// StartTracking handles POST /api/v1/track/start.
// It generates a short, random alphanumeric ID (e.g. TRK-4F8A) to serve as the
// primary identifier for a tracked vehicle.
func (h *APIHandler) StartTracking(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	bytes := make([]byte, 2)
	if _, err := rand.Read(bytes); err != nil {
		http.Error(w, `{"error":"failed to generate id"}`, http.StatusInternalServerError)
		return
	}
	systemID := "TRK-" + strings.ToUpper(hex.EncodeToString(bytes))

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)

	resp := map[string]string{
		"status":    "started",
		"system_id": systemID,
	}
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("[ERROR] Failed to encode response: %v", err)
	}
}

// IngestTelemetry handles POST /api/v1/telemetry.
// It reads the full request body, unmarshals it into a TelemetryEvent using
// the canonical parser from pkg/models, runs the spatiotemporal anomaly
// detection engine against prior events for the same plate, persists the
// event in the in-memory store, broadcasts it (and any alerts) to all
// connected WebSocket clients, and returns 201 Created with the event_id.
func (h *APIHandler) IngestTelemetry(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		log.Printf("[ERROR] Failed to read request body: %v", err)
		http.Error(w, `{"error":"failed to read request body"}`, http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	event, err := models.ParseTelemetryEvent(body)
	if err != nil {
		log.Printf("[ERROR] Failed to parse telemetry event: %v", err)
		http.Error(w, `{"error":"invalid telemetry payload"}`, http.StatusBadRequest)
		return
	}

	if event.EventID == "" || event.CameraID == "" {
		http.Error(w, `{"error":"missing required fields: event_id, camera_id"}`, http.StatusBadRequest)
		return
	}

	log.Printf("[INGEST] Event %s | Plate %s | Camera %s | Speed %.1f km/h",
		event.EventID, event.LicensePlate.Text, event.CameraID, event.SpeedKMH)

	// === ANOMALY DETECTION ENGINE ===
	// Before persisting the new event, check if the same plate was seen recently.
	// If the previous detection was at a different camera, run the spatiotemporal
	// check to determine if the travel time violates physical constraints.
	if event.LicensePlate.Text != "" && h.Registry != nil {
		lastEvent, found := h.Store.GetLatestEventForPlate(event.LicensePlate.Text, event.EventID)
		if found {
			alert := engine.CheckForAnomalies(*event, lastEvent, h.Registry)
			if alert != nil {
				log.Printf("[ALERT] *** %s *** Plate: %s | Severity: %s | %s",
					alert.AlertType, alert.TargetPlate, alert.Severity, alert.Details)

				// Broadcast the alert to all connected WebSocket clients immediately
				alertJSON, err := json.Marshal(alert)
				if err != nil {
					log.Printf("[ERROR] Failed to marshal alert for broadcast: %v", err)
				} else {
					h.Hub.Broadcast <- alertJSON
					log.Printf("[BROADCAST] Alert %s pushed to %d WebSocket client(s)",
						alert.AlertID, h.Hub.ClientCount())
				}
			}
		}
	}

	// Persist event in the in-memory store (AFTER anomaly check so the check
	// compares against the previous event, not the one being ingested)
	h.Store.AddEvent(*event)

	// Broadcast the telemetry event to all connected WebSocket clients in real-time.
	// Re-marshal the parsed event to ensure clean, validated JSON is sent
	// to frontends rather than forwarding raw unvalidated bytes.
	eventJSON, err := json.Marshal(event)
	if err != nil {
		log.Printf("[ERROR] Failed to marshal event for broadcast: %v", err)
	} else {
		h.Hub.Broadcast <- eventJSON
		log.Printf("[BROADCAST] Event %s pushed to %d WebSocket client(s)",
			event.EventID, h.Hub.ClientCount())
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)

	resp := map[string]string{
		"status":   "accepted",
		"event_id": event.EventID,
	}
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("[ERROR] Failed to encode response: %v", err)
	}
}

// QueryTelemetry handles GET /api/v1/telemetry.
// It supports optional query parameters for forensic filtering:
//   - camera_id: filter by specific camera node
//   - start_time: epoch_ms lower bound (inclusive)
//   - end_time: epoch_ms upper bound (inclusive)
//
// If no parameters are provided, all stored events are returned.
func (h *APIHandler) QueryTelemetry(w http.ResponseWriter, r *http.Request) {
	cameraID := r.URL.Query().Get("camera_id")
	startTimeStr := r.URL.Query().Get("start_time")
	endTimeStr := r.URL.Query().Get("end_time")

	var startTime, endTime int64
	var err error

	if startTimeStr != "" {
		startTime, err = strconv.ParseInt(startTimeStr, 10, 64)
		if err != nil {
			http.Error(w, `{"error":"invalid start_time parameter"}`, http.StatusBadRequest)
			return
		}
	}

	if endTimeStr != "" {
		endTime, err = strconv.ParseInt(endTimeStr, 10, 64)
		if err != nil {
			http.Error(w, `{"error":"invalid end_time parameter"}`, http.StatusBadRequest)
			return
		}
	}

	var events []models.TelemetryEvent
	if cameraID == "" && startTime == 0 && endTime == 0 {
		events = h.Store.GetAllEvents()
	} else {
		events = h.Store.QueryEvents(cameraID, startTime, endTime)
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	if err := json.NewEncoder(w).Encode(events); err != nil {
		log.Printf("[ERROR] Failed to encode query response: %v", err)
	}
}

// HealthCheck handles GET /api/v1/health.
// Returns the broker's operational status, event count, and connected
// WebSocket client count for monitoring.
func (h *APIHandler) HealthCheck(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)

	resp := map[string]interface{}{
		"status":      "operational",
		"event_count": h.Store.EventCount(),
		"ws_clients":  h.Hub.ClientCount(),
	}
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("[ERROR] Failed to encode health response: %v", err)
	}
}

