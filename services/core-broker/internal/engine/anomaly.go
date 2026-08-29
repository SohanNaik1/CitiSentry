package engine

import (
	"citisentry-broker/pkg/models"
	"fmt"
	"log"
	"time"

	"github.com/google/uuid"
)

// MaxLegalSpeedKMH is the absolute physical speed threshold in km/h.
// Any vehicle that appears to travel between two camera nodes at a speed
// exceeding this value is flagged as a CLONED_PLATE_SPOOF because it
// violates the laws of physics for road travel.
const MaxLegalSpeedKMH = 250.0

// CheckForAnomalies performs spatiotemporal validation between two consecutive
// detections of the same license plate. It calculates the Haversine distance
// between the two camera nodes and the time delta between the detections to
// derive the required travel speed. If the speed exceeds MaxLegalSpeedKMH,
// it returns a CRITICAL AlertEvent indicating a cloned or spoofed plate.
//
// Returns nil if:
//   - Both events are from the same camera (re-detection, not travel).
//   - Either camera node is not found in the spatial registry.
//   - The calculated speed is within physical limits.
func CheckForAnomalies(newEvent models.TelemetryEvent, lastEvent models.TelemetryEvent, registry *SpatialRegistry) *models.AlertEvent {
	// Same camera re-detection is not anomalous travel
	if newEvent.CameraID == lastEvent.CameraID {
		return nil
	}

	// Resolve coordinates for both camera nodes
	nodeA, okA := registry.GetNode(lastEvent.CameraID)
	if !okA {
		log.Printf("[ANOMALY] WARNING: Camera %s not found in spatial registry, skipping check", lastEvent.CameraID)
		return nil
	}

	nodeB, okB := registry.GetNode(newEvent.CameraID)
	if !okB {
		log.Printf("[ANOMALY] WARNING: Camera %s not found in spatial registry, skipping check", newEvent.CameraID)
		return nil
	}

	// Calculate great-circle distance between camera positions
	distanceKM := CalculateHaversineDistance(nodeA.Lat, nodeA.Lng, nodeB.Lat, nodeB.Lng)

	// Calculate time delta in hours from epoch_ms timestamps
	timeDeltaMS := newEvent.EpochMS - lastEvent.EpochMS
	if timeDeltaMS <= 0 {
		// Events are out of order or simultaneous — treat as anomalous
		log.Printf("[ANOMALY] WARNING: Non-positive time delta (%d ms) for plate %s between %s and %s",
			timeDeltaMS, newEvent.LicensePlate.Text, lastEvent.CameraID, newEvent.CameraID)

		alert := &models.AlertEvent{
			AlertID:        uuid.New().String(),
			AlertType:      "CLONED_PLATE_SPOOF",
			Severity:       "CRITICAL",
			TargetPlate:    newEvent.LicensePlate.Text,
			SourceCameraID: newEvent.CameraID,
			Details: fmt.Sprintf(
				"Simultaneous detection on cameras %s (%s) and %s (%s). Distance: %.2f km. Time delta: %d ms. Plate likely cloned.",
				lastEvent.CameraID, nodeA.Name, newEvent.CameraID, nodeB.Name, distanceKM, timeDeltaMS,
			),
			CreatedAt: time.Now().UTC().Format(time.RFC3339),
		}
		return alert
	}

	timeDeltaHours := float64(timeDeltaMS) / 3600000.0

	// Calculate required speed: Speed = Distance / Time
	requiredSpeedKMH := distanceKM / timeDeltaHours

	log.Printf("[ANOMALY] Plate %s: %s → %s | Distance: %.3f km | Delta: %d ms | Required speed: %.1f km/h",
		newEvent.LicensePlate.Text, lastEvent.CameraID, newEvent.CameraID,
		distanceKM, timeDeltaMS, requiredSpeedKMH)

	// Check against the physical speed threshold
	if requiredSpeedKMH > MaxLegalSpeedKMH {
		log.Printf("[ANOMALY] *** CLONED PLATE DETECTED *** Plate %s requires %.1f km/h (threshold: %.1f km/h)",
			newEvent.LicensePlate.Text, requiredSpeedKMH, MaxLegalSpeedKMH)

		alert := &models.AlertEvent{
			AlertID:        uuid.New().String(),
			AlertType:      "CLONED_PLATE_SPOOF",
			Severity:       "CRITICAL",
			TargetPlate:    newEvent.LicensePlate.Text,
			SourceCameraID: newEvent.CameraID,
			Details: fmt.Sprintf(
				"Impossible travel time detected. Vehicle with plate %s moved from %s (%s) to %s (%s) — %.2f km in %d ms. Required speed: %.1f km/h exceeds physical limit of %.1f km/h.",
				newEvent.LicensePlate.Text,
				lastEvent.CameraID, nodeA.Name,
				newEvent.CameraID, nodeB.Name,
				distanceKM, timeDeltaMS,
				requiredSpeedKMH, MaxLegalSpeedKMH,
			),
			CreatedAt: time.Now().UTC().Format(time.RFC3339),
		}
		return alert
	}

	return nil
}
