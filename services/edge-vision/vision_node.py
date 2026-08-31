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

target_roi = None
roi_search_frames = 0
MAX_ROI_SEARCH_FRAMES = 30

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
    global cap, latest_jpeg, target_track_id, target_plate, target_class, consecutive_misses, dispatch_count, is_paused, target_roi, roi_search_frames
    
    frame_count = 0
    SPEED_WINDOW = 15
    center_history = collections.deque(maxlen=SPEED_WINDOW)

    while True:
        if cap is None:
            import numpy as np
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(frame, "NO SIGNAL", (520, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            ret, jpeg = cv2.imencode('.jpg', frame)
            if ret:
                with frame_condition:
                    latest_jpeg = jpeg.tobytes()
                    frame_condition.notify_all()
            time.sleep(0.1)
            continue
            
        with state_lock:
            current_target_id = target_track_id
            current_target_plate = target_plate
            current_paused = is_paused
            current_roi = target_roi
            current_roi_frames = roi_search_frames
            
        if current_paused:
            time.sleep(0.1)
            continue
            
        current_cap = cap
        if current_cap is None:
            continue
            
        t0 = time.time()
        
        try:
            ret, frame = current_cap.read()
        except Exception:
            ret = False
            
        if not ret:
            # Loop video for the demo
            try:
                current_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            except Exception:
                pass
            continue
            
        frame_count += 1

        if current_target_id is not None or current_roi is not None:
            results = model.track(frame, persist=True, tracker="botsort.yaml", verbose=False, classes=[1, 2, 3, 5, 7], conf=0.25)
            
            if current_roi is not None:
                found_id = None
                found_class = "VEHICLE"
                
                if results[0].boxes is not None and results[0].boxes.id is not None:
                    boxes = results[0].boxes.xyxy.cpu().numpy().tolist()
                    ids = results[0].boxes.id.cpu().numpy().tolist()
                    classes = results[0].boxes.cls.cpu().numpy().tolist()
                    
                    best_iou = 0.0
                    for i in range(len(boxes)):
                        iou = compute_iou(current_roi, boxes[i])
                        if iou > best_iou:
                            best_iou = iou
                            found_id = ids[i]
                            found_class = model.names[int(classes[i])]
                            
                    if found_id is None:
                        user_cx = (current_roi[0] + current_roi[2]) / 2
                        user_cy = (current_roi[1] + current_roi[3]) / 2
                        user_w = current_roi[2] - current_roi[0]
                        user_h = current_roi[3] - current_roi[1]
                        max_allowed_dist = max(user_w, user_h, 150) * 1.5
                        
                        min_dist = float("inf")
                        for i in range(len(boxes)):
                            cx = (boxes[i][0] + boxes[i][2]) / 2
                            cy = (boxes[i][1] + boxes[i][3]) / 2
                            dist = ((cx - user_cx) ** 2 + (cy - user_cy) ** 2) ** 0.5
                            if dist < min_dist and dist < max_allowed_dist:
                                min_dist = dist
                                found_id = ids[i]
                                found_class = model.names[int(classes[i])]
                
                with state_lock:
                    if found_id is not None:
                        target_track_id = found_id
                        target_class = found_class
                        target_roi = None
                        print(f"\n[VISION] LOCKED onto Track ID: {found_id}")
                    else:
                        roi_search_frames -= 1
                        if roi_search_frames <= 0:
                            target_roi = None
                            print("\n[ERROR] Search timed out. No objects found.")
                
                continue

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

        # Calculate time taken and skip frames to maintain real-time 1x speed
        processing_time = time.time() - t0
        expected_time = 1.0 / fps
        
        if processing_time > expected_time:
            # YOLO tracking was slow. Skip frames to catch up to real-time.
            frames_to_skip = int(processing_time / expected_time)
            # Limit skipping to prevent freezing on massive lag spikes
            frames_to_skip = min(frames_to_skip, int(fps * 2))
            
            for _ in range(frames_to_skip):
                try:
                    ret_skip, _ = current_cap.read()
                    if not ret_skip:
                        break
                except Exception:
                    break
        else:
            # We processed faster than real-time. Sleep to maintain original FPS.
            time.sleep(expected_time - processing_time)

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
    global target_track_id, target_plate, target_class, consecutive_misses, is_paused, target_roi, roi_search_frames
    
    data = request.json
    if not data or 'plate' not in data or 'roi' not in data:
        return jsonify({"error": "Invalid request"}), 400
        
    plate = data['plate']
    roi_norm = data['roi'] # [xmin, ymin, xmax, ymax] normalized
    
    user_xyxy = [
        roi_norm[0] * frame_width,
        roi_norm[1] * frame_height,
        roi_norm[2] * frame_width,
        roi_norm[3] * frame_height
    ]

    print(f"\n[VISION] Initiating search for {plate} with ROI: {user_xyxy}")
    
    with state_lock:
        target_roi = user_xyxy
        roi_search_frames = MAX_ROI_SEARCH_FRAMES
        target_track_id = None
        target_plate = plate
        target_class = "VEHICLE"
        consecutive_misses = 0
        is_paused = False
        
    return jsonify({"status": "searching"})

@app.route('/switch_camera', methods=['POST'])
def switch_camera():
    global cap, camera_id_global, target_track_id, target_plate, target_class, consecutive_misses, is_paused, target_roi, roi_search_frames, frame_width, frame_height, fps
    
    data = request.json
    if not data or 'video_path' not in data or 'camera_id' not in data:
        return jsonify({"error": "Invalid request"}), 400
        
    video_path_rel = data['video_path']
    new_camera_id = data['camera_id']
    
    import os
    video_path = os.path.abspath(video_path_rel)
    
    with state_lock:
        print(f"\n[VISION] Switching camera to {new_camera_id}: {video_path}")
        
        new_cap = cv2.VideoCapture(video_path)
        if not new_cap.isOpened():
            print(f"[WARNING] Failed to open {video_path}. Switching to NO SIGNAL mode.", file=sys.stderr)
            new_cap = None
            
        if cap is not None:
            cap.release()
            
        cap = new_cap
        
        if cap is not None:
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        else:
            frame_width = 1280
            frame_height = 720
            fps = 10.0
            
        camera_id_global = new_camera_id
        
        # Reset tracking state
        target_roi = None
        roi_search_frames = 0
        target_track_id = None
        target_plate = None
        target_class = "VEHICLE"
        consecutive_misses = 0
        is_paused = False
        
    return jsonify({"status": "switched", "camera_id": new_camera_id})

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
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
