package store

import (
	"citisentry-broker/pkg/models"
	"sync"
)

// TelemetryStore is a thread-safe in-memory store for telemetry events.
// It uses a RWMutex to allow concurrent reads while serializing writes,
// which is critical for a high-throughput ingestion pipeline where the
// Python simulator POSTs events at high speed while the frontend and
// forensic query engine read concurrently.
type TelemetryStore struct {
	mu     sync.RWMutex
	events []models.TelemetryEvent
}

// NewTelemetryStore initializes and returns a new empty TelemetryStore
// with a pre-allocated backing slice to reduce GC pressure during burst
// ingestion from the edge simulator.
func NewTelemetryStore() *TelemetryStore {
	return &TelemetryStore{
		events: make([]models.TelemetryEvent, 0, 1024),
	}
}

// AddEvent appends a telemetry event to the store in a write-safe manner.
// The full write lock is held only for the duration of the append operation.
func (s *TelemetryStore) AddEvent(event models.TelemetryEvent) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.events = append(s.events, event)
}

// GetAllEvents returns a snapshot copy of all stored telemetry events.
// It acquires a read lock so that multiple goroutines can read concurrently
// without blocking each other while writes are serialized separately.
func (s *TelemetryStore) GetAllEvents() []models.TelemetryEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()

	snapshot := make([]models.TelemetryEvent, len(s.events))
	copy(snapshot, s.events)
	return snapshot
}

// QueryEvents filters stored events by camera ID and an epoch_ms time window.
// An empty cameraID matches all cameras. startTime and endTime of 0 disable
// that bound respectively, allowing open-ended temporal queries such as
// "all events on CAM-001 after 1:15 AM" which is the primary forensic use case.
func (s *TelemetryStore) QueryEvents(cameraID string, startTime int64, endTime int64) []models.TelemetryEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()

	results := make([]models.TelemetryEvent, 0)
	for _, event := range s.events {
		// Camera filter: skip if a specific camera was requested and this event is from a different one
		if cameraID != "" && event.CameraID != cameraID {
			continue
		}
		// Temporal lower bound: skip events before the start of the query window
		if startTime > 0 && event.EpochMS < startTime {
			continue
		}
		// Temporal upper bound: skip events after the end of the query window
		if endTime > 0 && event.EpochMS > endTime {
			continue
		}
		results = append(results, event)
	}
	return results
}

// GetLatestEventForPlate iterates backwards through the stored events and
// returns the most recent event matching the given license plate text.
// This reverse scan is intentional: we want the latest event, and since
// events are appended chronologically, the most recent match is near the
// end of the slice. The excludeEventID parameter allows the caller to
// skip the event currently being ingested to avoid self-comparison.
//
// Returns the event and true if found, or a zero-value event and false
// if no matching event exists in the store.
func (s *TelemetryStore) GetLatestEventForPlate(plate string, excludeEventID string) (models.TelemetryEvent, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	for i := len(s.events) - 1; i >= 0; i-- {
		ev := s.events[i]
		if ev.LicensePlate.Text == plate && ev.EventID != excludeEventID {
			return ev, true
		}
	}
	return models.TelemetryEvent{}, false
}

// EventCount returns the total number of stored events without copying the
// entire slice. Useful for health checks and telemetry counters.
func (s *TelemetryStore) EventCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.events)
}
