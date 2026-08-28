import json
import os
import uuid
from datetime import datetime, timezone, timedelta
import random

def generate_embedding():
    return [random.uniform(-1.0, 1.0) for _ in range(128)]

def generate_telemetry_event(camera_id, dt, plate_text, confidence, is_clean, vehicle_type, color):
    epoch_ms = int(dt.timestamp() * 1000)
    return {
        "event_id": str(uuid.uuid4()),
        "camera_id": camera_id,
        "timestamp": dt.isoformat(),
        "epoch_ms": epoch_ms,
        "license_plate": {
            "text": plate_text,
            "confidence": confidence,
            "is_clean": is_clean
        },
        "bounding_box": [0.2, 0.3, 0.4, 0.5], # [xmin, ymin, xmax, ymax]
        "vehicle_attributes": {
            "type": vehicle_type,
            "color": color,
            "color_confidence": 0.95
        },
        "speed_kmh": 60.0,
        "heading_degrees": 180.0,
        "reid_embeddings": generate_embedding()
    }

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base_dir, exist_ok=True)

    # Use current time as base time for the scenarios
    base_time = datetime.now(timezone.utc).replace(microsecond=0)

    # Scenario 1: Pursuit
    # A white SUV with plate "KA01AB1234" is detected at CAM-001.
    # 60 seconds later, it is detected at CAM-002.
    # 120 seconds later, it is detected at CAM-003.
    # Confidence should be high (>0.90) and is_clean should be true.
    scen1_events = [
        generate_telemetry_event("CAM-001", base_time, "KA01AB1234", 0.95, True, "SUV", "WHITE"),
        generate_telemetry_event("CAM-002", base_time + timedelta(seconds=60), "KA01AB1234", 0.96, True, "SUV", "WHITE"),
        generate_telemetry_event("CAM-003", base_time + timedelta(seconds=180), "KA01AB1234", 0.98, True, "SUV", "WHITE"),
    ]
    with open(os.path.join(base_dir, "scenario_1_pursuit.json"), "w") as f:
        json.dump(scen1_events, f, indent=2)

    # Scenario 2: Ambiguity
    # A black SEDAN is detected at CAM-001 with plate "KA04MH1001" (confidence 0.95).
    # 45 seconds later, it is detected at CAM-002, but the OCR misread it due to dirt/blur: 
    # plate "KA04MH1O01" (Letter 'O' instead of zero '0', confidence 0.65, is_clean: false).
    scen2_events = [
        generate_telemetry_event("CAM-001", base_time, "KA04MH1001", 0.95, True, "SEDAN", "BLACK"),
        generate_telemetry_event("CAM-002", base_time + timedelta(seconds=45), "KA04MH1O01", 0.65, False, "SEDAN", "BLACK"),
    ]
    with open(os.path.join(base_dir, "scenario_2_ambiguity.json"), "w") as f:
        json.dump(scen2_events, f, indent=2)

    # Scenario 3: Cloned Plate
    # A red HATCHBACK with plate "DL10CX5555" is detected at CAM-001.
    # Exactly 2 seconds later, the exact same plate is detected at CAM-005.
    scen3_events = [
        generate_telemetry_event("CAM-001", base_time, "DL10CX5555", 0.99, True, "HATCHBACK", "RED"),
        generate_telemetry_event("CAM-005", base_time + timedelta(seconds=2), "DL10CX5555", 0.98, True, "HATCHBACK", "RED"),
    ]
    with open(os.path.join(base_dir, "scenario_3_cloned.json"), "w") as f:
        json.dump(scen3_events, f, indent=2)

    print("Successfully generated 3 scenario files.")

if __name__ == "__main__":
    main()
