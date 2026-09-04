@echo off
setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo ========================================================
echo        CitiSentry: Multi-Camera AI Tracking System
echo                   Windows Launch System
echo ========================================================
echo.

:: ── Step 0: Pre-flight Port Sweep (Kill Ghost Processes) ──
echo [CitiSentry] Pre-flight: Clearing ports 3000, 5000, 8080...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr /r ":8080 :5000 :3000 :3001 :3002" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: ── Step 1: Detect Python Environment ──
if exist "%ROOT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
    echo [CitiSentry] Using virtual environment: .venv
) else if exist "%ROOT_DIR%web\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%web\.venv\Scripts\python.exe"
    echo [CitiSentry] Using virtual environment: web\.venv
) else if exist "%ROOT_DIR%venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%venv\Scripts\python.exe"
    echo [CitiSentry] Using virtual environment: venv
) else (
    set "PYTHON_EXE=python"
    echo [CitiSentry] Using system Python
)

:: ── Step 2: Start Go Core Broker (Port 8080) ──
echo [CitiSentry] Starting Core Broker (Go) on port 8080...
cd /d "%ROOT_DIR%services\core-broker"
start "CitiSentry - Core Broker" /b go run ./cmd/server
cd /d "%ROOT_DIR%"

:: Allow Go broker 2 seconds to bind port 8080
timeout /t 2 /nobreak >nul

:: ── Step 3: Start Python Edge Vision Node (Port 5000) ──
echo [CitiSentry] Starting Edge Vision Node (Python) on port 5000...
cd /d "%ROOT_DIR%services\edge-vision"
start "CitiSentry - Edge Vision" /b "%PYTHON_EXE%" -u vision_node.py --video "..\..\web\public\videos\cam001.mp4" --camera_id CAM-001
cd /d "%ROOT_DIR%"

:: ── Step 4: Start Next.js Web Dashboard (Port 3000) ──
echo [CitiSentry] Starting Web Dashboard (Next.js) on port 3000...
cd /d "%ROOT_DIR%web"
start "CitiSentry - Web Dashboard" /b cmd /c npm run dev
cd /d "%ROOT_DIR%"

echo.
echo ========================================================
echo                ALL SERVICES RUNNING!
echo ========================================================
echo  Dashboard: http://localhost:3000
echo  Broker:    http://localhost:8080
echo  Vision:    http://localhost:5000
echo ========================================================
echo Press any key or CTRL+C to safely shut down all services.
echo.

pause >nul

echo.
echo [CitiSentry] Shutting down all services...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr /r ":8080 :5000 :3000 :3001 :3002" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo [CitiSentry] Shutdown complete.
pause
