# CitiSentry: Multi-Camera AI Tracking System

CitiSentry is a computer vision and data processing system designed to track vehicles across a network of city cameras. It reads license plates, calculates vehicle speeds, and tracks movement on a live map in real time. 

The software is divided into three main components working together:
1. **Edge Vision (Python)**: Analyzes video feeds using AI to detect vehicles and read license plates.
2. **Core Broker (Go)**: Acts as the central brain. It receives data from the cameras and routes it to the frontend.
3. **Web Dashboard (Next.js)**: The user interface where operators can view the live map, watch video feeds, and monitor alerts.

---

## Prerequisites

Before running the project, you must have the following software installed on your computer.

### Required Software
- **Node.js** (v18 or higher)
- **Go** (v1.22 or higher)
- **Python** (v3.11 or higher)

### System-Specific Requirements

**For Windows:**
No additional system packages are required, provided Python, Go, and Node.js are added to your System PATH during installation.

**For Linux (CachyOS, Ubuntu, Arch, etc.):**
You must install `ffmpeg` and OpenGL libraries for the video processing pipeline to work properly.
- Arch/CachyOS: `sudo pacman -S ffmpeg mesa`
- Ubuntu/Debian: `sudo apt install ffmpeg libgl1-mesa-glx`

---

## Initial Setup

You only need to perform these steps once to install the required libraries.

1. Open your terminal or command prompt.
2. Navigate into the project folder.
3. Install the web dependencies:
   ```bash
   cd web
   npm install --legacy-peer-deps
   cd ..
   ```
4. Set up the Python virtual environment and install the AI dependencies:
   ```bash
   cd services/edge-vision
   python -m venv .venv
   
   # On Windows:
   .venv\Scripts\activate
   # On Linux:
   source .venv/bin/activate
   
   pip install -r requirements.txt
   cd ../..
   ```

---

## Running the Application

To make it as easy as possible to launch the entire system at once, startup scripts are provided in the root directory.

### On Linux
Run the provided shell script from your terminal:
```bash
./start.sh
```

### On Windows
Double-click the `start.bat` file in your file explorer, or run it from your command prompt:
```cmd
start.bat
```

Once the script finishes booting the services, open your web browser and navigate to:
**http://localhost:3000**

To stop the system, go back to the terminal window running the startup script and press `CTRL+C`.