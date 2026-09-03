#!/bin/bash

echo "[CitiSentry] Starting all services..."

# ── Pre-flight: kill anything squatting on our ports ──
echo "[CitiSentry] Pre-flight: clearing ports 3000, 5000, 8080..."
lsof -ti:3000 -ti:3001 -ti:3002 -ti:5000 -ti:8080 2>/dev/null | xargs -r kill -9 2>/dev/null || true
sleep 1

# Function to clean up background processes on exit (CTRL+C)
cleanup() {
    echo ""
    echo "[CitiSentry] Shutting down all services..."
    kill $(jobs -p) 2>/dev/null || true
    wait 2>/dev/null || true
    echo "[CitiSentry] Shutdown complete."
}
trap cleanup EXIT INT TERM

# 1. Start Go Core Broker (Port 8080)
echo "[CitiSentry] Starting Core Broker (Go) on port 8080..."
cd services/core-broker
go run cmd/server/*.go &
cd ../..

# Give Go broker 2 seconds to bind port 8080 before starting others
sleep 2

# 2. Start Python Edge Vision Node (Port 5000)
echo "[CitiSentry] Starting Edge Vision Node (Python) on port 5000..."
cd services/edge-vision
../../.venv/bin/python vision_node.py --video ../../web/public/videos/cam001.mp4 --camera_id CAM-001 &
cd ../..

# 3. Start Next.js Web Dashboard (Port 3000)
echo "[CitiSentry] Starting Web Dashboard (Next.js) on port 3000..."
cd web
npm run dev &
cd ..

echo "========================================================"
echo "               ALL SERVICES RUNNING!"
echo "========================================================"
echo " Dashboard: http://localhost:3000"
echo " Broker:    http://localhost:8080"
echo " Vision:    http://localhost:5000"
echo "========================================================"
echo "Press CTRL+C to safely shut down all services."

# Wait indefinitely until interrupted
wait
