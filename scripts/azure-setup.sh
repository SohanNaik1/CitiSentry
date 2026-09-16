#!/bin/bash
# ==============================================================================
# CitiSentry - Azure Ubuntu VM Automated Setup Script
# Installs Go 1.22, Python 3.11+, Node.js 20 LTS, OpenCV libs, and project deps.
# ==============================================================================

set -e

echo "=== [1/5] Updating system and installing base dependencies ==="
sudo apt-get update -y
sudo apt-get install -y curl wget git build-essential ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 python3-pip python3-venv

echo "=== [2/5] Installing Go 1.22 ==="
if ! command -v go &> /dev/null || [[ "$(go version)" != *"go1.22"* ]]; then
    GO_TAR="go1.22.6.linux-amd64.tar.gz"
    wget -q "https://go.dev/dl/${GO_TAR}"
    sudo rm -rf /usr/local/go
    sudo tar -C /usr/local -xzf "${GO_TAR}"
    rm "${GO_TAR}"
    
    # Add Go to profile if not present
    if ! grep -q "/usr/local/go/bin" ~/.bashrc; then
        echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
    fi
    export PATH=$PATH:/usr/local/go/bin
fi
echo "Go installed: $(go version)"

echo "=== [3/5] Installing Node.js 20 LTS ==="
if ! command -v node &> /dev/null || [[ "$(node -v)" != *"v20"* ]]; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
echo "Node installed: $(node -v), npm: $(npm -v)"

echo "=== [4/5] Setting up Python Virtual Environment ==="
cd "$(dirname "$0")/.."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r services/edge-vision/requirements.txt
pip install -r services/edge-simulator/requirements.txt

echo "=== [5/5] Installing Next.js Frontend Dependencies ==="
cd web
npm install
cd ..

echo "=============================================================================="
echo " [SUCCESS] CitiSentry environment configured successfully!"
echo " To launch all services, run:"
echo "     ./start.sh"
echo "=============================================================================="
