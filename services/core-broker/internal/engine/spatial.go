package engine

import (
	"citisentry-broker/pkg/models"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"os"
)

// EarthRadiusKM is the mean radius of the Earth used for Haversine calculations.
const EarthRadiusKM = 6371.0

// SpatialRegistry holds all camera nodes in an in-memory lookup table indexed
// by camera_id. It is initialized once at broker boot from the canonical
// camera_nodes.json topology file and provides O(1) coordinate lookups for
// the anomaly detection engine.
type SpatialRegistry struct {
	nodes map[string]models.CameraNode
}

// NewSpatialRegistry reads and parses the camera topology JSON file from disk,
// builds the lookup map, and returns the initialized registry. Returns an error
// if the file cannot be read or contains malformed JSON.
func NewSpatialRegistry(topologyPath string) (*SpatialRegistry, error) {
	data, err := os.ReadFile(topologyPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read topology file %q: %w", topologyPath, err)
	}

	var nodes []models.CameraNode
	if err := json.Unmarshal(data, &nodes); err != nil {
		return nil, fmt.Errorf("failed to parse topology JSON: %w", err)
	}

	registry := &SpatialRegistry{
		nodes: make(map[string]models.CameraNode, len(nodes)),
	}
	for _, node := range nodes {
		registry.nodes[node.CameraID] = node
		log.Printf("[SPATIAL] Registered camera %s (%s) at [%.4f, %.4f]",
			node.CameraID, node.Name, node.Lat, node.Lng)
	}

	log.Printf("[SPATIAL] SpatialRegistry initialized with %d camera nodes", len(registry.nodes))
	return registry, nil
}

// GetNode performs an O(1) lookup of a camera node by its camera_id.
// Returns the node and true if found, or a zero-value node and false if the
// camera_id does not exist in the registry.
func (sr *SpatialRegistry) GetNode(cameraID string) (models.CameraNode, bool) {
	node, ok := sr.nodes[cameraID]
	return node, ok
}

// CalculateHaversineDistance computes the great-circle distance in kilometers
// between two geographic coordinates (lat1, lon1) and (lat2, lon2) using the
// Haversine formula. Inputs are in decimal degrees.
//
// Formula:
//
//	a = sin²(Δlat/2) + cos(lat1) · cos(lat2) · sin²(Δlon/2)
//	c = 2 · atan2(√a, √(1−a))
//	d = R · c
func CalculateHaversineDistance(lat1, lon1, lat2, lon2 float64) float64 {
	// Convert degrees to radians
	lat1Rad := lat1 * math.Pi / 180.0
	lon1Rad := lon1 * math.Pi / 180.0
	lat2Rad := lat2 * math.Pi / 180.0
	lon2Rad := lon2 * math.Pi / 180.0

	dLat := lat2Rad - lat1Rad
	dLon := lon2Rad - lon1Rad

	a := math.Sin(dLat/2)*math.Sin(dLat/2) +
		math.Cos(lat1Rad)*math.Cos(lat2Rad)*
			math.Sin(dLon/2)*math.Sin(dLon/2)

	c := 2 * math.Atan2(math.Sqrt(a), math.Sqrt(1-a))

	return EarthRadiusKM * c
}
