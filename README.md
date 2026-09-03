# CitiSentry: Tactical Multi-Camera ANPR Trajectory Engine & Command Center

**SIH Problem Statement ID:** SIH26127  
**Nodal Organization:** Bharat Electronics Limited (BEL)  
**System Class:** Distributed Tactical Multi-Camera Vehicle Trajectory Engine & Command Center (C2)

CitiSentry is a tactical surveillance and computer vision intelligence system designed to maintain unbroken chain-of-custody tracking of target vehicles across city-scale, multi-camera surveillance grids. 

Even when license plates are obscured, occluded, or missing, CitiSentry locks onto a vehicle's physical identity using deep visual embeddings (**ConvNeXt-Large**), tracks movement through severe occlusions (**YOLO11x + ByteTrack**), mathematically verifies trajectory feasibility via road kinematics (**Go Spatiotemporal Anomaly Engine**), and renders pursuit vectors on a defense-grade Command Console (**Next.js 14**).

---

## System Architecture

The software is composed of three decoupled, high-performance microservices:

1. **Edge Vision Node (Python 3.10+) — Port 5000**
   - **Detector:** Ultralytics YOLO11x (Extra-Large model with SPPF and C3k2 blocks).
   - **Tracker:** ByteTrack (two-stage association matching high- and low-confidence detections).
   - **Deep Re-ID:** ConvNeXt-Large extracting 1536-dimensional L2-normalized feature vectors for cosine similarity matching ($\ge 0.85$).
   - **ANPR & Anti-Logo:** EasyOCR with $2\times$ bicubic upscaling and negative-lookahead regex filtering (`^(?!.*FEDEX)`).
   - **Velocity Engine:** 15-frame windowed displacement anchored on the tire-road bottom-center $(x_{bc}, y_{bc})$ with EMA smoothing.
   - **Streaming:** High-throughput MJPEG stream (`/video_feed`) with real-time REST target locking (`/set_target`) and camera switching (`/switch_camera`).

2. **Core Event Broker (Go 1.22+) — Port 8080**
   - In-memory thread-safe telemetry repository with `sync.RWMutex`.
   - High-throughput Gorilla WebSocket hub pushing low-latency JSON streams to tactical consoles.
   - **Spatiotemporal Anomaly Engine:** Computes Great-Circle Haversine distances across 30 camera nodes. If a vehicle travels between cameras at an impossible physical velocity ($> 250\text{ km/h}$), it immediately broadcasts a `CRITICAL: CLONED_PLATE_SPOOF` alert.

3. **Tactical Command Dashboard (Next.js 14) — Port 3000**
   - Dark-mode tactical HUD (`#0a0e17`) with Leaflet GIS mapping, dynamic polylines, and real-time markers.
   - Interactive HTML5 Canvas overlay dynamically rendering normalized fractional bounding boxes directly on the video feed.
   - Zustand state store with `system_id` deduplication (`TRK-XXXX`) preventing plate overwrite bugs.

---

## System Prerequisites

Ensure you have the following installed on your machine:

| Component | Minimum Version | Recommended Version | Verification Command |
| :--- | :--- | :--- | :--- |
| **Python** | 3.10+ | 3.11 or 3.12 | `python --version` |
| **Node.js** | 18.0+ | 20.0+ LTS | `node --version` |
| **Go** | 1.22+ | 1.22+ | `go version` |
| **Git** | 2.30+ | Latest | `git --version` |

---

## Windows Installation & Setup Guide

### 1. Clone the Repository
Open Command Prompt (`cmd.exe`) or PowerShell:
```cmd
git clone https://github.com/SohanNaik1/CitiSentry.git
cd CitiSentry
```

### 2. Install Web Dashboard Dependencies
From the repository root:
```cmd
cd web
npm install --legacy-peer-deps
cd ..
```

### 3. Create & Activate Python Virtual Environment
Create the virtual environment directly in the **repository root**:
```cmd
python -m venv .venv
call .venv\Scripts\activate
```
*(On PowerShell, run: `.\.venv\Scripts\Activate.ps1`. If script execution is restricted, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first).*

### 4. Install Python Dependencies
Choose the option matching your hardware:

#### Option A: For NVIDIA GPU Acceleration (Recommended for systems with dedicated NVIDIA GPUs)
```cmd
python -m pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

#### Option B: For CPU Only (No Dedicated GPU)
```cmd
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> **Note on Windows Compatibility:** The `requirements.txt` file is pre-configured with `lapx>=0.5.5; sys_platform == 'win32'`, providing pre-compiled binary wheels for ByteTrack so you do **not** need to install Microsoft Visual C++ Build Tools manually.

---

## Linux Installation & Setup Guide (Ubuntu, Debian, CachyOS, Arch)

### 1. Install System Media Libraries
- **Ubuntu/Debian:**
  ```bash
  sudo apt update && sudo apt install -y ffmpeg libgl1-mesa-glx
  ```
- **Arch Linux / CachyOS:**
  ```bash
  sudo pacman -S --needed ffmpeg mesa
  ```

### 2. Install Web Dashboard Dependencies
```bash
cd web
npm install --legacy-peer-deps
cd ..
```

### 3. Create Virtual Environment & Install Requirements
From the repository root:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# For NVIDIA GPU:
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

pip install -r requirements.txt
```

---

## Running the Application

### On Windows
Simply double-click **`start.bat`** in File Explorer, or run it from Command Prompt or PowerShell:
```cmd
start.bat
```

**What `start.bat` does automatically:**
1. **Pre-flight Port Sweep:** Automatically cleans and terminates any ghost processes squatting on ports `3000`, `5000`, or `8080`.
2. **Environment Auto-Detection:** Automatically locates `.venv\Scripts\python.exe` or `venv\Scripts\python.exe`.
3. **Sequential Service Launch:** Boots the Go Core Broker on port 8080, pauses for 2 seconds to allow socket binding, launches the Python Vision Node on port 5000, and starts the Next.js Dashboard on port 3000.
4. **Clean Termination:** Pressing any key or `CTRL+C` terminates all three microservices cleanly without lingering background processes.

### On Linux
Run the provided shell script:
```bash
./start.sh
```

---

## Accessing the Tactical Command Console

Once the services are booted:
1. Open your web browser and navigate to:
   **`http://localhost:3000`**
2. **Live Video Feed:** You will see the live traffic camera stream on the left with camera selector buttons.
3. **Tracking a Vehicle:**
   - Click and drag a tactical bounding box (ROI) directly over any vehicle in the video feed, or click the vehicle.
   - The Vision Node locks onto the target, registers its ConvNeXt-Large appearance embedding, and assigns a persistent profile (`TRK-XXXX`).
   - The velocity readout stabilizes and reflects physical vehicle speed.
4. **Multi-Camera & Re-ID Testing:**
   - Click another camera node (e.g., CAM-028 or CAM-029) on the interactive tactical map.
   - The Global DVR clock seeks to the exact millisecond.
   - When the same vehicle reappears, the Cosine Re-ID engine recognizes the target appearance ($Similarity \ge 0.85$) and re-attaches the existing `TRK-XXXX` identifier without generating a new ID.
5. **Anti-Spoof Alert Testing:**
   - If consecutive detections of the same vehicle violate road kinematics ($> 250\text{ km/h}$ travel time), a `CRITICAL: CLONED_PLATE_SPOOF` alert banner flashes instantly across the console.

---

## Verification & Self-Testing Commands

To verify each microservice independently before full system launch:

```bash
# 1. Test Go Broker compilation
cd services/core-broker
go build ./cmd/server/
cd ../..

# 2. Test Python Vision Node syntax
python -c "import py_compile; py_compile.compile('services/edge-vision/vision_node.py', doraise=True)"

# 3. Test Contract JSON Schemas against sample payloads
python contracts/validate_schemas.py

# 4. Test Web Build
cd web
npm run build
cd ..
```

---

## Project Directory Structure

```
CitiSentry/
├── requirements.txt                    # Master Python dependencies (Windows & Linux compatible)
├── start.bat                           # Hardened Windows launcher (self-cleaning ports)
├── start.sh                            # Hardened Linux launcher (pre-flight port sweep)
├── DOCUMENTATION.md                    # In-depth architectural & technical manual
├── README.md                           # Quickstart & setup guide
├── contracts/                          # Shared canonical schemas & topologies
│   ├── schemas/                        # JSON schemas (Telemetry, Alert, Camera)
│   ├── topology/                       # Camera nodes (30 nodes) & spatial graph
│   └── validate_schemas.py             # Schema regression validator
├── services/
│   ├── core-broker/                    # High-concurrency Go 1.22+ event broker
│   │   ├── cmd/server/main.go          # Broker entrypoint (HTTP + WebSockets)
│   │   ├── internal/api/               # REST handlers (/telemetry, /health, /track)
│   │   ├── internal/engine/            # SpatialRegistry & Haversine AnomalyEngine
│   │   ├── internal/store/             # Thread-safe in-memory telemetry store
│   │   └── internal/ws/                # Gorilla WebSocket client hub
│   ├── edge-simulator/                 # Replay harness & scenario simulator
│   │   └── simulator.py
│   └── edge-vision/                    # Python AI computer vision node
│       ├── requirements.txt            # Edge vision dependency specifications
│       ├── vision_node.py              # YOLO11x + ByteTrack + ConvNeXt + EasyOCR pipeline
│       └── yolo11x.pt                  # Ultralytics YOLO11 Extra-Large model weights
└── web/                                # Next.js 14 Tactical Command Console
    ├── src/
    │   ├── app/                        # App Router (layout.tsx, page.tsx)
    │   ├── components/                 # Map, VideoViewport, TargetDetails, EventPanel
    │   ├── stores/                     # Zustand state engine (useTelemetryStore.ts)
    │   └── types/                      # TypeScript schemas mirroring Go/JSON contracts
    └── public/videos/                  # Multi-camera traffic video archives
```

---

## Troubleshooting

### Port Conflicts (`Address already in use`)
If a port collision occurs:
- **On Windows:** Run `start.bat`. It will automatically detect and force-terminate ghost processes on ports 3000, 5000, and 8080. Alternatively, run:
  ```cmd
  for /f "tokens=5" %a in ('netstat -aon ^| findstr ":8080 :5000 :3000" ^| findstr "LISTENING"') do taskkill /f /pid %a
  ```
- **On Linux:** Run:
  ```bash
  lsof -ti:3000 -ti:5000 -ti:8080 | xargs -r kill -9
  ```

### CUDA / GPU Not Detected
If `torch.cuda.is_available()` returns `False` on Windows with an NVIDIA GPU:
1. Ensure your NVIDIA Game Ready or Studio Driver is installed and up-to-date.
2. Reinstall PyTorch with the CUDA 12.1 index:
   ```cmd
   pip install --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cu121
   ```