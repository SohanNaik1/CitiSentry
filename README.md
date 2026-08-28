# CitiSentry: Tactical Multi-Camera ANPR Trajectory Engine

CitiSentry is a high-performance, command-and-control (C2) spatial topology engine designed for defense, smart mobility, and urban surveillance operations. The system processes real-time Automatic Number Plate Recognition (ANPR) telemetry across a multi-node camera network to compute trajectories, identify anomalies (e.g., cloned plates, speed violations), and visualize targets on a geospatial tactical interface.

## System Architecture

The repository is built as a unified multi-service architecture comprising three core layers:

1. **Contracts (Data Definition Layer)**
   Contains the canonical JSON schemas, sample payloads, and spatial topology configuration. This ensures strict type safety and data integrity across the entire stack.
   - `contracts/schemas/`: Draft-07 JSON schemas for `camera_node`, `telemetry_event`, and `alert_event`.
   - `contracts/topology/`: Spatial graph definition and camera registry for the city grid.

2. **Backend & Simulation (Data Ingestion & Processing)**
   - **Core Broker (Go)**: A high-concurrency event broker utilizing Go 1.22+. It processes telemetry, executes spatial constraints, and streams enriched data via WebSocket to the frontend.
   - **Edge Simulator (Python)**: A robust CLI harness for generating and replaying deterministic, time-series telemetry events (e.g., pursuit scenarios, spoofed plates) to stress-test the broker.

3. **Tactical Command Dashboard (Next.js)**
   An operational Next.js 14+ frontend designed for defense/police operators.
   - **Stack**: React 18, Next.js (App Router), Tailwind CSS (Tactical Dark Theme), Zustand, React-Leaflet.
   - **Features**: Synchronized video viewports, HTML5 Canvas telemetry overlays, CartoDB spatial mapping, and real-time event feeds.

## Prerequisites

- **Node.js**: v18.17+
- **Go**: v1.22+
- **Python**: v3.11+ (with `pip` and `virtualenv`)
- **CARTO API Key**: Required for base map tiles (update environment variables accordingly).

## Getting Started

### 1. Web Dashboard (Frontend)

Navigate to the `web` directory to launch the Tactical Command Dashboard:

```bash
cd web
npm install
npm run dev
```

The application will be accessible at `http://localhost:3000`.

### 2. Edge Simulator

Navigate to the `services/edge-simulator` directory to generate and replay scenarios:

```bash
cd services/edge-simulator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Generate mock scenario datasets
python scenarios/generate_scenarios.py

# Replay a specific scenario to the broker
python simulator.py --scenario scenarios/pursuit_scenario.json --speed 1.0
```

### 3. Core Broker

*(Under active development)* Navigate to `services/core-broker` to run the ingestion engine.

## Code Standards & Directives

- **Type Safety**: `strict: true` is enforced across all TypeScript files.
- **Data Integrity**: Exhaustive validation against JSON schemas is required for all ingress telemetry.
- **Graceful Degradation**: The system is designed to handle edge cases, including camera blind spots, dirty/occluded plates, and sudden stream drops.

## License

Proprietary Software. All rights reserved.