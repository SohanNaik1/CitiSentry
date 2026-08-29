#!/usr/bin/env python3
"""
WebSocket Test Client for CitiSentry Core Broker.

Connects to the broker's WebSocket endpoint and prints every
telemetry event received in real-time. Used to verify the end-to-end
pipeline: Simulator -> HTTP POST -> Go Broker -> WS Broadcast -> This Client.

Usage:
    python3 ws_test_client.py [--url ws://localhost:8080/ws]
"""

import argparse
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("[ERROR] 'websockets' package is required. Install it with: pip install websockets")
    sys.exit(1)


async def listen(url: str) -> None:
    """Connect to the WebSocket endpoint and print incoming messages."""
    print(f"[WS-CLIENT] Connecting to {url}...")

    try:
        async with websockets.connect(url) as ws:
            print(f"[WS-CLIENT] Connected. Listening for telemetry events...\n")
            async for message in ws:
                try:
                    event = json.loads(message)
                    event_id = event.get("event_id", "UNKNOWN")
                    camera_id = event.get("camera_id", "UNKNOWN")
                    plate = event.get("license_plate", {}).get("text", "UNKNOWN")
                    speed = event.get("speed_kmh", 0)
                    confidence = event.get("license_plate", {}).get("confidence", 0)
                    print(
                        f"[RECEIVED] Event {event_id} | "
                        f"Camera {camera_id} | "
                        f"Plate {plate} | "
                        f"Speed {speed} km/h | "
                        f"Confidence {confidence:.2f}"
                    )
                except json.JSONDecodeError:
                    print(f"[RECEIVED] Raw: {message}")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"[WS-CLIENT] Connection closed: {e}")
    except ConnectionRefusedError:
        print(f"[WS-CLIENT] Connection refused. Is the broker running on {url}?")
    except Exception as e:
        print(f"[WS-CLIENT] Error: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CitiSentry WS Test Client")
    parser.add_argument(
        "--url",
        type=str,
        default="ws://localhost:8080/ws",
        help="WebSocket URL of the Go broker",
    )
    args = parser.parse_args()

    try:
        asyncio.run(listen(args.url))
    except KeyboardInterrupt:
        print("\n[WS-CLIENT] Disconnected.")


if __name__ == "__main__":
    main()
