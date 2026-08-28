import argparse
import json
import time
import sys
from typing import List, Dict, Any
import requests
from requests.exceptions import RequestException

def load_events(filepath: str) -> List[Dict[str, Any]]:
    with open(filepath, 'r') as f:
        events = json.load(f)
    if not isinstance(events, list):
        raise ValueError("Scenario file must contain a JSON array of events.")
    return events

def main() -> None:
    parser = argparse.ArgumentParser(description="Edge Simulator & Replay Harness")
    parser.add_argument("--scenario", type=str, required=True, help="Path to the scenario JSON file")
    parser.add_argument("--target", type=str, default="http://localhost:8080/api/v1/telemetry", help="Target URL for the Go broker")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier")
    
    args = parser.parse_args()
    
    try:
        events = load_events(args.scenario)
    except Exception as e:
        print(f"[ERROR] Failed to load scenario file: {e}")
        sys.exit(1)
        
    if not events:
        print("[WARN] Scenario file is empty. Exiting.")
        sys.exit(0)
        
    # Sort events chronologically based on epoch_ms
    events.sort(key=lambda x: x.get("epoch_ms", 0))
    
    print(f"--- Starting Simulation ---")
    print(f"Scenario: {args.scenario}")
    print(f"Target: {args.target}")
    print(f"Speed Multiplier: {args.speed}x")
    print(f"Total Events: {len(events)}\n")
    
    previous_epoch_ms: int | None = None
    
    for idx, event in enumerate(events):
        current_epoch_ms = event.get("epoch_ms")
        
        if current_epoch_ms is None:
            print(f"[ERROR] Event at index {idx} is missing 'epoch_ms'. Skipping.")
            continue
            
        if previous_epoch_ms is not None:
            delta_seconds = (current_epoch_ms - previous_epoch_ms) / 1000.0
            sleep_time = delta_seconds / args.speed
            if sleep_time > 0:
                print(f"[*] Sleeping for {sleep_time:.2f} seconds (Real delta: {delta_seconds:.2f}s)...")
                time.sleep(sleep_time)
                
        # Dispatch event
        event_id = event.get("event_id", "UNKNOWN")
        plate_text = event.get("license_plate", {}).get("text", "UNKNOWN")
        camera_id = event.get("camera_id", "UNKNOWN")
        
        try:
            response = requests.post(args.target, json=event, timeout=5.0)
            response.raise_for_status()
            print(f"[SUCCESS] Dispatched Event {event_id} for Plate {plate_text} at Camera {camera_id}.")
        except RequestException:
            print(f"[WARN] Broker unreachable. Simulated dispatch of Event {event_id} for Plate {plate_text} at Camera {camera_id}.")
            
        previous_epoch_ms = current_epoch_ms
        
    print("\n--- Simulation Complete ---")

if __name__ == "__main__":
    main()
