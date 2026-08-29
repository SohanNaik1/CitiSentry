import argparse
import collections
import datetime
import sys
import threading
import time
import uuid

import cv2
import requests
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
from ultralytics import YOLO

app = Flask(__name__)
CORS(app)

BROKER_URL = "http://localhost:8080/api/v1/telemetry"

# Global state
state_lock = threading.Lock()
cap = None
frame_width = 0
frame_height = 0
fps = 30.0
camera_id_global = "CAM-001"

target_plate = None
target_track_id = None
target_class = "VEHICLE"
consecutive_misses = 0
MAX_CONSECUTIVE_MISSES = 90
dispatch_count = 0
is_paused = False

latest_jpeg = None
frame_condition = threading.Condition()

model = YOLO("yolov8s.pt")

def xywh_to_xyxy(box: tuple[int, ...]) -> list[float]:
    return [float(box[0]), float(box[1]), float(box[0] + box[2]), float(box[1] + box[3])]

def compute_iou(box_a: list[float], box_b: list[float]) -> float:
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter == 0.0:
        return 0.0

    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0

def process_video():
    global cap, latest_jpeg, target_track_id, target_plate, target_class, consecutive_misses, dispatch_count, is_paused
    
    frame_count = 0
    SPEED_WINDOW = 15
    center_history = collections.deque(maxlen=SPEED_WINDOW)

    while True:
        if cap is None:
            time.sleep(0.1)
            continue
            
        with state_lock:
            current_target_id = target_track_id
            current_target_plate = target_plate
            current_paused = is_paused
            
        if current_paused:
            time.sleep(0.1)
            continue
            
        ret, frame = cap.read()
        if not ret:
            # Loop video for the demo
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
            
        frame_count += 1

        if current_target_id is not None:
            results = model.track(frame, persist=True, tracker="botsort.yaml", verbose=False, classes=[1, 2, 3, 5, 7], conf=0.25)
            
            tracked_xyxy = None
            if results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy().tolist()
                ids = results[0].boxes.id.cpu().numpy().tolist()

                for i in range(len(ids)):
                    if ids[i] == current_target_id:
                        tracked_xyxy = boxes[i]
                        break

            if tracked_xyxy is not None:
                consecutive_misses = 0

                bbox_normalized = [
                    max(0.0, tracked_xyxy[0]) / frame_width,
                    max(0.0, tracked_xyxy[1]) / frame_height,
                    min(float(frame_width), tracked_xyxy[2]) / frame_width,
                    min(float(frame_height), tracked_xyxy[3]) / frame_height,
                ]

                cx = (tracked_xyxy[0] + tracked_xyxy[2]) / 2.0
                cy = (tracked_xyxy[1] + tracked_xyxy[3]) / 2.0
                center_history.append((cx, cy))

                simulated_speed = 0.0
                if len(center_history) >= 2:
                    dx = center_history[-1][0] - center_history[0][0]
                    dy = center_history[-1][1] - center_history[0][1]
                    displacement = (dx ** 2 + dy ** 2) ** 0.5
                    dt = len(center_history) / fps
                    pixel_speed = displacement / dt
                    PIXELS_PER_METER = 25.0
                    speed_mps = pixel_speed / PIXELS_PER_METER
                    simulated_speed = speed_mps * 3.6

                now = datetime.datetime.now(datetime.timezone.utc)
                video_time_sec = frame_count / fps

                event = {
                    "event_id": str(uuid.uuid4()),
                    "camera_id": camera_id_global,
                    "timestamp": now.isoformat(),
                    "epoch_ms": int(now.timestamp() * 1000),
                    "license_plate": {
                        "text": current_target_plate,
                        "confidence": 0.98,
                        "is_clean": True,
                    },
                    "bounding_box": [round(float(v), 4) for v in bbox_normalized],
                    "vehicle_attributes": {
                        "type": target_class.upper(),
                        "color": "UNKNOWN",
                        "color_confidence": 0.0,
                    },
                    "speed_kmh": round(float(simulated_speed), 1),
                    "heading_degrees": 0.0,
                    "reid_embeddings": [0.0] * 128,
                    "video_time_sec": round(float(video_time_sec), 3),
                }

                try:
                    requests.post(BROKER_URL, json=event, timeout=0.5)
                    dispatch_count += 1
                    sys.stdout.write(f"\r[VISION] Dispatch #{dispatch_count} | Speed: {simulated_speed:05.1f} km/h")
                    sys.stdout.flush()
                except requests.RequestException:
                    pass  

                x1, y1 = int(tracked_xyxy[0]), int(tracked_xyxy[1])
                x2, y2 = int(tracked_xyxy[2]), int(tracked_xyxy[3])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"ID:{int(current_target_id)} {target_class} {simulated_speed:.0f}km/h"
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                consecutive_misses += 1
                cv2.putText(
                    frame,
                    f"SEARCHING FOR ID:{int(current_target_id)} ({consecutive_misses}/{MAX_CONSECUTIVE_MISSES})",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
                )
                if consecutive_misses >= MAX_CONSECUTIVE_MISSES:
                    print(f"\n[VISION] Target ID {current_target_id} lost. Tracking stopped.")
                    with state_lock:
                        target_track_id = None
                        target_plate = None

        ret, jpeg = cv2.imencode('.jpg', frame)
        if ret:
            with frame_condition:
                latest_jpeg = jpeg.tobytes()
                frame_condition.notify_all()

        # To keep it close to 30fps and not spin out of control
        time.sleep(1.0 / fps)

@app.route('/video_feed')
def video_feed():
    def generate():
        # Yield the latest frame immediately if available so reconnects during pause get an image
        with frame_condition:
            if latest_jpeg is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_jpeg + b'\r\n\r\n')
                       
        while True:
            with frame_condition:
                # Use a timeout so that if the video is paused, we still yield the frozen frame
                frame_condition.wait(timeout=0.1)
                jpeg_bytes = latest_jpeg
            
            if jpeg_bytes is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n\r\n')

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/pause', methods=['POST'])
def pause_video():
    global is_paused
    with state_lock:
        is_paused = True
    return jsonify({"status": "paused"})

@app.route('/reset', methods=['POST'])
def reset_video():
    global is_paused, target_track_id, target_plate
    with state_lock:
        is_paused = False
        target_track_id = None
        target_plate = None
        if cap is not None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return jsonify({"status": "reset"})

@app.route('/set_target', methods=['POST'])
def set_target():
    global target_track_id, target_plate, target_class, consecutive_misses, is_paused
    
    data = request.json
    if not data or 'plate' not in data or 'roi' not in data:
        return jsonify({"error": "Invalid request"}), 400
        
    plate = data['plate']
    roi_norm = data['roi'] # [xmin, ymin, xmax, ymax] normalized
    
    if cap is None:
        return jsonify({"error": "Video capture not initialized"}), 500

    # Read current frame to initialize tracking
    ret, frame = cap.read()
    if not ret:
        return jsonify({"error": "Could not read frame"}), 500

    user_xyxy = [
        roi_norm[0] * frame_width,
        roi_norm[1] * frame_height,
        roi_norm[2] * frame_width,
        roi_norm[3] * frame_height
    ]

    print(f"\n[VISION] Setting target {plate} with ROI: {user_xyxy}")
    
    init_results = model.track(frame, persist=True, tracker="botsort.yaml", verbose=False, classes=[1, 2, 3, 5, 7], conf=0.25)
    
    found_id = None
    found_class = "VEHICLE"
    
    if init_results[0].boxes is not None and init_results[0].boxes.id is not None:
        boxes = init_results[0].boxes.xyxy.cpu().numpy().tolist()
        ids = init_results[0].boxes.id.cpu().numpy().tolist()
        classes = init_results[0].boxes.cls.cpu().numpy().tolist()

        best_iou = 0.0
        for i in range(len(boxes)):
            iou = compute_iou(user_xyxy, boxes[i])
            if iou > best_iou:
                best_iou = iou
                found_id = ids[i]
                found_class = model.names[int(classes[i])]

        if found_id is None:
            # Fallback to center-distance with a strict threshold
            user_cx = (user_xyxy[0] + user_xyxy[2]) / 2
            user_cy = (user_xyxy[1] + user_xyxy[3]) / 2
            user_w = user_xyxy[2] - user_xyxy[0]
            user_h = user_xyxy[3] - user_xyxy[1]
            max_allowed_dist = max(user_w, user_h, 100) * 1.5 # dynamic threshold with minimum 150px
            
            min_dist = float("inf")

            for i in range(len(boxes)):
                cx = (boxes[i][0] + boxes[i][2]) / 2
                cy = (boxes[i][1] + boxes[i][3]) / 2
                dist = ((cx - user_cx) ** 2 + (cy - user_cy) ** 2) ** 0.5
                if dist < min_dist and dist < max_allowed_dist:
                    min_dist = dist
                    found_id = ids[i]
                    found_class = model.names[int(classes[i])]

    if found_id is not None:
        with state_lock:
            target_track_id = found_id
            target_plate = plate
            target_class = found_class
            consecutive_misses = 0
            is_paused = False
        print(f"[VISION] LOCKED onto Track ID: {found_id}, Class: {found_class}")
        return jsonify({"status": "success", "track_id": found_id})
    else:
        with state_lock:
            # Unpause even on failure, so the user can try again!
            is_paused = False
        print("[ERROR] No matching objects found.")
        return jsonify({"error": "No objects found matching ROI"}), 404

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CitiSentry Flask Vision Node")
    parser.add_argument("--video", required=True, help="Path to the video file")
    parser.add_argument("--camera_id", required=True, help="Camera node ID (e.g. CAM-001)")
    args = parser.parse_args()

    camera_id_global = args.camera_id
    
    print(f"[VISION] Opening video: {args.video}")
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"[ERROR] Failed to open {args.video}", file=sys.stderr)
        sys.exit(1)

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    print(f"[VISION] Video loaded: {frame_width}x{frame_height} @ {fps} FPS")

    # Start processing thread
    t = threading.Thread(target=process_video, daemon=True)
    t.start()

    print("[VISION] Starting Flask server on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
