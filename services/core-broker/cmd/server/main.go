package main

import (
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"citisentry-broker/internal/analytics"
	"citisentry-broker/internal/api"
	"citisentry-broker/internal/store"
	"citisentry-broker/internal/ws"

	"github.com/gorilla/mux"
)

func main() {
	// Initialize the Hub
	hub := ws.NewHub()
	go hub.Run()

	// Initialize the in-memory Vector Store
	vectorStore := store.NewVectorStore()

	// Initialize the Analytics Engine
	analyticsEngine := analytics.NewEngine()
	go analyticsEngine.StartBroadcastTicker(hub, 5*time.Second)

	// Initialize API Handler
	apiHandler := api.NewAPIHandler(hub, vectorStore, analyticsEngine)

	// Set up the Gorilla Mux router
	r := mux.NewRouter()

	// Register POST /api/v1/telemetry -> IngestTelemetry
	r.HandleFunc("/api/v1/telemetry", apiHandler.IngestTelemetry).Methods("POST", "OPTIONS")

	// Register POST /api/v1/track/start -> StartTrack
	r.HandleFunc("/api/v1/track/start", apiHandler.StartTrack).Methods("POST", "OPTIONS")

	// Register GET /ws -> WebSocket upgrade handler
	r.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		ws.ServeWs(hub, w, r)
	})

	// Start the HTTP server on 0.0.0.0:8080 with graceful shutdown logging
	addr := "0.0.0.0:8080"
	log.Printf("Starting CitiSentry Core Event Broker on %s...", addr)

	srv := &http.Server{
		Handler: r,
		Addr:    addr,
	}

	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Listen and serve error: %v", err)
		}
	}()

	// Graceful shutdown logging
	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt, syscall.SIGTERM)
	<-c
	log.Println("Shutting down CitiSentry Core Event Broker...")
}
