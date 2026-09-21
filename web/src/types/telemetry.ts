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
  camera_id: string;
  timestamp: string;
  ocr_text: string;
  vector?: number[];
  speed_kmh: number;
  vehicle_class: string;
  system_id?: string;
  locked_class?: string;
  locked_color?: string;
  is_matched?: boolean;
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

export interface AnalyticsSnapshot {
  fleet_composition: Record<string, number>;
  node_avg_speeds: Record<string, number>;
  od_flow: Record<string, number>;
  total_tracked: number;
  all_time_total?: number;
}

