import argparse
import collections
import datetime
import math
import sys
import threading
import time
import uuid
import os

import cv2
import numpy as np
import requests
import easyocr
import re
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
from ultralytics import YOLO
import torch

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

CAMERA_OFFSETS: dict[str, float] = {}
def load_offsets():
    local_offset = os.path.join(os.path.dirname(os.path.abspath(__file__)), "S04.txt")
    offset_file = local_offset if os.path.exists(local_offset) else "/home/sohan/Downloads/AICity22_Track1_MTMC_Tracking/cam_timestamp/S04.txt"
    if os.path.exists(offset_file):
        with open(offset_file, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 2:
                    CAMERA_OFFSETS[parts[0]] = float(parts[1])
load_offsets()

# ── Absolute Timeline Master Clock ──────────────────────────────────────────
# S04 Dataset covers exactly 222 seconds (c040 offset 175.8s + 45.4s duration = 221.2s).
MASTER_CYCLE_SEC: float = 222.0

# Global state
state_lock = threading.Lock()
camera_lock = threading.RLock() # Protects cv2.VideoCapture calls
cap = None
pending_video_path = None
pending_new_cam_id = None
frame_width = 0
frame_height = 0
fps = 30.0
camera_id_global = "CAM-001"
current_frame_index = 0
centroid_history: collections.deque = collections.deque(maxlen=15)
prev_center = None

# DVR clock state (all protected by state_lock)
dvr_start_time: float = time.time()       # Wall-clock anchor for t=0
dvr_paused_accumulator: float = 0.0       # Total seconds spent paused (subtracted from elapsed)
dvr_pause_start: float | None = None      # Wall-clock timestamp when pause began, None if playing
is_dvr_paused: bool = False               # True when the timeline is frozen

embedding_db: dict = {}  # Maps system_id -> embedding (tensor)
active_system_id = None
active_embedding = None
last_tracked_xyxy = None
last_tracked_area = None
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
is_paused = False         # Legacy per-target pause (ROI selection flow)
smoothed_speed = 0.0

target_roi = None
roi_search_frames = 0
MAX_ROI_SEARCH_FRAMES = 30

latest_jpeg = None
frame_condition = threading.Condition()


def get_effective_time() -> float:
    """Compute the current position in the absolute master timeline.

    Returns the absolute virtual elapsed seconds since the system started.
    This value never resets, allowing each individual camera to modulo
    at its own exact native duration without jumping randomly.
    Accounts for accumulated pause duration so pausing freezes the timeline
    and unpausing resumes seamlessly.

    Must be called while state_lock is held, or with local copies of the
    DVR variables.
    """
    now = time.time()
    wall_elapsed = now - dvr_start_time
    if is_dvr_paused and dvr_pause_start is not None:
        # While paused, subtract the time since pause began
        current_pause_duration = now - dvr_pause_start
        virtual_elapsed = wall_elapsed - dvr_paused_accumulator - current_pause_duration
    else:
        virtual_elapsed = wall_elapsed - dvr_paused_accumulator
    # Clamp to non-negative before modulo (guards against float drift)
    virtual_elapsed = max(0.0, virtual_elapsed)
    return virtual_elapsed


def get_video_duration(capture: cv2.VideoCapture) -> float:
    """Return the duration (in seconds) of the video loaded in a cv2.VideoCapture.

    Falls back to 0.0 if metadata is unavailable.
    """
    with camera_lock:
        total_frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        vid_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    if vid_fps <= 0:
        vid_fps = 30.0
    if total_frames > 0:
        return total_frames / vid_fps
    return 0.0

yolo_weights = os.getenv("YOLO_MODEL", "yolov8s.pt")
if not os.path.exists(yolo_weights):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(script_dir, yolo_weights)
    if os.path.exists(candidate):
        yolo_weights = candidate
    elif os.path.exists(os.path.join(script_dir, "yolov8s.pt")):
        yolo_weights = os.path.join(script_dir, "yolov8s.pt")
    elif os.path.exists(os.path.join(script_dir, "yolov8n.pt")):
        yolo_weights = os.path.join(script_dir, "yolov8n.pt")
    elif os.path.exists(os.path.join(script_dir, "yolo11x.pt")):
        yolo_weights = os.path.join(script_dir, "yolo11x.pt")
print(f"[VISION] Loading YOLO model: {yolo_weights}")
model = YOLO(yolo_weights)

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

def compute_iom(box_a: list[float], box_b: list[float]) -> float:
    """Intersection over Minimum Area (IoM). Good for part-to-whole matching."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter == 0.0:
        return 0.0

    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    min_area = min(area_a, area_b)
    
    return inter / min_area if min_area > 0 else 0.0

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

def get_embedding(frame: np.ndarray, bbox: list[float]) -> np.ndarray | None:
    return None

def process_video():
    global cap, latest_jpeg, target_track_id, target_plate, target_class, locked_plate, locked_class, locked_color, consecutive_misses, dispatch_count, is_paused, target_roi, roi_search_frames, smoothed_speed, centroid_history, prev_center, active_system_id, reid_matched, last_tracked_xyxy, last_tracked_area
    global pending_video_path, pending_new_cam_id, frame_width, frame_height, fps, current_frame_index, camera_id_global
    
    frame_count = 0
    active_embedding = None

    while True:
        with state_lock:
            local_pending = pending_video_path
            local_new_cam_id = pending_new_cam_id
            if pending_video_path is not None:
                pending_video_path = None
                pending_new_cam_id = None
                
        if local_pending is not None:
            # Snapshot old camera state BEFORE spawning the switch thread
            with camera_lock:
                snap_old_frame_idx = current_frame_index
                snap_old_fps = fps
                snap_old_cam_id = camera_id_global  # e.g. "c022" (set by previous bg_seek)
            
            def bg_seek(path, old_idx, old_fps_val, old_cam_id):
                global cap, frame_width, frame_height, fps, camera_id_global, current_frame_index
                try:
                    c_new = cv2.VideoCapture(path)
                    if c_new.isOpened():
                        f_fps = c_new.get(cv2.CAP_PROP_FPS) or 30.0
                        if f_fps > 100: f_fps = 30.0
                        
                        new_frame_idx = 0
                        is_avi = path.lower().endswith('.avi')
                        if is_avi:
                            c_id = os.path.basename(path).replace('.avi', '')
                            new_cam_off = CAMERA_OFFSETS.get(c_id, 0.0)
                            new_vid_dur = c_new.get(cv2.CAP_PROP_FRAME_COUNT) / f_fps
                            
                            # Use snapshotted old state (race-free)
                            old_video_time = old_idx / old_fps_val
                            # Normalize old camera ID: "CAM-022" → "c022" or already "c022"
                            old_key = old_cam_id.lower().replace('cam-', 'c') if old_cam_id else ''
                            old_cam_off = CAMERA_OFFSETS.get(old_key, 0.0)
                            
                            # Convert old video position to global time, then to new camera position
                            global_time = old_video_time + old_cam_off
                            if new_vid_dur > 0:
                                new_video_time = (global_time - new_cam_off) % new_vid_dur
                            else:
                                new_video_time = 0.0
                            
                            target_f = int(new_video_time * f_fps)
                            c_new.set(cv2.CAP_PROP_POS_FRAMES, target_f)
                            new_frame_idx = target_f
                            print(f"[DVR SYNC] Switch: old={old_cam_id}@{old_video_time:.2f}s(off={old_cam_off:.1f}) → global={global_time:.2f} → {c_id}@{new_video_time:.2f}s(off={new_cam_off:.1f}) frame={target_f}")
                            
                        with camera_lock:
                            if cap is not None: cap.release()
                            current_frame_index = new_frame_idx
                            cap = c_new
                            frame_width = int(c_new.get(cv2.CAP_PROP_FRAME_WIDTH))
                            frame_height = int(c_new.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            fps = f_fps
                            if is_avi:
                                camera_id_global = c_id
                                
                        print(f"[DVR SYNC] Async switch complete to {path} at frame {new_frame_idx}")
                except Exception as e:
                    print(f"[DVR SYNC] Error in bg_seek: {e}")
                        
            threading.Thread(target=bg_seek, args=(local_pending, snap_old_frame_idx, snap_old_fps, snap_old_cam_id), daemon=True).start()

        # ── No camera attached: render NO SIGNAL slate ──────────────────
        with camera_lock:
            if cap is None:
                frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                cv2.putText(frame, "NO SIGNAL", (520, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
                import cv2 as cv
                ret, jpeg = cv.imencode('.jpg', frame)
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
            local_dvr_paused = is_dvr_paused
            
        if local_dvr_paused:
            with frame_condition:
                if latest_jpeg is not None:
                    frame_condition.notify_all()
            time.sleep(0.2)
            continue
            
        # ── DVR Timeline paused: keep yielding last frame at ~5 FPS ────
        # The MJPEG stream must continue producing frames or the browser
        # <img> tag will stall and show a broken-image icon.
        if local_dvr_paused:
            with frame_condition:
                if latest_jpeg is not None:
                    frame_condition.notify_all()
            time.sleep(0.2)   # ~5 FPS idle yield
            continue

        if current_paused:
            time.sleep(0.1)
            continue

        t0 = time.time()
        
        with camera_lock:
            if cap is None: continue
            
            # Simple sequential read — no drift correction, no frame skipping
            ret, frame = cap.read()
            if not ret:
                # EOF: loop back to start
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                current_frame_index = 0
                ret, frame = cap.read()
                if not ret: continue
            current_frame_index += 1
                        
        frame_count += 1
        if current_target_id is not None or current_roi is not None:
            # Use 0.30 for initial ROI locking to avoid ghosts, but 0.15 for tracking to maintain through occlusions
            current_conf = 0.15 if current_target_id is not None else 0.30
            results = model.track(frame, persist=True, tracker="botsort.yaml", verbose=False, classes=[1, 2, 3, 5, 7], conf=current_conf)
            
            if current_roi is not None:
                found_id = None
                found_class = "VEHICLE"
                found_bbox = None
                
                if results[0].boxes is not None and results[0].boxes.id is not None:
                    boxes = results[0].boxes.xyxy.cpu().numpy().tolist()
                    ids = results[0].boxes.id.cpu().numpy().tolist()
                    classes = results[0].boxes.cls.cpu().numpy().tolist()
                    
                    user_cx = (current_roi[0] + current_roi[2]) / 2
                    user_cy = (current_roi[1] + current_roi[3]) / 2
                    
                    best_score = -float('inf')
                    for i in range(len(boxes)):
                        box = boxes[i]
                        cx = (box[0] + box[2]) / 2
                        cy = (box[1] + box[3]) / 2
                        dist = math.hypot(cx - user_cx, cy - user_cy)
                        
                        # Normalize distance against YOLO bounding box diagonal instead of the user's box
                        box_diag = math.hypot(box[2] - box[0], box[3] - box[1]) + 1e-6
                        norm_dist = dist / box_diag
                        
                        # Use Intersection over Minimum Area (IoM)
                        iom = compute_iom(current_roi, box)
                        
                        score = iom - (norm_dist * 1.5)
                        
                        if (iom > 0.0 or norm_dist < 1.0) and score > best_score:
                            best_score = score
                            found_id = ids[i]
                            found_bbox = box
                            found_class = map_yolo_class(int(classes[i]))
                            found_color = extract_dominant_color(frame, box)
                
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
                                sim = reid_engine.compute_similarity(emb, saved_emb)
                                if sim > best_sim:
                                    best_sim = sim
                                    best_match_id = sys_id
                                    
                            if best_sim > 0.75:
                                active_system_id = best_match_id
                                reid_matched = True
                                print(f"[VISION] OSNet Re-ID Match! {best_sim:.3f} -> {active_system_id}")
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

                # --- ACTIVE RE-ID SEARCH BLOCK ---
                if tracked_xyxy is None and active_embedding is not None:
                    # Check if the target drove off the edge of the frame
                    left_frame = False
                    if last_tracked_xyxy is not None:
                        lx1, ly1, lx2, ly2 = last_tracked_xyxy
                        if lx1 < 20 or ly1 < 20 or lx2 > frame_width - 20 or ly2 > frame_height - 20:
                            left_frame = True
                            
                    if left_frame:
                        print(f"\n[VISION] Target ID {current_target_id} exited frame. Tracking stopped.")
                        with state_lock:
                            target_track_id = None
                            target_plate = None
                            locked_plate = None
                            locked_class = "UNKNOWN"
                            locked_color = "OTHER"
                            target_roi = None
                        active_system_id = None
                        active_embedding = None
                        last_tracked_xyxy = None
                        last_tracked_area = None
                        reid_matched = False
                        continue

                    # Spatial tracker dropped the ID. Scan all current boxes.
                    best_sim = -1.0
                    best_match_idx = -1
                    
                    for i in range(len(ids)):
                        candidate_w = boxes[i][2] - boxes[i][0]
                        candidate_h = boxes[i][3] - boxes[i][1]
                        candidate_area = candidate_w * candidate_h
                        
                        if last_tracked_area is not None and last_tracked_area > 0:
                            scale_ratio = candidate_area / last_tracked_area
                            if scale_ratio > 2.5 or scale_ratio < 0.4:
                                continue  # Physics Gate: Physically impossible scale change
                                
                        emb = get_embedding(frame, boxes[i])
                        if emb is not None:
                            sim = reid_engine.compute_similarity(emb, active_embedding)
                            if sim > best_sim:
                                best_sim = sim
                                best_match_idx = i
                                
                    if best_sim > 0.82:
                        print(f"\n[VISION] OSNet Active Re-ID Hijack! ID {current_target_id} -> {ids[best_match_idx]} (sim: {best_sim:.3f})")
                        with state_lock:
                            target_track_id = ids[best_match_idx]
                        current_target_id = ids[best_match_idx]
                        tracked_xyxy = boxes[best_match_idx]
                # ---------------------------------

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
                
                # --- DEPTH EXIT CHECK ---
                current_area = w * h
                MIN_TRACKING_AREA = 400
                if current_area < MIN_TRACKING_AREA:
                    print(f"\n[VISION] Target ID {current_target_id} too small (Depth Exit). Tracking stopped.")
                    with state_lock:
                        target_track_id = None
                        target_plate = None
                        locked_plate = None
                        locked_class = "UNKNOWN"
                        locked_color = "OTHER"
                        target_roi = None
                    active_system_id = None
                    active_embedding = None
                    last_tracked_xyxy = None
                    last_tracked_area = None
                    reid_matched = False
                    continue
                
                last_tracked_area = current_area
                # ------------------------
                
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
                    
                # Dynamically update embedding to capture scale/rotation changes periodically
                if frame_count % 15 == 0:
                    current_emb = get_embedding(frame, tracked_xyxy)
                    if current_emb is not None:
                        if active_embedding is not None:
                            # EMA Blend (numpy)
                            blended = (active_embedding * 0.9) + (current_emb * 0.1)
                            # Re-normalize (L2)
                            norm = np.linalg.norm(blended)
                            active_embedding = blended / norm if norm > 0 else blended
                        else:
                            active_embedding = current_emb
                        # Persist to global DB for future re-acquisition
                        embedding_db[active_system_id] = active_embedding

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
                    "reid_embeddings": (active_embedding[:128].tolist()) if active_embedding is not None else ([0.0] * 128),
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
                last_tracked_xyxy = tracked_xyxy
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

        # Calculate time taken and sleep if processing is faster than real-time
        processing_time = time.time() - t0
        expected_time = 1.0 / fps
        
        if processing_time < expected_time:
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
    global is_paused, is_dvr_paused, dvr_pause_start
    with state_lock:
        is_paused = True
        if not is_dvr_paused:
            dvr_pause_start = time.time()
            is_dvr_paused = True
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
        with camera_lock:
            if cap is not None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return jsonify({"status": "reset"})

@app.route('/set_target', methods=['POST'])
def set_target():
    global target_track_id, target_plate, target_class, consecutive_misses, is_paused, target_roi, roi_search_frames, locked_plate, locked_class, locked_color, smoothed_speed, active_system_id
    global is_dvr_paused, dvr_pause_start, dvr_paused_accumulator
    
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
        
        # Auto-unpause the DVR timeline so tracking begins immediately
        now = time.time()
        if is_dvr_paused:
            if dvr_pause_start is not None:
                dvr_paused_accumulator += (now - dvr_pause_start)
                dvr_pause_start = None
            is_dvr_paused = False
        
    return jsonify({"status": "searching"})

# ── DVR Timeline Control Endpoints ──────────────────────────────────────────

@app.route('/dvr/status', methods=['GET'])
def dvr_status():
    """Return the current master DVR clock state for the frontend scrubber."""
    with state_lock:
        effective_t = get_effective_time()
        paused = is_dvr_paused
    return jsonify({
        "effective_time": round(effective_t, 2),
        "master_cycle_sec": MASTER_CYCLE_SEC,
        "is_paused": paused,
        "camera_id": camera_id_global,
    })


@app.route('/dvr/seek', methods=['POST'])
def dvr_seek():
    """Jump the master timeline to a specific second within [0, MASTER_CYCLE_SEC).

    The math: We want get_effective_time() to return `seek_sec` immediately.
    effective_time = (now - dvr_start_time - paused_acc) % MASTER_CYCLE_SEC

    When playing:  virtual_elapsed = now - dvr_start_time - paused_acc
                   Set dvr_start_time = now - paused_acc - seek_sec
    When paused:   virtual_elapsed also subtracts (now - dvr_pause_start).
                   Reset dvr_pause_start = now so that extra term is zero,
                   then set dvr_start_time = now - paused_acc - seek_sec.
    """
    global dvr_start_time, dvr_pause_start

    data = request.json
    if not data or 'seek_sec' not in data:
        return jsonify({"error": "Missing seek_sec"}), 400

    seek_sec = float(data['seek_sec'])
    seek_sec = max(0.0, min(seek_sec, MASTER_CYCLE_SEC - 0.01))

    now = time.time()
    with state_lock:
        if is_dvr_paused and dvr_pause_start is not None:
            # Flush the old pause segment into the accumulator and restart
            # the pause clock at 'now' so get_effective_time()'s
            # (now - dvr_pause_start) term is zero at this instant.
            dvr_paused_accumulator_local = dvr_paused_accumulator + (now - dvr_pause_start)
            dvr_pause_start = now
            dvr_start_time = now - dvr_paused_accumulator_local - seek_sec
        else:
            dvr_start_time = now - dvr_paused_accumulator - seek_sec
        effective_t = get_effective_time()

    print(f"[DVR] Seeked to {effective_t:.2f}s (requested {seek_sec:.2f}s)")
    return jsonify({"status": "seeked", "effective_time": round(effective_t, 2)})


@app.route('/dvr/toggle_pause', methods=['POST'])
def dvr_toggle_pause():
    """Toggle the master DVR timeline between playing and paused.

    When pausing:  Record dvr_pause_start = now.
    When resuming: Add (now - dvr_pause_start) to dvr_paused_accumulator,
                   then clear dvr_pause_start.
    """
    global is_dvr_paused, dvr_pause_start, dvr_paused_accumulator

    now = time.time()
    with state_lock:
        if is_dvr_paused:
            # ── Resume ──
            if dvr_pause_start is not None:
                dvr_paused_accumulator += (now - dvr_pause_start)
                dvr_pause_start = None
            is_dvr_paused = False
            new_state = "playing"
        else:
            # ── Pause ──
            dvr_pause_start = now
            is_dvr_paused = True
            new_state = "paused"
        effective_t = get_effective_time()

    print(f"[DVR] Timeline {new_state} at {effective_t:.2f}s")
    return jsonify({"status": new_state, "effective_time": round(effective_t, 2)})

@app.route('/reset_sync', methods=['POST'])
def reset_sync():
    """Resets the global AVI sync clock to the beginning of the loop."""
    global dvr_start_time, dvr_paused_accumulator, is_dvr_paused, dvr_pause_start, current_frame_index
    with state_lock:
        dvr_start_time = time.time()
        dvr_paused_accumulator = 0.0
        is_dvr_paused = False
        dvr_pause_start = None
    with camera_lock:
        if cap is not None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            current_frame_index = 0
    return jsonify({"status": "sync_reset"})

@app.route('/switch_camera', methods=['POST'])
def switch_camera():
    global cap, camera_id_global, target_track_id, target_plate, target_class, consecutive_misses, is_paused, target_roi, roi_search_frames, frame_width, frame_height, fps, locked_plate, locked_class, locked_color, smoothed_speed, pending_video_path
    
    data = request.json
    if not data or 'video_path' not in data or 'camera_id' not in data:
        return jsonify({"error": "Invalid request"}), 400
        
    video_path_rel = data['video_path']
    new_camera_id = data['camera_id']
    
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
        print(f"\n[VISION] Queueing camera switch to {new_camera_id}: {video_path}")
        pending_video_path = video_path
        pending_new_cam_id = new_camera_id
        # NOTE: Do NOT set camera_id_global here — bg_seek will set it
        # after snapshotting the old state. Setting it here causes a race condition.
        
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
        last_tracked_area = None
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

    print(f"[VISION] Queueing initial video: {video_path}")
    pending_video_path = video_path

    # Start processing thread
    t = threading.Thread(target=process_video, daemon=True)
    t.start()

    dvr_start_time = time.time()
    
    import signal
    def handle_sigint(sig, frame):
        print("\n[VISION] Shutting down...")
        os._exit(0)
    signal.signal(signal.SIGINT, handle_sigint)
    
    print("[VISION] Starting Flask server on port 5000...")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
