package store

import (
	"math"
	"sync"
)

type VectorStore struct {
	mu      sync.RWMutex
	vectors map[string][]float64
}

func NewVectorStore() *VectorStore {
	return &VectorStore{
		vectors: make(map[string][]float64),
	}
}

// CosineSimilarity calculates the angle between two embedding vectors.
func (vs *VectorStore) CosineSimilarity(a, b []float64) float64 {
	if len(a) != len(b) {
		return 0.0
	}
	
	var dotProduct, normA, normB float64
	for i := 0; i < len(a); i++ {
		dotProduct += a[i] * b[i]
		normA += a[i] * a[i]
		normB += b[i] * b[i]
	}
	
	if normA == 0 || normB == 0 {
		return 0.0
	}
	
	return dotProduct / (math.Sqrt(normA) * math.Sqrt(normB))
}

// SaveVector safely caches the vector into the store.
func (vs *VectorStore) SaveVector(id string, vector []float64) {
	vs.mu.Lock()
	defer vs.mu.Unlock()
	
	// Create a copy to prevent external mutation
	vecCopy := make([]float64, len(vector))
	copy(vecCopy, vector)
	
	vs.vectors[id] = vecCopy
}

// FindMatch iterates over cached vectors and returns the system_id of the highest match above the threshold.
func (vs *VectorStore) FindMatch(vector []float64, threshold float64) (string, float64) {
	vs.mu.RLock()
	defer vs.mu.RUnlock()
	
	var bestMatchID string
	var bestScore float64 = -1.0
	
	for id, cachedVec := range vs.vectors {
		score := vs.CosineSimilarity(vector, cachedVec)
		if score > bestScore {
			bestScore = score
			bestMatchID = id
		}
	}
	
	if bestScore >= threshold {
		return bestMatchID, bestScore
	}
	
	return "", 0.0
}
