package analytics

import (
	"encoding/json"
	"log"
	"sync"
	"time"

	"citisentry-broker/internal/ws"
)

// TelemetryEvent represents the fields needed for analytics aggregation.
type TelemetryEvent struct {
	SystemID string  `json:"system_id"`
	CameraID string  `json:"camera_id"`
	Class    string  `json:"vehicle_class"`
	SpeedKmh float64 `json:"speed_kmh"`
}

// SpeedAccumulator tracks total speed and count for average calculation.
type SpeedAccumulator struct {
	TotalSpeed float64
	Count      int
}

// Engine is a thread-safe analytics aggregator that accumulates
// fleet composition, node velocity, and origin-destination flow data
// from real telemetry events sent by the Python vision node.
type Engine struct {
	mu sync.RWMutex

	// Counts by vehicle class: "SEDAN": 12, "TRUCK": 3, etc.
	FleetComposition map[string]int

	AllTimeTotal int

	// Average speed per camera: "CAM-001": {TotalSpeed: 450.0, Count: 10}
	NodeSpeeds map[string]*SpeedAccumulator

	// Last seen camera for a given system_id (for O-D flow)
	VehicleHistory map[string]string

	// Transition counts: "CAM-001->CAM-002": 5
	ODFlow map[string]int
}

// NewEngine creates and returns a fully initialized Engine.
func NewEngine() *Engine {
	return &Engine{
		FleetComposition: make(map[string]int),
		NodeSpeeds:       make(map[string]*SpeedAccumulator),
		VehicleHistory:   make(map[string]string),
		ODFlow:           make(map[string]int),
	}
}

// Update ingests a single telemetry event and updates all tracked aggregations.
func (e *Engine) Update(event TelemetryEvent) {
	e.mu.Lock()
	defer e.mu.Unlock()

	// 1. Fleet Composition
	if event.Class != "" {
		e.FleetComposition[event.Class]++
	}

	// 2. Node Speeds (for heatmap avg velocity)
	if event.CameraID != "" {
		acc, exists := e.NodeSpeeds[event.CameraID]
		if !exists {
			acc = &SpeedAccumulator{}
			e.NodeSpeeds[event.CameraID] = acc
		}
		acc.TotalSpeed += event.SpeedKmh
		acc.Count++
	}

	// 3. Origin-Destination Flow and Unique Count
	if event.SystemID != "" {
		lastCamera, seen := e.VehicleHistory[event.SystemID]
		if !seen {
			e.AllTimeTotal++
		}
		if event.CameraID != "" {
			if seen && lastCamera != event.CameraID {
				// Vehicle moved from one camera to another
				flowKey := lastCamera + "->" + event.CameraID
				e.ODFlow[flowKey]++
			}
			e.VehicleHistory[event.SystemID] = event.CameraID
		}
	}
}

// GetSnapshot safely calculates average speeds, packages all stats,
// and returns a map ready for JSON marshaling.
func (e *Engine) GetSnapshot() map[string]interface{} {
	e.mu.Lock()
	defer e.mu.Unlock()

	// Calculate average speeds per node
	avgSpeeds := make(map[string]float64)
	for cameraID, acc := range e.NodeSpeeds {
		if acc.Count > 0 {
			avgSpeeds[cameraID] = acc.TotalSpeed / float64(acc.Count)
		}
	}

	// Deep copy fleet composition
	fleet := make(map[string]int)
	for k, v := range e.FleetComposition {
		fleet[k] = v
	}
	
	// Reset fleet composition for instantaneous flux calculation
	e.FleetComposition = make(map[string]int)

	// Deep copy O-D flow
	od := make(map[string]int)
	for k, v := range e.ODFlow {
		od[k] = v
	}

	return map[string]interface{}{
		"fleet_composition": fleet,
		"node_avg_speeds":   avgSpeeds,
		"od_flow":           od,
		"total_tracked":     len(e.VehicleHistory),
		"all_time_total":    e.AllTimeTotal,
	}
}

// StartBroadcastTicker runs an infinite loop that broadcasts an analytics
// snapshot to the WebSocket hub at the given interval.
func (e *Engine) StartBroadcastTicker(hub *ws.Hub, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	log.Printf("[ANALYTICS] Broadcast ticker started (interval: %v)", interval)

	for range ticker.C {
		snapshot := e.GetSnapshot()

		msg := map[string]interface{}{
			"type": "ANALYTICS_UPDATE",
			"data": snapshot,
		}

		msgBytes, err := json.Marshal(msg)
		if err != nil {
			log.Printf("[ANALYTICS] Error marshaling snapshot: %v", err)
			continue
		}

		hub.Broadcast <- msgBytes
	}
}
