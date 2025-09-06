package main

import (
	"bytes"
	"encoding/json"
	"log"
	"net/http"
	"sync"

	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
}

type TunnelServer struct {
	conn   *websocket.Conn
	mu     sync.Mutex
	pending map[string]chan http.Response
}

func NewTunnelServer() *TunnelServer {
	return &TunnelServer{
		pending: make(map[string]chan http.Response),
	}
}

func (ts *TunnelServer) handleTunnel(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("Upgrade error:", err)
		return
	}
	defer conn.Close()

	ts.mu.Lock()
	ts.conn = conn
	ts.mu.Unlock()

	log.Println("Tunnel client connected")

	for {
		var resp http.Response
		if err := conn.ReadJSON(&resp); err != nil {
			log.Println("Read error:", err)
			break
		}

		id := resp.Header.Get("X-Tunnel-ID")
		if ch, ok := ts.pending[id]; ok {
			ch <- resp
		}
	}
}

func (ts *TunnelServer) handleHTTP(w http.ResponseWriter, r *http.Request) {
	if ts.conn == nil {
		http.Error(w, "No tunnel client connected", http.StatusServiceUnavailable)
		return
	}

	id := generateID()
	ch := make(chan http.Response, 1)

	ts.mu.Lock()
	ts.pending[id] = ch
	ts.mu.Unlock()

	defer func() {
		ts.mu.Lock()
		delete(ts.pending, id)
		ts.mu.Unlock()
	}()

	// Forward request to tunnel client
	reqBytes, _ := json.Marshal(r)
	msg := map[string]interface{}{
		"ID":      id,
		"Request": json.RawMessage(reqBytes),
	}

	ts.mu.Lock()
	if err := ts.conn.WriteJSON(msg); err != nil {
		ts.mu.Unlock()
		http.Error(w, "Tunnel write error", http.StatusInternalServerError)
		return
	}
	ts.mu.Unlock()

	// Wait for response
	resp := <-ch

	// Copy response back to client
	for k, vv := range resp.Header {
		for _, v := range vv {
			w.Header().Add(k, v)
		}
	}
	w.WriteHeader(resp.StatusCode)
	buf := new(bytes.Buffer)
	buf.ReadFrom(resp.Body)
	w.Write(buf.Bytes())
}

func generateID() string {
	return fmt.Sprintf("%d", time.Now().UnixNano())
}

func main() {
	ts := NewTunnelServer()

	http.HandleFunc("/tunnel", ts.handleTunnel)
	http.HandleFunc("/", ts.handleHTTP)

	port := os.Getenv("PORT")
	if port == "" {
		port = "10000"
	}
	log.Println("Server listening on port", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
