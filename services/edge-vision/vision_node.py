import argparse
import collections
import datetime
import math
import sys
import threading
import time
import uuid

import cv2
import numpy as np
import requests
import easyocr
import re
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
from ultralytics import YOLO
import torch
import torchvision.models as models
import torchvision.transforms as transforms
import torch.nn.functional as F

app = Flask(__name__)
CORS(app)

BROKER_URL = "http://localhost:8080/api/v1/telemetry"

print("[VISION] Initializing EasyOCR model (GPU)...")
try:
    ocr_reader = easyocr.Reader(['en'], gpu=True)
except Exception as e:
    print(f"[ERROR] Failed to initialize EasyOCR: {e}", file=sys.stderr)
    ocr_reader = None

PLATE_REGEX = re.compile(r'^(?!.*FEDEX)[A-Z0-9]{4,10}$')

print("[VISION] Initializing Deep Re-ID Model (ConvNeXt-Large)...")
try:
    reid_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    reid_model = models.convnext_large(weights='DEFAULT').to(reid_device)
    # ConvNeXt classifier is a Sequential block; replace the final Linear layer
    reid_model.classifier[2] = torch.nn.Identity()
    reid_model.eval()
    
    reid_transform = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
except Exception as e:
    print(f"[ERROR] Failed to init Re-ID model: {e}", file=sys.stderr)
    reid_model = None

# Global state
state_lock = threading.Lock()
cap = None
frame_width = 0
frame_height = 0
fps = 30.0
camera_id_global = "CAM-001"
dvr_start_time = time.time()
centroid_history = collections.deque(maxlen=15)
prev_center = None

embedding_db = {} # Maps system_id -> embedding (tensor)
active_system_id = None
active_embedding = None
reid_matched = False

target_plate = None
target_track_id = None
target_class = "VEHICLE"
locked_plate = None
locked_class = "UNKNOWN"
locked_color = "OTHER"
consecutive_misses = 0
MAX_CONSECUTIVE_MISSES = 90
dispatch_count = 0
is_paused = False
smoothed_speed = 0.0

target_roi = None
roi_search_frames = 0
MAX_ROI_SEARCH_FRAMES = 30

latest_jpeg = None
frame_condition = threading.Condition()

model = YOLO("yolo11x.pt")

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

YOLO_COCO_CLASSES = {
    2: "SEDAN",
    3: "MOTORCYCLE",
    5: "BUS",
    7: "TRUCK"
}

def map_yolo_class(class_id: int) -> str:
    return YOLO_COCO_CLASSES.get(class_id, "SUV")

def extract_dominant_color(frame: np.ndarray, bbox: list[float]) -> str:
    try:
        x1, y1, x2, y2 = map(int, bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        
        if x2 <= x1 or y2 <= y1:
            return "UNKNOWN"
            
        crop = frame[y1:y2, x1:x2]
        tiny = cv2.resize(crop, (32, 32))
        hsv = cv2.cvtColor(tiny, cv2.COLOR_BGR2HSV)
        
        boundaries = {
            "WHITE":  ([0, 0, 200], [180, 30, 255]),
            "BLACK":  ([0, 0, 0], [180, 255, 50]),
            "SILVER": ([0, 0, 50], [180, 40, 200]),
            "RED":    ([0, 100, 100], [10, 255, 255]),
            "BLUE":   ([100, 100, 50], [140, 255, 255]),
            "YELLOW": ([20, 100, 100], [40, 255, 255])
        }
        
        max_count = 0
        best_color = "UNKNOWN"
        
        for color, (lower, upper) in boundaries.items():
            lower_np = np.array(lower, dtype=np.uint8)
            upper_np = np.array(upper, dtype=np.uint8)
            mask = cv2.inRange(hsv, lower_np, upper_np)
            count = cv2.countNonZero(mask)
            
            if color == "RED":
                mask2 = cv2.inRange(hsv, np.array([160, 100, 100], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8))
                count += cv2.countNonZero(mask2)
                
            if count > max_count:
                max_count = count
                best_color = color
                
        return best_color if max_count > 0 else "UNKNOWN"
    except Exception:
        return "UNKNOWN"

def get_embedding(frame: np.ndarray, bbox: list[float]) -> torch.Tensor:
    if reid_model is None:
        return None
    try:
        x1, y1, x2, y2 = map(int, bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        
        if x2 <= x1 or y2 <= y1:
            return None
            
        crop = frame[y1:y2, x1:x2]
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        input_tensor = reid_transform(crop_rgb).unsqueeze(0).to(reid_device)
        
        with torch.no_grad():
            embedding = reid_model(input_tensor)
            # L2 Normalize
            embedding = F.normalize(embedding, p=2, dim=1)
            return embedding
    except Exception as e:
        print(f"[ERROR] Embedding failed: {e}")
        return None

def process_video():
    global cap, latest_jpeg, target_track_id, target_plate, target_class, locked_plate, locked_class, locked_color, consecutive_misses, dispatch_count, is_paused, target_roi, roi_search_frames, smoothed_speed, centroid_history, prev_center, active_system_id, reid_matched
    
    frame_count = 0

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
            # Loop video maintaining Global DVR sync
            try:
                elapsed_sec = time.time() - dvr_start_time
                total_frames = current_cap.get(cv2.CAP_PROP_FRAME_COUNT)
                vid_fps = current_cap.get(cv2.CAP_PROP_FPS) or 30.0
                if vid_fps <= 0:
                    vid_fps = 30.0
                    
                if total_frames > 0:
                    video_duration = total_frames / vid_fps
                    seek_sec = elapsed_sec % video_duration
                    current_cap.set(cv2.CAP_PROP_POS_MSEC, seek_sec * 1000.0)
                else:
                    current_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    
                # Grab the valid frame after seeking
                ret, frame = current_cap.read()
                if not ret:
                    # We are in a "dead zone" (calculated duration > actual frames).
                    # Force reset to frame 0 immediately to prevent an infinite loop!
                    current_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = current_cap.read()
                    if not ret:
                        continue
            except Exception:
                continue
            
        frame_count += 1

        if current_target_id is not None or current_roi is not None:
            results = model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False, classes=[1, 2, 3, 5, 7], conf=0.25)
            
            if current_roi is not None:
                found_id = None
                found_class = "VEHICLE"
                found_bbox = None
                
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
                            found_bbox = boxes[i]
                            found_class = map_yolo_class(int(classes[i]))
                            found_color = extract_dominant_color(frame, boxes[i])
                            
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
                                found_bbox = boxes[i]
                                found_class = map_yolo_class(int(classes[i]))
                                found_color = extract_dominant_color(frame, boxes[i])
                
                with state_lock:
                    if found_id is not None:
                        target_track_id = found_id
                        target_class = found_class
                        locked_class = found_class
                        locked_color = found_color
                        target_roi = None
                        print(f"\n[VISION] LOCKED onto Track ID: {found_id}")
                        
                        # Extract Deep Embedding
                        emb = get_embedding(frame, found_bbox)
                        if emb is not None:
                            active_embedding = emb
                            
                            best_sim = -1.0
                            best_match_id = None
                            
                            # Compare with known embeddings
                            for sys_id, saved_emb in embedding_db.items():
                                sim = F.cosine_similarity(emb, saved_emb).item()
                                if sim > best_sim:
                                    best_sim = sim
                                    best_match_id = sys_id
                                    
                            if best_sim > 0.85:
                                active_system_id = best_match_id
                                reid_matched = True
                                print(f"[VISION] Deep Re-ID Match! {best_sim:.3f} -> {active_system_id}")
                            else:
                                if active_system_id is None:
                                    import uuid
                                    active_system_id = f"TRK-{uuid.uuid4().hex[:4].upper()}"
                                embedding_db[active_system_id] = emb
                                reid_matched = False
                        else:
                            if active_system_id is None:
                                import uuid
                                active_system_id = f"TRK-{uuid.uuid4().hex[:4].upper()}"
                            reid_matched = False
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

                x1, y1 = int(tracked_xyxy[0]), int(tracked_xyxy[1])
                x2, y2 = int(tracked_xyxy[2]), int(tracked_xyxy[3])
                w, h = max(1, x2 - x1), max(1, y2 - y1)
                
                cx = x1 + w / 2.0
                cy = y1 + h / 2.0
                
                # Windowed Displacement Velocity Tracking
                current_time = time.time()
                # Use bottom-center of bounding box for stability (touches the road)
                bcx = x1 + w / 2.0
                bcy = y2
                
                centroid_history.append((bcx, bcy, current_time))
                
                if len(centroid_history) >= 15:
                    old_cx, old_cy, old_time = centroid_history[0]
                    dt = current_time - old_time
                    if dt > 0:
                        dist = math.hypot(bcx - old_cx, bcy - old_cy)
                        
                        # Tune this factor based on estimated pixels-per-meter for the camera angle
                        pixels_per_meter = 15.0
                        speed_mps = (dist / pixels_per_meter) / dt
                        raw_speed_kmh = speed_mps * 3.6
                        
                        # Apply a low-pass filter and clamp
                        raw_speed_kmh = max(0.0, min(120.0, raw_speed_kmh))
                        smoothed_speed = (smoothed_speed * 0.7) + (raw_speed_kmh * 0.3) if smoothed_speed > 0 else raw_speed_kmh

                if locked_plate is None and ocr_reader is not None:
                    if frame_count % 15 == 0 and w > 120 and h > 120:
                        # Crop bottom 60% for plate detection
                        if y2 > y1 and x2 > x1:
                            plate_crop = frame[y1 + int((y2 - y1) * 0.4) : y2, x1 : x2]
                            if plate_crop.shape[0] > 10 and plate_crop.shape[1] > 10:
                                gray_crop = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
                                gray_crop = cv2.resize(gray_crop, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                                results_ocr = ocr_reader.readtext(gray_crop)
                                
                                for (bbox, text, prob) in results_ocr:
                                    cleaned_text = re.sub(r'[^A-Z0-9]', '', text.upper())
                                    if PLATE_REGEX.match(cleaned_text) and prob > 0.30:
                                        locked_plate = cleaned_text
                                        
                                        print(f"\n[ANPR SUCCESS] Plate Locked: {locked_plate} | Class: {locked_class} | Color: {locked_color}")
                                        break

                if active_system_id is None:
                    import uuid
                    active_system_id = f"TRK-{uuid.uuid4().hex[:4].upper()}"
                    reid_matched = False

                now = datetime.datetime.now(datetime.timezone.utc)
                video_time_sec = frame_count / fps

                event = {
                    "event_id": str(uuid.uuid4()),
                    "system_id": active_system_id,
                    "camera_id": camera_id_global,
                    "timestamp": now.isoformat(),
                    "epoch_ms": int(now.timestamp() * 1000),
                    "license_plate": {
                        "text": locked_plate if locked_plate else "UNKNOWN",
                        "confidence": 0.95 if locked_plate else 0.0,
                        "is_clean": reid_matched
                    },
                    "bounding_box": [round(float(v), 4) for v in bbox_normalized],
                    "vehicle_attributes": {
                        "type": locked_class if locked_class != "UNKNOWN" else map_yolo_class(target_class),
                        "color": locked_color,
                        "color_confidence": 0.9 if locked_color != "OTHER" else 0.0,
                    },
                    "speed_kmh": round(float(smoothed_speed), 1),
                    "heading_degrees": 0.0,
                    "reid_embeddings": (active_embedding[0][:128].cpu().numpy().tolist()) if active_embedding is not None else ([0.0] * 128),
                    "video_time_sec": round(float(video_time_sec), 3),
                }

                try:
                    r = requests.post(BROKER_URL, json=event, timeout=0.5)
                    if r.status_code == 200:
                        dispatch_count += 1
                        sys.stdout.write(f"\r[VISION] Dispatch #{dispatch_count} | Speed: {smoothed_speed:05.1f} km/h")
                        sys.stdout.flush()
                except requests.RequestException:
                    pass  

                x1, y1 = int(tracked_xyxy[0]), int(tracked_xyxy[1])
                x2, y2 = int(tracked_xyxy[2]), int(tracked_xyxy[3])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"ID:{int(current_target_id)} {target_class} {smoothed_speed:.0f}km/h"
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
                        locked_plate = None
                        locked_class = "UNKNOWN"
                        locked_color = "OTHER"
                        smoothed_speed = 0.0
                        centroid_history.clear()
                        prev_center = None
                        active_system_id = None
                        reid_matched = False

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
    global is_paused, target_track_id, target_plate, locked_plate, locked_class, locked_color, smoothed_speed
    with state_lock:
        is_paused = False
        target_track_id = None
        target_plate = None
        locked_plate = None
        locked_class = "UNKNOWN"
        locked_color = "OTHER"
        smoothed_speed = 0.0
        if cap is not None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return jsonify({"status": "reset"})

@app.route('/set_target', methods=['POST'])
def set_target():
    global target_track_id, target_plate, target_class, consecutive_misses, is_paused, target_roi, roi_search_frames, locked_plate, locked_class, locked_color, smoothed_speed, active_system_id
    
    data = request.json
    if not data or 'plate' not in data or 'roi' not in data:
        return jsonify({"error": "Invalid request"}), 400
        
    plate = data['plate']
    roi_norm = data['roi'] # [xmin, ymin, xmax, ymax] normalized
    incoming_sys_id = data.get('system_id')
    
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
        locked_plate = None
        locked_class = "UNKNOWN"
        locked_color = "OTHER"
        target_class = "VEHICLE"
        consecutive_misses = 0
        is_paused = False
        smoothed_speed = 0.0
        active_system_id = incoming_sys_id
        
    return jsonify({"status": "searching"})

@app.route('/switch_camera', methods=['POST'])
def switch_camera():
    global cap, camera_id_global, target_track_id, target_plate, target_class, consecutive_misses, is_paused, target_roi, roi_search_frames, frame_width, frame_height, fps, locked_plate, locked_class, locked_color, smoothed_speed, dvr_start_time
    
    data = request.json
    if not data or 'video_path' not in data or 'camera_id' not in data:
        return jsonify({"error": "Invalid request"}), 400
        
    video_path_rel = data['video_path']
    new_camera_id = data['camera_id']
    
    import os
    video_path = os.path.abspath(video_path_rel)
    if not os.path.exists(video_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alt_path = os.path.abspath(os.path.join(script_dir, video_path_rel))
        if os.path.exists(alt_path):
            video_path = alt_path
        else:
            repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
            clean_rel = video_path_rel.replace("../../", "").replace("..\\..\\", "")
            alt_path2 = os.path.abspath(os.path.join(repo_root, clean_rel))
            if os.path.exists(alt_path2):
                video_path = alt_path2

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
            if fps <= 0:
                fps = 30.0
                
            elapsed_sec = time.time() - dvr_start_time
            total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            
            if total_frames > 0:
                video_duration = total_frames / fps
                seek_sec = elapsed_sec % video_duration
                cap.set(cv2.CAP_PROP_POS_MSEC, seek_sec * 1000.0)
                print(f"[DVR SYNC] Seeked to {seek_sec:.2f}s (Modulo elapsed: {elapsed_sec:.2f}s)")
                
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
        locked_plate = None
        locked_class = "UNKNOWN"
        locked_color = "OTHER"
        target_class = "VEHICLE"
        consecutive_misses = 0
        is_paused = False
        smoothed_speed = 0.0
        centroid_history.clear()
        prev_center = None
        active_system_id = None
        reid_matched = False
        
    return jsonify({"status": "switched", "camera_id": new_camera_id})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CitiSentry Flask Vision Node")
    parser.add_argument("--video", required=True, help="Path to the video file")
    parser.add_argument("--camera_id", required=True, help="Camera node ID (e.g. CAM-001)")
    args = parser.parse_args()

    camera_id_global = args.camera_id
    
    video_path = os.path.abspath(args.video)
    if not os.path.exists(video_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alt_path = os.path.abspath(os.path.join(script_dir, args.video))
        if os.path.exists(alt_path):
            video_path = alt_path
        else:
            repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
            clean_rel = args.video.replace("../../", "").replace("..\\..\\", "")
            alt_path2 = os.path.abspath(os.path.join(repo_root, clean_rel))
            if os.path.exists(alt_path2):
                video_path = alt_path2

    print(f"[VISION] Opening video: {video_path}")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Failed to open {video_path}", file=sys.stderr)
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
