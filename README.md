# CitiSentry: Tactical Multi-Camera ANPR Trajectory Engine

CitiSentry is a high-performance, command-and-control (C2) spatial topology engine designed for defense, smart mobility, and urban surveillance operations. The system processes real-time Automatic Number Plate Recognition (ANPR) telemetry across a multi-node camera network to compute trajectories, identify anomalies (e.g., cloned plates, speed violations), and visualize targets on a geospatial tactical interface.

## System Architecture

The repository is built as a unified multi-service architecture comprising three core layers:

1. **Contracts (Data Definition Layer)**
   Contains the canonical JSON schemas, sample payloads, and spatial topology configuration. This ensures strict type safety and data integrity across the entire stack.
   - `contracts/schemas/`: Draft-07 JSON schemas for `camera_node`, `telemetry_event`, and `alert_event`.
   - `contracts/topology/`: Spatial graph definition and camera registry for the city grid.

2. **Backend Services (Data Ingestion & Processing)**
   - **Core Broker (Go)**: A high-concurrency event broker utilizing Go 1.22+. It acts as the central hub, orchestrating the Python vision pipelines, receiving telemetry, evaluating spatial constraints, and broadcasting enriched data via WebSocket to the frontend.
   - **Edge Vision Node (Python)**: A robust OpenCV and YOLOv8-powered tracking engine wrapped in a Flask API. It processes raw camera feeds, executes object detection (BotSORT/ByteTrack), and streams a live MJPEG visual feed to the browser. It supports interactive Region of Interest (ROI) selection to track specific vehicles on demand.

3. **Tactical Command Dashboard (Next.js)**
   An operational Next.js 14+ frontend designed for defense/police operators.
   - **Stack**: React 18, Next.js (App Router), Tailwind CSS (Tactical Dark Theme), Zustand, React-Leaflet.
   - **Features**: Synchronized MJPEG video viewports, interactive ROI tracking overlay, CartoDB spatial mapping, and real-time event feeds.

## Prerequisites

- **Node.js**: v18.17+
- **Go**: v1.22+
- **Python**: v3.11+ (with `pip`)
- **System**: ffmpeg, libgl1-mesa-glx (for OpenCV)

## Getting Started

### 1. Web Dashboard (Frontend)

Navigate to the `web` directory to launch the Tactical Command Dashboard:

```bash
cd web
npm install
npm run dev
```

The application will be accessible at `http://localhost:3000`.

### 2. Edge Vision & Core Broker

The Go Core Broker automatically orchestrates the Python Edge Vision node. Ensure you have installed the Python dependencies before starting the Go broker:

```bash
cd services/edge-vision
pip install -r requirements.txt
```

Navigate to `services/core-broker` to run the ingestion engine and vision pipeline:

```bash
cd services/core-broker
go run cmd/server/main.go
```

The broker will listen on `:8080` for WebSocket connections from the dashboard, and the Python vision node will spawn on `:5000` to serve the live MJPEG feed.

## Code Standards & Directives

- **Type Safety**: `strict: true` is enforced across all TypeScript files.
- **Data Integrity**: Exhaustive validation against JSON schemas is required for all ingress telemetry.
- **Graceful Degradation**: The system is designed to handle edge cases, including camera blind spots, dirty/occluded plates, and sudden stream drops.

## License

Proprietary Software. All rights reserved.