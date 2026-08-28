import json
import os
import sys

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    nodes_path = os.path.join(base_dir, 'camera_nodes.json')
    graph_path = os.path.join(base_dir, 'spatial_graph.json')

    print("--- Starting Topology Validation ---")

    try:
        nodes = load_json(nodes_path)
        edges = load_json(graph_path)
    except Exception as e:
        print(f"FAIL: Could not load JSON files. Error: {e}")
        sys.exit(1)

    print("PASS: Successfully loaded camera_nodes.json and spatial_graph.json")

    # Rule a: Ensure there are no duplicate camera_ids in camera_nodes.json
    camera_ids = set()
    for node in nodes:
        cid = node.get("camera_id")
        if not cid:
            print("FAIL: Camera node missing 'camera_id'.")
            sys.exit(1)
        if cid in camera_ids:
            print(f"FAIL: Duplicate camera_id detected: {cid}")
            sys.exit(1)
        camera_ids.add(cid)
    print("PASS: No duplicate camera_ids found.")

    # Rule b & c: Ensure every source/destination exists, distance > 0, speed > 0
    for edge in edges:
        src = edge.get("source")
        dst = edge.get("destination")
        dist = edge.get("distance_meters")
        speed = edge.get("speed_limit_kmh")

        if src not in camera_ids:
            print(f"FAIL: Source camera '{src}' not found in camera_nodes.json")
            sys.exit(1)
        if dst not in camera_ids:
            print(f"FAIL: Destination camera '{dst}' not found in camera_nodes.json")
            sys.exit(1)
            
        if not isinstance(dist, (int, float)) or dist <= 0:
            print(f"FAIL: Edge {src} -> {dst} has invalid distance_meters: {dist}")
            sys.exit(1)
            
        if not isinstance(speed, (int, float)) or speed <= 0:
            print(f"FAIL: Edge {src} -> {dst} has invalid speed_limit_kmh: {speed}")
            sys.exit(1)

    print("PASS: Referential integrity checked. All source/destination cameras exist.")
    print("PASS: Distance and speed limits are strictly positive for all edges.")

    print("\nAll Topology Validation Rules PASSED!")
    sys.exit(0)

if __name__ == "__main__":
    main()
