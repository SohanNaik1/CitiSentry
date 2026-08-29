package ws

import (
	"log"
	"sync"
)

// Hub maintains the set of active WebSocket clients and broadcasts
// incoming messages to all of them. It is the central coordination
// point for real-time telemetry distribution from the Go broker to
// all connected Next.js frontend instances.
type Hub struct {
	// mu protects the clients map from concurrent modification
	mu sync.RWMutex

	// clients is the set of currently registered WebSocket clients.
	// The bool value is always true; the map is used as a set.
	clients map[*Client]bool

	// Broadcast is the inbound channel for messages that should be
	// sent to every connected client. The ingestion handler pushes
	// serialized telemetry JSON into this channel.
	Broadcast chan []byte

	// register is the channel for client registration requests.
	register chan *Client

	// unregister is the channel for client disconnection cleanup.
	unregister chan *Client
}

// NewHub allocates and returns a new Hub with initialized channels
// and an empty client set. The Broadcast channel is buffered to 256
// messages to absorb short bursts from the simulator without blocking
// the HTTP ingestion handler goroutine.
func NewHub() *Hub {
	return &Hub{
		clients:    make(map[*Client]bool),
		Broadcast:  make(chan []byte, 256),
		register:   make(chan *Client),
		unregister: make(chan *Client),
	}
}

// Run starts the Hub's main event loop. It must be launched in its own
// goroutine via `go hub.Run()`. The loop uses a select statement to
// handle three event types without busy-waiting:
//
//  1. register: a new client connected, add it to the set.
//  2. unregister: a client disconnected, remove it and close its send channel.
//  3. Broadcast: a new message arrived, fan it out to every connected client.
//     If a client's send buffer is full (stuck/slow consumer), it is evicted.
func (h *Hub) Run() {
	log.Println("[WS-HUB] WebSocket hub started, awaiting connections...")
	for {
		select {
		case client := <-h.register:
			h.mu.Lock()
			h.clients[client] = true
			count := len(h.clients)
			h.mu.Unlock()
			log.Printf("[WS-HUB] Client connected. Active clients: %d", count)

		case client := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[client]; ok {
				delete(h.clients, client)
				close(client.send)
			}
			count := len(h.clients)
			h.mu.Unlock()
			log.Printf("[WS-HUB] Client disconnected. Active clients: %d", count)

		case message := <-h.Broadcast:
			h.mu.RLock()
			for client := range h.clients {
				select {
				case client.send <- message:
					// Message queued successfully
				default:
					// Client's send buffer is full — evict the slow consumer
					// to prevent the entire broadcast pipeline from stalling.
					// The close triggers WritePump to exit and clean up the conn.
					h.mu.RUnlock()
					h.mu.Lock()
					delete(h.clients, client)
					close(client.send)
					h.mu.Unlock()
					h.mu.RLock()
					log.Println("[WS-HUB] Evicted slow consumer")
				}
			}
			h.mu.RUnlock()
		}
	}
}

// ClientCount returns the number of currently connected WebSocket clients.
func (h *Hub) ClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}
