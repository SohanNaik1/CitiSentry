package api

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"citisentry-broker/internal/analytics"
	"citisentry-broker/internal/store"
	"citisentry-broker/internal/ws"
)

// vehicleSighting tracks the last time+camera a vehicle was seen (for overlap debounce)
type vehicleSighting struct {
	CameraID string
	SeenAt   time.Time
}

// cameraAdjacency maps source camera -> list of neighboring destination cameras
var cameraAdjacency = map[string][]string{
	"CAM-001": {"CAM-005", "CAM-002"},
	"CAM-002": {"CAM-003"},
	"CAM-003": {"CAM-002", "CAM-004"},
	"CAM-004": {"CAM-003"},
	"CAM-005": {"CAM-001"},
}

// cameraVideoFiles maps camera_id -> relative video path for handoff
var cameraVideoFiles = map[string]string{
	"CAM-001": "test_video.mp4",
	"CAM-002": "../../web/public/videos/cam002.mp4",
	"CAM-003": "../../web/public/videos/cam003.mp4",
	"CAM-004": "../../web/public/videos/cam004.mp4",
	"CAM-005": "../../web/public/videos/cam005.mp4",
}

// GetNextCamera returns the first neighboring camera for handoff, or "" if none
func GetNextCamera(cameraID string) string {
	neighbors, ok := cameraAdjacency[cameraID]
	if ok && len(neighbors) > 0 {
		return neighbors[0]
	}
	// Dynamic fallback for AICity22 dataset (CAM-016 to CAM-040)
	if strings.HasPrefix(cameraID, "CAM-0") {
		var num int
		if _, err := fmt.Sscanf(cameraID, "CAM-%03d", &num); err == nil {
			if num >= 16 && num < 40 {
				return fmt.Sprintf("CAM-%03d", num+1)
			}
		}
	}
	return ""
}

type APIHandler struct {
	Hub         *ws.Hub
	VectorStore *store.VectorStore
	Analytics   *analytics.Engine

	// Overlap debounce: tracks last sighting per system_id
	sightingsMu sync.Mutex
	sightings   map[string]*vehicleSighting
}

type TelemetryPayload struct {
	CameraID     string    `json:"camera_id"`
	Timestamp    string    `json:"timestamp"`
	OCRText      string    `json:"ocr_text"`
	Vector       []float64 `json:"vector"`
	SpeedKmh     float64   `json:"speed_kmh"`
	VehicleClass string    `json:"vehicle_class"`
	LockedColor  string    `json:"locked_color"`
	SystemID     string    `json:"system_id,omitempty"`
	IsMatched    bool      `json:"is_matched"`
	Status       string    `json:"status,omitempty"`
}

func generateSystemID() string {
	b := make([]byte, 2)
	rand.Read(b)
	return "TRK-" + hex.EncodeToString(b)
}

func NewAPIHandler(hub *ws.Hub, vectorStore *store.VectorStore, analyticsEngine *analytics.Engine) *APIHandler {
	return &APIHandler{
		Hub:         hub,
		VectorStore: vectorStore,
		Analytics:   analyticsEngine,
		sightings:   make(map[string]*vehicleSighting),
	}
}

// StartTrack generates a new system ID for manual tracking initiated from the UI
func (h *APIHandler) StartTrack(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusOK)
		return
	}

	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// For manual UI tracking, we just generate an ID. The frontend will pass this
	// ID to the vision node, which will then send telemetry with it.
	newID := generateSystemID()
	
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"system_id": newID,
	})
}

func (h *APIHandler) IngestTelemetry(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	payloadBytes, err := io.ReadAll(r.Body)
	if err != nil {
		log.Printf("Error reading body: %v", err)
		http.Error(w, "Can't read body", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	var payload TelemetryPayload
	if err := json.Unmarshal(payloadBytes, &payload); err != nil {
		log.Printf("Error unmarshaling payload: %v", err)
		http.Error(w, "Invalid JSON payload", http.StatusBadRequest)
		return
	}

	// ── HANDOFF TRIGGER ──────────────────────────────────────────────
	// If the vision node reports TARGET_LOST, initiate automatic handoff
	if payload.Status == "TARGET_LOST" && payload.SystemID != "" {
		nextCam := GetNextCamera(payload.CameraID)
		if nextCam != "" {
			log.Printf("[HANDOFF] Target %s lost on %s. Handing off to %s", payload.SystemID, payload.CameraID, nextCam)

			systemID := payload.SystemID
			go func() {
				time.Sleep(500 * time.Millisecond)

				// Determine video path for the next camera
				videoPath, ok := cameraVideoFiles[nextCam]
				if !ok {
					// Fallback check for AICity22
					var num int
					if _, err := fmt.Sscanf(nextCam, "CAM-%03d", &num); err == nil && num >= 16 {
						videoPath = fmt.Sprintf("../../web/public/videos/AICity22/S04/c%03d.avi", num)
					} else {
						videoPath = fmt.Sprintf("../../web/public/videos/%s.mp4", strings.ToLower(nextCam))
					}
				}

				// Tell Python to switch camera and auto-lock the target
				switchPayload, _ := json.Marshal(map[string]string{
					"camera_id":        nextCam,
					"video_path":       videoPath,
					"target_system_id": systemID,
				})
				resp, err := http.Post("http://127.0.0.1:5000/switch_camera", "application/json", bytes.NewReader(switchPayload))
				if err != nil {
					log.Printf("[HANDOFF] Failed to POST /switch_camera: %v", err)
					return
				}
				resp.Body.Close()

				// Broadcast HANDOFF event to all WebSocket clients
				handoffMsg, _ := json.Marshal(map[string]string{
					"type":          "HANDOFF",
					"new_camera_id": nextCam,
				})
				h.Hub.Broadcast <- handoffMsg
				log.Printf("[HANDOFF] Successfully handed off to %s", nextCam)
			}()
		}
		w.WriteHeader(http.StatusCreated)
		w.Write([]byte(`{"status":"handoff_initiated"}`))
		return
	}

	// ── OVERLAP DEBOUNCE ─────────────────────────────────────────────
	// If a vehicle's CameraID changes but the time since last detection is < 3s,
	// it's an FOV overlap — skip anomaly checks, just update the camera.
	if payload.SystemID != "" {
		h.sightingsMu.Lock()
		last, exists := h.sightings[payload.SystemID]
		now := time.Now()
		if exists && last.CameraID != payload.CameraID && now.Sub(last.SeenAt) < 3*time.Second {
			// FOV overlap detected — just update sighting and skip anomaly checks
			last.CameraID = payload.CameraID
			last.SeenAt = now
			h.sightingsMu.Unlock()
			log.Printf("[DEBOUNCE] FOV overlap for %s (%s -> %s), skipping anomaly check", payload.SystemID, last.CameraID, payload.CameraID)

			// Still feed analytics and broadcast
			h.Analytics.Update(analytics.TelemetryEvent{
				SystemID: payload.SystemID,
				CameraID: payload.CameraID,
				Class:    payload.VehicleClass,
				SpeedKmh: payload.SpeedKmh,
			})
			enrichedBytes, _ := json.Marshal(payload)
			h.Hub.Broadcast <- enrichedBytes
			w.WriteHeader(http.StatusCreated)
			w.Write([]byte(`{"status":"debounced"}`))
			return
		}
		// Update or create sighting
		if exists {
			last.CameraID = payload.CameraID
			last.SeenAt = now
		} else {
			h.sightings[payload.SystemID] = &vehicleSighting{
				CameraID: payload.CameraID,
				SeenAt:   now,
			}
		}
		h.sightingsMu.Unlock()
	}

	if len(payload.Vector) > 0 {
		// Run vector similarity search across all historical vectors
		matchID, score := h.VectorStore.FindMatch(payload.Vector, 0.85)

		if matchID != "" && matchID != payload.SystemID {
			// A match was found, AND it belongs to a historical track!
			// The Python node generated a local ID, but the Broker knows its true Global ID.
			payload.SystemID = matchID
			payload.IsMatched = true
			log.Printf("[C2] Match Found! Translating local ID to Global ID: %s | Cosine Score: %.3f", matchID, score)
			// Save updated vector under the true Global ID
			h.VectorStore.SaveVector(matchID, payload.Vector)
		} else {
			// No historical match found (or it matched itself). Keep the local SystemID.
			if payload.SystemID == "" {
				payload.SystemID = generateSystemID()
			}
			payload.IsMatched = false
			// Save the vector to keep the database fresh
			h.VectorStore.SaveVector(payload.SystemID, payload.Vector)
			
			if matchID == "" {
				log.Printf("[C2] New Target Enrolled! Assigned Global ID: %s", payload.SystemID)
			}
		}
	} else {
		if payload.SystemID == "" {
			payload.SystemID = "UNKNOWN"
		}
		payload.IsMatched = false
	}

	// Feed the Analytics Engine
	h.Analytics.Update(analytics.TelemetryEvent{
		SystemID: payload.SystemID,
		CameraID: payload.CameraID,
		Class:    payload.VehicleClass,
		SpeedKmh: payload.SpeedKmh,
	})

	// Marshal back to JSON to broadcast
	enrichedBytes, err := json.Marshal(payload)
	if err != nil {
		log.Printf("Error marshaling enriched payload: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	// Push enriched payload to Hub
	h.Hub.Broadcast <- enrichedBytes

	w.WriteHeader(http.StatusCreated)
	w.Write([]byte(`{"status":"success"}`))
}
