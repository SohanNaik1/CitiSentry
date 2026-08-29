package ws

import (
	"log"
	"net/http"
	"time"

	"github.com/gorilla/websocket"
)

const (
	// writeWait is the maximum time allowed to write a message to the peer.
	writeWait = 10 * time.Second

	// pongWait is the maximum time to wait for a pong response from the peer.
	// If no pong is received within this window, the connection is considered dead.
	pongWait = 60 * time.Second

	// pingPeriod is the interval at which pings are sent to the peer.
	// Must be less than pongWait to ensure the peer responds in time.
	pingPeriod = (pongWait * 9) / 10

	// maxMessageSize is the maximum message size allowed from peer.
	// We only push data to clients, so inbound messages should be minimal.
	maxMessageSize = 512
)

// upgrader handles HTTP-to-WebSocket protocol upgrade.
// CheckOrigin returns true for all origins during the hackathon MVP phase.
// In production, this should validate against a whitelist of allowed origins.
var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

// Client represents a single WebSocket connection managed by the Hub.
// Each client has a dedicated WritePump goroutine that drains the send
// channel and writes messages to the underlying WebSocket connection.
type Client struct {
	hub  *Hub
	conn *websocket.Conn
	send chan []byte
}

// WritePump pumps messages from the hub's broadcast channel to the
// WebSocket connection. It runs as a dedicated goroutine per client.
//
// A ticker sends periodic pings to detect dead connections. If the
// send channel is closed (hub eviction or clean shutdown), the
// goroutine writes a close message and exits, cleaning up the connection.
func (c *Client) WritePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		c.conn.Close()
	}()

	for {
		select {
		case message, ok := <-c.send:
			if err := c.conn.SetWriteDeadline(time.Now().Add(writeWait)); err != nil {
				log.Printf("[WS-CLIENT] Failed to set write deadline: %v", err)
				return
			}
			if !ok {
				// The hub closed the channel — send a close frame and exit.
				if err := c.conn.WriteMessage(websocket.CloseMessage, []byte{}); err != nil {
					log.Printf("[WS-CLIENT] Failed to write close message: %v", err)
				}
				return
			}

			if err := c.conn.WriteMessage(websocket.TextMessage, message); err != nil {
				log.Printf("[WS-CLIENT] Write error: %v", err)
				return
			}

		case <-ticker.C:
			if err := c.conn.SetWriteDeadline(time.Now().Add(writeWait)); err != nil {
				log.Printf("[WS-CLIENT] Failed to set write deadline for ping: %v", err)
				return
			}
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				log.Printf("[WS-CLIENT] Ping error: %v", err)
				return
			}
		}
	}
}

// ReadPump pumps messages from the WebSocket connection to the hub.
// Since this is a push-only architecture (server-to-client), ReadPump
// primarily exists to detect client disconnection by reading control
// frames. When the read fails, the client is unregistered from the hub.
func (c *Client) ReadPump() {
	defer func() {
		c.hub.unregister <- c
		c.conn.Close()
	}()

	c.conn.SetReadLimit(maxMessageSize)
	if err := c.conn.SetReadDeadline(time.Now().Add(pongWait)); err != nil {
		log.Printf("[WS-CLIENT] Failed to set initial read deadline: %v", err)
		return
	}
	c.conn.SetPongHandler(func(string) error {
		return c.conn.SetReadDeadline(time.Now().Add(pongWait))
	})

	for {
		if _, _, err := c.conn.ReadMessage(); err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure) {
				log.Printf("[WS-CLIENT] Unexpected close error: %v", err)
			}
			break
		}
	}
}

// ServeWS handles the initial HTTP request, upgrades it to a WebSocket
// connection, creates a Client bound to the Hub, registers it, and
// starts the ReadPump and WritePump goroutines.
func ServeWS(hub *Hub, w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[WS] Failed to upgrade connection: %v", err)
		return
	}

	client := &Client{
		hub:  hub,
		conn: conn,
		send: make(chan []byte, 256),
	}

	hub.register <- client

	// Start both pumps as goroutines. ReadPump detects disconnection;
	// WritePump pushes telemetry to the client.
	go client.WritePump()
	go client.ReadPump()
}
