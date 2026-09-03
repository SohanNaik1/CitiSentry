package main

import (
	"citisentry-broker/internal/api"
	"citisentry-broker/internal/engine"
	"citisentry-broker/internal/store"
	"citisentry-broker/internal/ws"
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/gorilla/mux"
)

func main() {
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds | log.Lshortfile)
	log.Println("[BOOT] CitiSentry Core Broker starting...")

	// Initialize the thread-safe in-memory telemetry store
	telemetryStore := store.NewTelemetryStore()
	log.Println("[BOOT] In-memory telemetry store initialized")

	// Initialize the WebSocket Hub and start its event loop
	hub := ws.NewHub()
	go hub.Run()
	log.Println("[BOOT] WebSocket hub started")

	// Initialize the Spatial Registry from the canonical camera topology.
	// The topology path is resolved relative to the executable's working directory.
	// In production, this would come from a config file or env var.
	topologyPath := os.Getenv("TOPOLOGY_PATH")
	if topologyPath == "" {
		// Default: resolve relative to the core-broker service root
		// The broker is typically run from services/core-broker/
		topologyPath = filepath.Join("..", "..", "contracts", "topology", "camera_nodes.json")
	}
	registry, err := engine.NewSpatialRegistry(topologyPath)
	if err != nil {
		log.Fatalf("[FATAL] Failed to initialize SpatialRegistry: %v", err)
	}
	log.Println("[BOOT] Spatiotemporal anomaly engine armed")

	// Initialize API handlers wired to the store, WS hub, and spatial registry
	handler := api.NewAPIHandler(telemetryStore, hub, registry)

	// Configure Gorilla Mux router
	router := mux.NewRouter()
	router.Use(corsMiddleware)
	router.Use(loggingMiddleware)

	// API v1 routes
	v1 := router.PathPrefix("/api/v1").Subrouter()
	v1.HandleFunc("/telemetry", handler.IngestTelemetry).Methods(http.MethodPost, http.MethodOptions)
	v1.HandleFunc("/telemetry", handler.QueryTelemetry).Methods(http.MethodGet)
	v1.HandleFunc("/health", handler.HealthCheck).Methods(http.MethodGet)
	v1.HandleFunc("/track/start", handler.StartTracking).Methods(http.MethodPost, http.MethodOptions)

	// WebSocket upgrade endpoint — frontend clients connect here for live telemetry
	router.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		ws.ServeWS(hub, w, r)
	})

	// Determine port from environment or default to 8080
	port := os.Getenv("BROKER_PORT")
	if port == "" {
		port = "8080"
	}

	srv := &http.Server{
		Addr:         ":" + port,
		Handler:      router,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Start server in a goroutine so graceful shutdown can proceed on the main thread
	go func() {
		log.Printf("[BOOT] HTTP server listening on :%s", port)
		log.Println("[BOOT] Routes:")
		log.Println("  POST /api/v1/telemetry   -> IngestTelemetry + AnomalyEngine")
		log.Println("  GET  /api/v1/telemetry   -> QueryTelemetry")
		log.Println("  GET  /api/v1/health      -> HealthCheck")
		log.Println("  GET  /ws                 -> WebSocket Upgrade")
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[FATAL] Server failed to start: %v", err)
		}
	}()

	// Python vision node is orchestrated externally via start.sh

	// Graceful shutdown: wait for SIGINT or SIGTERM
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	sig := <-quit
	log.Printf("[SHUTDOWN] Received signal %v, initiating graceful shutdown...", sig)


	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("[FATAL] Forced shutdown: %v", err)
	}

	log.Printf("[SHUTDOWN] Broker stopped. Total events ingested: %d", telemetryStore.EventCount())
}

// corsMiddleware adds permissive CORS headers so the Next.js frontend
// running on localhost:3000 can communicate with the broker on :8080.
func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// loggingMiddleware logs every incoming HTTP request for operational visibility.
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		log.Printf("[HTTP] %s %s %s", r.Method, r.RequestURI, time.Since(start))
	})
}
