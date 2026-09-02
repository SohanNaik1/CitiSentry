export interface CameraNode {
  camera_id: string;
  name: string;
  lat: number;
  lng: number;
  status: "ONLINE" | "OFFLINE" | "DEGRADED";
  stream_url: string;
  fps: number;
}

export interface LicensePlate {
  text: string;
  confidence: number;
  is_clean: boolean;
}

export interface VehicleAttributes {
  type: "SEDAN" | "SUV" | "HATCHBACK" | "TRUCK" | "BUS" | "MOTORCYCLE" | "UNKNOWN" | "VEHICLE";
  color: "WHITE" | "BLACK" | "SILVER" | "GREY" | "RED" | "BLUE" | "OTHER" | "UNKNOWN";
  color_confidence: number;
}

export interface TelemetryEvent {
  event_id: string;
  system_id: string;
  camera_id: string;
  timestamp: string;
  epoch_ms: number;
  license_plate: LicensePlate;
  /** Bounding box in [xmin, ymin, xmax, ymax] format, normalized between 0.0 and 1.0 */
  bounding_box: [number, number, number, number];
  vehicle_attributes: VehicleAttributes;
  speed_kmh: number;
  heading_degrees: number;
  reid_embeddings: number[];
}

export interface AlertEvent {
  alert_id: string;
  alert_type: "HOTLIST_HIT" | "CLONED_PLATE_SPOOF" | "SPEED_VIOLATION" | "BLIND_SPOT_DEVIATION";
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "INFO";
  target_plate: string;
  source_camera_id: string;
  details: string;
  created_at: string;
}
