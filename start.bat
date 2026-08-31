@echo off
setlocal

echo [CitiSentry] Starting all services...

:: 1. Start Go Core Broker (Port 8080)
echo [CitiSentry] Starting Core Broker (Go) on port 8080...
cd services\core-broker
start /b go run cmd\server\*.go
cd ..\..

:: 2. Start Python Edge Vision Node (Port 5000)
echo [CitiSentry] Starting Edge Vision Node (Python) on port 5000...
cd services\edge-vision
call ..\..\.venv\Scripts\activate.bat
start /b python vision_node.py --video ..\..\web\public\videos\cam001.mp4 --camera_id CAM-001
call deactivate
cd ..\..

:: 3. Start Next.js Web Dashboard (Port 3000)
echo [CitiSentry] Starting Web Dashboard (Next.js) on port 3000...
cd web
start /b npm run dev
cd ..

echo ========================================================
echo                ALL SERVICES RUNNING!
echo ========================================================
echo  Dashboard: http://localhost:3000
echo  Broker:    http://localhost:8080
echo  Vision:    http://localhost:5000
echo ========================================================
echo Press CTRL+C to safely shut down all services.

:: Wait for user input to exit
pause >nul
