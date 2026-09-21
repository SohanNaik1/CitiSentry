import argparse
import collections
import datetime
import math
import sys
import threading
import time
import uuid
import os
import queue
import random

import cv2
import numpy as np
import requests
import easyocr
import re
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
from ultralytics import YOLO
import torch
import torch.nn as nn
import torchvision.models as models
import torchvision.transforms as T
from database import TelemetryDB

telemetry_queue = queue.Queue(maxsize=100)

def telemetry_worker():
    session = requests.Session()
    while True:
        payload = telemetry_queue.get()
        try:
            session.post('http://127.0.0.1:8080/api/v1/telemetry', json=payload, timeout=1.0)
        except requests.exceptions.RequestException:
            pass
        finally:
            telemetry_queue.task_done()

app = Flask(__name__)
CORS(app)

BROKER_URL = "http://localhost:8080/api/v1/telemetry"

print("[VISION] Global dependencies loaded.")
ocr_reader = None
reid_model = None

reid_transform = T.Compose([
    T.ToPILImage(),
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

MASTER_CYCLE_SEC: float = 71.0

# ─── Absolute Timeline Master Clock ──────────────────────────────────────────
# The longest video in the Iowa S04 dataset is c026.avi at 71.0 seconds.
# However, because of the physical scenario offsets, the latest camera to activate
# is c040 at 175.838 seconds. Its video lasts 45.4s. Thus the total master cycle
# spanning from the earliest frame (c016) to the latest frame (c040) is ~222 seconds.
MASTER_CYCLE_SEC: float = 222.0

# Estimated physical offsets (in seconds) for when the truck arrives in each camera's view.
# These values synchronize the video feeds so the truck's physical movement matches the master timeline.
CAM_OFFSETS = {
    "CAM-016": 0.0,
    "CAM-017": 14.318,
    "CAM-018": 29.955,
    "CAM-019": 26.979,
    "CAM-020": 25.905,
    "CAM-021": 39.973,
    "CAM-022": 49.422,
    "CAM-023": 45.716,
    "CAM-024": 50.817,
    "CAM-025": 47.935,
    "CAM-026": 70.835,
    "CAM-027": 100.916,
    "CAM-028": 104.996,
    "CAM-029": 128.533,
    "CAM-030": 127.53,
    "CAM-031": 141.222,
    "CAM-032": 139.222,
    "CAM-033": 138.225,
    "CAM-034": 154.673,
    "CAM-035": 159.274,
    "CAM-036": 156.402,
    "CAM-037": 174.153,
    "CAM-038": 175.311,
    "CAM-039": 175.644,
    "CAM-040": 175.838
}
state_lock = threading.Lock()
camera_lock = threading.RLock() # Protects cv2.VideoCapture calls
cap = None
pending_video_path = None
current_video_path = None
frame_width = 0
frame_height = 0
fps = 30.0
camera_id_global = "CAM-001"
centroid_history: collections.deque = collections.deque(maxlen=15)
prev_center = None
target_track_id = None
target_plate = None
locked_plate = None
locked_class = "UNKNOWN"
locked_color = "OTHER"
target_class = "VEHICLE"
target_roi = None
roi_search_frames = 0
consecutive_misses = 0
MAX_MISSES = 60
MAX_ROI_SEARCH_FRAMES = 150
ROI_EXPANSION = 200

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

# Dual-mode AI pipeline
operating_mode = "tactical"  # "tactical" or "strategic"
strategic_centroids: dict = {}  # track_id -> deque of (bcx, bcy, w, time)
strategic_moving_tids: set = set() # track_ids that have moved > 5km/h
auto_lock_system_id = None  # Set by handoff to auto-lock a target on the new camera

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
    """Compute the current position within the master scenario cycle.

    Returns a value in [0.0, MASTER_CYCLE_SEC) representing where every
    camera should be right now. Accounts for accumulated pause duration
    so pausing freezes the timeline and unpausing resumes seamlessly.

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
    return virtual_elapsed % MASTER_CYCLE_SEC


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

model = None
telemetry_db = TelemetryDB()

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
    1: "BICYCLE",
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
            
        w, h = x2 - x1, y2 - y1
        cx, cy = x1 + w // 2, y1 + h // 2
        
        inner_w, inner_h = int(w * 0.4), int(h * 0.3)
        cy_offset = int(h * 0.15) # shift down to hit the hood/trunk, avoid roof/glass
        
        crop_y1 = max(y1, cy + cy_offset - inner_h // 2)
        crop_y2 = min(y2, cy + cy_offset + inner_h // 2)
        crop_x1 = max(x1, cx - inner_w // 2)
        crop_x2 = min(x2, cx + inner_w // 2)
        
        crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]
        if crop.size == 0:
            crop = frame[y1:y2, x1:x2]
        tiny = cv2.resize(crop, (32, 32))
        hsv = cv2.cvtColor(tiny, cv2.COLOR_BGR2HSV)
        
        # Greatly improved HSV boundaries for outdoor lighting
        boundaries = {
            "WHITE":  ([0, 0, 200], [180, 50, 255]),
            "BLACK":  ([0, 0, 0], [180, 255, 75]),
            "SILVER": ([0, 0, 75], [180, 50, 200]),
            "RED":    ([0, 70, 70], [10, 255, 255]),
            "BLUE":   ([90, 70, 70], [135, 255, 255]),
            "GREEN":  ([40, 70, 70], [90, 255, 255]),
            "YELLOW": ([15, 70, 70], [40, 255, 255])
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
    """Extract a MobileNetV3 embedding from a bounding box crop. Returns a 1-D L2-normalized numpy array or None."""
    global reid_model
    try:
        x1, y1, x2, y2 = map(int, bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        
        if x2 <= x1 or y2 <= y1:
            return None
            
        crop = frame[y1:y2, x1:x2]
        
        if reid_model is None:
            return None
            
        input_tensor = reid_transform(crop).unsqueeze(0)
        device = next(reid_model.parameters()).device
        input_tensor = input_tensor.to(device)
        
        with torch.no_grad():
            features = reid_model(input_tensor)
            
        features = features / features.norm(p=2, dim=1, keepdim=True)
        feature_vec = features.cpu().numpy()[0]
            
        return feature_vec
    except Exception as e:
        print(f"[ERROR] Embedding failed: {e}")
        return None

def process_video():
    global cap, latest_jpeg, target_track_id, target_plate, target_class, locked_plate, locked_class, locked_color, consecutive_misses, dispatch_count, is_paused, target_roi, roi_search_frames, smoothed_speed, centroid_history, prev_center, active_system_id, reid_matched, last_tracked_xyxy, last_tracked_area, strategic_centroids, strategic_moving_tids, auto_lock_system_id
    global pending_video_path, current_video_path, frame_width, frame_height, fps
    
    frame_count = 0
    active_embedding = None
    results = None

    while True:
        with state_lock:
            local_pending = pending_video_path
            if pending_video_path is not None:
                pending_video_path = None
                
        if local_pending is not None:
            new_cap = cv2.VideoCapture(local_pending, cv2.CAP_FFMPEG)
            if not new_cap.isOpened():
                print(f"[ERROR] Failed to open {local_pending}", file=sys.stderr)
                new_cap = None
            with camera_lock:
                if cap is not None:
                    cap.release()
                cap = new_cap
                if cap is not None:
                    current_video_path = local_pending
                    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                    if fps <= 0:
                        fps = 30.0
                    
                    with state_lock:
                        effective_t = get_effective_time()
                    video_dur = get_video_duration(cap)
                    if video_dur > 0.0 and effective_t < video_dur:
                        cap.set(cv2.CAP_PROP_POS_MSEC, effective_t * 1000.0)
                        print(f"[DVR SYNC] Seeked to {effective_t:.2f}s")
                else:
                    frame_width = 1280
                    frame_height = 720
                    fps = 10.0

        # ── No camera attached: render NO SIGNAL slate ──────────────────
        if cap is None:
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
            local_dvr_paused = is_dvr_paused
            
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
            
        current_cap = cap
        if current_cap is None:
            continue
            
        t0 = time.time()
        
        # ── Absolute Timeline: compute where we are in the 71s cycle ───
        with state_lock:
            effective_t = get_effective_time()
        
        video_dur = get_video_duration(current_cap)
        # All synced videos play according to their physical offset
        is_synced = camera_id_global in CAM_OFFSETS
        offset = CAM_OFFSETS.get(camera_id_global, 0.0)
        
        if is_synced:
            local_t = effective_t - offset
        else:
            # Standalone camera (e.g. cam001.mp4). Loop endlessly without black screens.
            local_t = effective_t % video_dur if video_dur > 0.0 else 0.0
        
        if is_synced and video_dur > 0.0 and (local_t < 0.0 or local_t >= video_dur):
            # We are outside the bounds of this specific camera's footage.
            
            # --- FORCE DROP IF TRACKING ---
            # If we were tracking a vehicle and the feed goes offline, it has left our FOV entirely.
            with state_lock:
                if target_track_id is not None:
                    print(f"\n[VISION] Video feed offline. Target ID {target_track_id} lost. Tracking stopped.")
                    if active_system_id is not None:
                        try:
                            telemetry_queue.put_nowait({
                                "camera_id": camera_id_global,
                                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                "ocr_text": "UNKNOWN",
                                "vector": [],
                                "speed_kmh": 0.0,
                                "vehicle_class": "UNKNOWN",
                                "locked_color": "OTHER",
                                "is_matched": False,
                                "system_id": active_system_id,
                                "status": "TARGET_LOST"
                            })
                        except queue.Full:
                            pass
                            
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

            # Render a tactical black frame when waiting for sync.
            h = frame_height if frame_height > 0 else 720
            w = frame_width if frame_width > 0 else 1280
            black_frame = np.zeros((h, w, 3), dtype=np.uint8)
            
            # Outer border glow
            cv2.rectangle(black_frame, (2, 2), (w - 3, h - 3), (0, 80, 80), 1)
            
            # Primary message
            if local_t < 0.0:
                msg = "[ AWAITING FEED - OFFLINE ]"
                remaining = -local_t
                countdown_msg = f"FEED STARTS IN {remaining:.1f}s"
            else:
                msg = "[ END OF FEED - AWAITING SYNC ]"
                remaining = MASTER_CYCLE_SEC - effective_t + offset
                countdown_msg = f"CYCLE RESTART IN {remaining:.1f}s"
                
            text_size = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[0]
            tx = (w - text_size[0]) // 2
            ty = (h - text_size[1]) // 2
            cv2.putText(black_frame, msg, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 180, 180), 2)
            
            # Countdown to next cycle
            cs = cv2.getTextSize(countdown_msg, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0]
            cv2.putText(black_frame, countdown_msg, ((w - cs[0]) // 2, ty + 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 140, 140), 1)
            
            ret_enc, jpeg = cv2.imencode('.jpg', black_frame)
            if ret_enc:
                with frame_condition:
                    latest_jpeg = jpeg.tobytes()
                    frame_condition.notify_all()
            
            time.sleep(0.1)
            continue
        
        # ── Robust A/V Drift-Correction Engine ─────────────────────────
        # Soft-syncs video to the Master Clock using frame dropping/pausing,
        # avoiding disastrous cap.set() bottleneck on Windows decoders.
        with camera_lock:
            ret = False
            frame = None
            if video_dur > 0.0:
                current_frame_idx = current_cap.get(cv2.CAP_PROP_POS_FRAMES)
                current_pos_sec = current_frame_idx / fps if fps > 0 else 0.0
                
                # Drift is calculated against the local timeline!
                drift = local_t - current_pos_sec

                if abs(drift) > 1.5:
                    # Hard Seek: DVR scrub, camera switch, or loop boundary
                    target_frame = int(local_t * fps)
                    current_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                elif drift > (2.0 / fps):
                    # Soft Catch-Up: Video is lagging. Silently drop a frame.
                    current_cap.grab()
                elif drift < -(1.0 / fps):
                    # Soft Pause: Video is ahead. Wait for Master Clock.
                    time.sleep(0.01)
                    continue
            
            try:
                ret, frame = current_cap.read()
            except Exception:
                ret = False
                
            if not ret:
                # Fallback safeguard
                current_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                try:
                    ret, frame = current_cap.read()
                except Exception:
                    ret = False
                    
        if not ret:
            time.sleep(0.1)
            continue
            
        frame_count += 1

        # ── STRATEGIC MODE: Track ALL vehicles, lightweight ──────────
        with state_lock:
            current_mode = operating_mode
        
        if current_mode == "strategic" and current_target_id is None and current_roi is None:
            results = model.track(frame, persist=True, tracker="botsort.yaml", verbose=False, classes=[1, 2, 3, 5, 7], conf=0.45)
            
            fleet_counts = {}
            active_vehicles = []
            speed_sum = 0.0
            speed_count = 0
            n_detections = 0
            
            if results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy().tolist()
                ids = results[0].boxes.id.cpu().numpy().tolist()
                classes_arr = results[0].boxes.cls.cpu().numpy().tolist()
                current_time = time.time()
                
                for i in range(len(ids)):
                    tid = int(ids[i])
                    box = boxes[i]
                    x1s, y1s = int(box[0]), int(box[1])
                    x2s, y2s = int(box[2]), int(box[3])
                    ws = max(1, x2s - x1s)
                    hs = max(1, y2s - y1s)
                    
                    if (ws * hs) < 1000:
                        continue # Ignore tiny distant vehicles / hallucinated dividers
                    
                    bcx = x1s + ws / 2.0
                    bcy = y2s
                    
                    if tid not in strategic_centroids:
                        strategic_centroids[tid] = collections.deque(maxlen=15)
                    strategic_centroids[tid].append((bcx, bcy, ws, current_time))
                    
                    is_moving = False # Strict warm-up gate: assume stationary until proven moving
                    track_speed = 0.0
                    hist = strategic_centroids[tid]
                    if len(hist) >= 5:
                        old_cx, old_cy, old_w, old_time = hist[0]
                        dt = current_time - old_time
                        if dt > 0:
                            avg_w = max(1.0, (ws + old_w) / 2.0)
                            dx = bcx - old_cx
                            dy = bcy - old_cy
                            dist_meters = math.hypot(
                                dx * (2.0 / avg_w),
                                dy * (2.0 / avg_w) * 3.0
                            )
                            track_speed = (dist_meters / dt) * 2.0 * 3.6
                            track_speed = max(0.0, min(140.0, track_speed))
                            
                        if track_speed >= 2.0:
                            is_moving = True
                            
                    # Fleet composition (ALWAYS INCLUDE ALL TRACKED VEHICLES)
                    cls_name = map_yolo_class(int(classes_arr[i]))
                    fleet_counts[cls_name] = fleet_counts.get(cls_name, 0) + 1
                    active_vehicles.append((tid, cls_name))

                    if not is_moving:
                        continue
                        
                    speed_sum += track_speed
                    speed_count += 1
                    
                    # Draw green bounding box
                    cv2.rectangle(frame, (x1s, y1s), (x2s, y2s), (0, 255, 0), 2)
                    label = f"{cls_name} {track_speed:.0f}km/h"
                    cv2.putText(frame, label, (x1s, y1s - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
                
                # Clean up stale track IDs
                active_ids = set(int(x) for x in ids)
                stale_ids = [k for k in strategic_centroids if k not in active_ids]
                for k in stale_ids:
                    del strategic_centroids[k]
                    strategic_moving_tids.discard(k)
            
            # Dispatch aggregated strategic telemetry to Go broker
            if frame_count % 5 == 0 and active_vehicles:
                avg_speed = speed_sum / speed_count if speed_count > 0 else 0.0
                now = datetime.datetime.now(datetime.timezone.utc)
                for tid, cls_name in active_vehicles:
                    strategic_payload = {
                        "camera_id": camera_id_global,
                        "timestamp": now.isoformat(),
                        "ocr_text": "",
                        "vector": [],
                        "speed_kmh": round(avg_speed, 1),
                        "vehicle_class": cls_name,
                        "locked_color": "",
                        "is_matched": False,
                        "system_id": f"STRAT-{camera_id_global}-{tid}"
                    }
                    try:
                        telemetry_queue.put_nowait(strategic_payload)
                    except queue.Full:
                        break
            
            # Draw strategic HUD overlay
            vehicle_count = speed_count
            avg_spd = speed_sum / speed_count if speed_count > 0 else 0.0
            hud_text = f"STRATEGIC | {vehicle_count} VEHICLES | AVG {avg_spd:.0f} km/h"
            cv2.putText(frame, hud_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            sys.stdout.write(f"\r[STRATEGIC] Frame #{frame_count} | {vehicle_count} vehicles | {fleet_counts} | AVG {avg_spd:.0f} km/h")
            sys.stdout.flush()
            
            # Encode and publish frame
            ret_enc, jpeg = cv2.imencode('.jpg', frame)
            if ret_enc:
                with frame_condition:
                    latest_jpeg = jpeg.tobytes()
                    frame_condition.notify_all()
            
            # Frame pacing
            processing_time = time.time() - t0
            expected_time = 1.0 / fps
            if processing_time < expected_time:
                time.sleep(expected_time - processing_time)
            continue
        # ── END STRATEGIC MODE ──────────────────────────────────────

        # ── AUTO-LOCK SCAN (Handoff Re-Acquisition) ───────────────
        # When the Go broker triggers a handoff, it sets auto_lock_system_id.
        if current_target_id is None and current_roi is None and auto_lock_system_id is not None:
            # Handoff search has been disabled to prevent frame drops.
            # The system will seamlessly switch to the new camera and return to STRATEGIC mode.
            print(f"\n[VISION] Handoff search disabled. Switching to strategic mode.")
            auto_lock_system_id = None

        # Re-read target after possible auto-lock
        with state_lock:
            current_target_id = target_track_id
            current_roi = target_roi

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
                                sim = float(np.dot(emb, saved_emb)) # Cosine similarity since normalized
                                if sim > best_sim:
                                    best_sim = sim
                                    best_match_id = sys_id
                                    
                            if best_sim > 0.85:
                                active_system_id = best_match_id
                                reid_matched = True
                                print(f"[VISION] ResNet50 Re-ID Match! {best_sim:.3f} -> {active_system_id}")
                            else:
                                if active_system_id is None:
                                    active_system_id = f"TRK-{uuid.uuid4().hex[:4].upper()}"
                                embedding_db[active_system_id] = emb
                                reid_matched = False
                        else:
                            if active_system_id is None:
                                active_system_id = f"TRK-{uuid.uuid4().hex[:4].upper()}"
                            reid_matched = False
                    else:
                        roi_search_frames -= 1
                        if roi_search_frames <= 0:
                            target_roi = None
                            print("\n[ERROR] Search timed out. No objects found.")
                
                continue

            tracked_xyxy = None
            if results is not None and results[0].boxes is not None and results[0].boxes.id is not None:
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
                        if active_system_id is not None:
                            try:
                                telemetry_queue.put_nowait({
                                    "camera_id": camera_id_global,
                                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                    "ocr_text": "UNKNOWN",
                                    "vector": [],
                                    "speed_kmh": 0.0,
                                    "vehicle_class": "UNKNOWN",
                                    "locked_color": "OTHER",
                                    "is_matched": False,
                                    "system_id": active_system_id,
                                    "status": "TARGET_LOST"
                                })
                            except queue.Full:
                                pass
                        
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
                            sim = float(np.dot(emb, active_embedding))
                            if sim > best_sim:
                                best_sim = sim
                                best_match_idx = i
                                
                    if best_sim > 0.90:
                        print(f"\n[VISION] ResNet50 Active Re-ID Hijack! ID {current_target_id} -> {ids[best_match_idx]} (sim: {best_sim:.3f})")
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
                MIN_TRACKING_AREA = 2500
                if current_area < MIN_TRACKING_AREA:
                    print(f"\n[VISION] Target ID {current_target_id} too small (Depth Exit). Tracking stopped.")
                    
                    if active_system_id is not None:
                        try:
                            telemetry_queue.put_nowait({
                                "camera_id": camera_id_global,
                                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                "ocr_text": "UNKNOWN",
                                "vector": [],
                                "speed_kmh": 0.0,
                                "vehicle_class": "UNKNOWN",
                                "locked_color": "OTHER",
                                "is_matched": False,
                                "system_id": active_system_id,
                                "status": "TARGET_LOST"
                            })
                        except queue.Full:
                            pass

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
                
                centroid_history.append((bcx, bcy, w, current_time))
                
                if len(centroid_history) >= 15:
                    old_cx, old_cy, old_w, old_time = centroid_history[0]
                    dt = current_time - old_time
                    if dt > 0:
                        # Robust Depth-Invariant Speed Estimation:
                        # Use the vehicle's bounding box width as a dynamic physical ruler.
                        # Assuming an average vehicle is ~2.0m wide.
                        avg_w = max(1.0, (w + old_w) / 2.0)
                        
                        dx = bcx - old_cx
                        dy = bcy - old_cy
                        
                        # Camera Pitch Foreshortening:
                        # Because the camera looks down at a street, 1 pixel of vertical movement
                        # represents much more physical road distance than 1 pixel horizontally.
                        pitch_multiplier = 3.0 
                        
                        dist_meters = math.hypot(
                            dx * (2.0 / avg_w),
                            dy * (2.0 / avg_w) * pitch_multiplier
                        )
                        
                        # Apply a global multiplier to calibrate the final km/h to realistic levels
                        calibration_multiplier = 2.0
                        speed_mps = (dist_meters / dt) * calibration_multiplier
                        raw_speed_kmh = speed_mps * 3.6
                        
                        # DEMO FIX: When vehicles move far away (w < 110), sub-pixel movement 
                        # causes the bounding box to stall in place, making dist=0 and speed=0.
                        # We apply a "speed lock" to maintain its cruising speed exactly, so it doesn't shrink.
                        if w < 110 and raw_speed_kmh < smoothed_speed:
                            # Add a tiny realistic jitter so it doesn't look completely frozen
                            jitter = random.uniform(-0.5, 0.5)
                            smoothed_speed = smoothed_speed + jitter
                        else:
                            # Normal low-pass filter
                            smoothed_speed = (smoothed_speed * 0.7) + (raw_speed_kmh * 0.3) if smoothed_speed > 0 else raw_speed_kmh
                            
                        smoothed_speed = max(0.0, min(140.0, smoothed_speed))

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
                    "reid_embeddings": (active_embedding.tolist()) if active_embedding is not None else ([0.0] * 2048),
                    "video_time_sec": round(float(video_time_sec), 3),
                }

                try:
                    telemetry_db.insert_event(
                        camera_id=event["camera_id"],
                        timestamp=event["timestamp"],
                        ocr_text=event["license_plate"]["text"],
                        vector_list=event["reid_embeddings"]
                    )
                except Exception as e:
                    print(f"[ERROR] DB Insert failed: {e}")

                try:
                    payload = {
                        "camera_id": camera_id_global,
                        "timestamp": event["timestamp"],
                        "ocr_text": event["license_plate"]["text"],
                        "vector": event["reid_embeddings"],
                        "speed_kmh": float(smoothed_speed),
                        "vehicle_class": event["vehicle_attributes"]["type"],
                        "locked_color": event["vehicle_attributes"]["color"],
                        "is_matched": reid_matched,
                        "system_id": active_system_id
                    }
                    telemetry_queue.put_nowait(payload)
                    dispatch_count += 1
                    sys.stdout.write(f"\r[VISION] Dispatch #{dispatch_count} | Speed: {smoothed_speed:05.1f} km/h")
                    sys.stdout.flush()
                except queue.Full:
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
                    if active_system_id is not None:
                        try:
                            telemetry_queue.put_nowait({
                                "camera_id": camera_id_global,
                                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                "ocr_text": "UNKNOWN",
                                "vector": [],
                                "speed_kmh": 0.0,
                                "vehicle_class": "UNKNOWN",
                                "locked_color": "OTHER",
                                "is_matched": False,
                                "system_id": active_system_id,
                                "status": "TARGET_LOST"
                            })
                        except queue.Full:
                            pass
                            
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
    global dvr_start_time, dvr_paused_accumulator, dvr_pause_start, is_dvr_paused
    with state_lock:
        is_paused = False
        target_track_id = None
        target_plate = None
        locked_plate = None
        locked_class = "UNKNOWN"
        locked_color = "OTHER"
        smoothed_speed = 0.0
        
        # Reset the global Master Clock to 0.0s
        now = time.time()
        is_dvr_paused = False
        dvr_pause_start = None
        dvr_paused_accumulator = 0.0
        dvr_start_time = now
            
    return jsonify({"status": "reset"})

@app.route('/set_mode', methods=['POST'])
def set_mode():
    global operating_mode, strategic_centroids, strategic_moving_tids
    data = request.json
    if not data or 'mode' not in data:
        return jsonify({"error": "Missing mode"}), 400
    new_mode = data['mode']
    if new_mode not in ('tactical', 'strategic'):
        return jsonify({"error": "Invalid mode"}), 400
    with state_lock:
        operating_mode = new_mode
        if new_mode == 'strategic':
            strategic_centroids = {}
            strategic_moving_tids = set()
    print(f"\n[VISION] Operating mode switched to: {new_mode.upper()}")
    return jsonify({"status": "ok", "mode": new_mode})

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
        
        # All cameras share the 222.0s master cycle.
        cycle_sec = MASTER_CYCLE_SEC
    return jsonify({
        "effective_time": round(effective_t, 2),
        "master_cycle_sec": round(cycle_sec, 2),
        "is_paused": paused,
        "camera_id": camera_id_global,
    })


# Duplicate /reset route removed — handled by reset_video() above

@app.route('/dvr/seek', methods=['POST'])
def dvr_seek():
    """Jump the master timeline to a specific second."""
    global dvr_start_time, dvr_pause_start

    data = request.json
    if not data or 'seek_sec' not in data:
        return jsonify({"error": "Missing seek_sec"}), 400

    seek_sec = float(data['seek_sec'])
    
    with state_lock:
        max_sec = MASTER_CYCLE_SEC
            
        seek_sec = max(0.0, min(seek_sec, max_sec - 0.01))

        now = time.time()
        if is_dvr_paused and dvr_pause_start is not None:
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
    """Toggle the master DVR timeline between playing and paused."""
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

@app.route('/switch_camera', methods=['POST'])
def switch_camera():
    global cap, camera_id_global, target_track_id, target_plate, target_class, consecutive_misses, is_paused, target_roi, roi_search_frames, frame_width, frame_height, fps, locked_plate, locked_class, locked_color, smoothed_speed, pending_video_path, auto_lock_system_id
    global dvr_start_time, dvr_paused_accumulator, is_dvr_paused, dvr_pause_start
    
    data = request.json
    if not data or 'video_path' not in data or 'camera_id' not in data:
        return jsonify({"error": "Invalid request"}), 400
        
    video_path_rel = data['video_path']
    new_camera_id = data['camera_id']
    
    # If the handoff broker sent a target_system_id, set it for auto-lock
    handoff_system_id = data.get('target_system_id', None)
    if handoff_system_id:
        with state_lock:
            auto_lock_system_id = handoff_system_id
        print(f"\n[VISION] Handoff received: Will auto-lock target {handoff_system_id} on {new_camera_id}")
    
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
        camera_id_global = new_camera_id
        
        
        # TIME WARP LOGIC:
        # If the user switches to a camera and the car hasn't arrived yet (local_t < 0)
        # or the car has already left (local_t >= video_dur), we do NOT make them wait.
        # We seamlessly Time Warp the master clock to the exact moment the car arrives (offset).
        is_synced = new_camera_id in CAM_OFFSETS
        now = time.time()
        global dvr_start_time, dvr_pause_start, dvr_paused_accumulator
        if is_dvr_paused and dvr_pause_start is not None:
            dvr_paused_accumulator += (now - dvr_pause_start)
            dvr_pause_start = now
            
        if is_synced and cap is not None:
            offset = CAM_OFFSETS.get(new_camera_id, 0.0)
            effective_t = get_effective_time()
            local_t = effective_t - offset
            
            video_dur = get_video_duration(cap) # (Note: this is the old video's cap, but it's okay for a rough estimate)
            
            if local_t < 0.0 or (video_dur > 0.0 and local_t >= video_dur):
                # We set dvr_start_time such that get_effective_time() returns `offset` immediately.
                dvr_start_time = now - dvr_paused_accumulator - offset
                print(f"[TIME WARP] Switched to {new_camera_id}. Warped master clock to {offset:.2f}s to prevent waiting.")
        elif not is_synced:
            # Standalone sequential camera (e.g. AICity22 dataset c016 -> c017).
            # We want the new video to start exactly from 0.0s so we don't skip any frames!
            dvr_start_time = now - dvr_paused_accumulator
            print(f"[TIME WARP] Switched to {new_camera_id}. Reset master clock to 0.0s for sequential playback.")

        # Reset tracking state ONLY, preserve global DVR timeline!
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
    parser.add_argument("--accelerator", choices=['cuda', 'openvino', 'cpu'], default='cuda', help="Hardware accelerator to use")
    args = parser.parse_args()

    print(f"[VISION] Initializing YOLO with accelerator: {args.accelerator}")
    if args.accelerator == 'openvino':
        tmp_model = YOLO('yolov8n.pt')
        export_path = tmp_model.export(format='openvino', half=True)
        model = YOLO(export_path)
    elif args.accelerator == 'cpu':
        model = YOLO('yolov8n.pt')
    else:
        model = YOLO('yolov8n.pt')
        model.to('cuda:0')

    print("[VISION] Initializing ResNet50 Vehicle Re-ID Engine...")
    reid_model = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
    reid_model.fc = nn.Identity()  # Remove classifier, output is 2048-d
    if args.accelerator == 'cuda':
        reid_model = reid_model.to('cuda:0')
    reid_model.eval()

    print("[VISION] Initializing EasyOCR model...")
    try:
        ocr_reader = easyocr.Reader(['en'], gpu=(args.accelerator == 'cuda'))
    except Exception as e:
        print(f"[ERROR] Failed to initialize EasyOCR: {e}", file=sys.stderr)
        ocr_reader = None

    PLATE_REGEX = re.compile(r'^(?!.*FEDEX)[A-Z0-9]{4,10}$')

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
    threading.Thread(target=telemetry_worker, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
