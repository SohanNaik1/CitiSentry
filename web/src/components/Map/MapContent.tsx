'use client';

import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import cameraNodes from '../../../../contracts/topology/camera_nodes.json';
import { useTelemetryStore } from '../../stores/useTelemetryStore';

export default function MapContent() {
  const activeCameraId = useTelemetryStore((state) => state.activeCameraId);

  // Center on average coords
  const avgLat = cameraNodes.reduce((sum, node) => sum + node.lat, 0) / cameraNodes.length || 12.97;
  const avgLng = cameraNodes.reduce((sum, node) => sum + node.lng, 0) / cameraNodes.length || 77.59;

  // Function to create a custom tactical icon
  const createIcon = (isActive: boolean) => {
    const pulseClass = isActive 
      ? 'shadow-[0_0_15px_rgba(6,182,212,1)] bg-cyan-telemetry animate-pulse'
      : 'bg-emerald-online shadow-[0_0_10px_rgba(16,185,129,0.5)]';

    return L.divIcon({
      className: 'bg-transparent',
      html: `<div class="w-4 h-4 rounded-full border-2 border-tactical-dark ${pulseClass}"></div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    });
  };

  return (
    <MapContainer 
      center={[avgLat, avgLng]} 
      zoom={13} 
      className="w-full h-full bg-tactical-dark z-0"
      zoomControl={false}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=cb1_2hnp_1_939456ea1a6f1ca94af2c299"
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        maxZoom={19}
      />
      
      {cameraNodes.map((node) => (
        <Marker 
          key={node.camera_id} 
          position={[node.lat, node.lng]} 
          icon={createIcon(activeCameraId === node.camera_id)}
        >
          <Popup className="tactical-popup">
            <div className="font-mono text-tactical-dark text-xs p-1">
              <strong>{node.camera_id}</strong>
              <br />
              {node.name}
            </div>
          </Popup>
        </Marker>
      ))}

      {/* Polyline for trajectories (Preparation) */}
      <Polyline positions={[]} pathOptions={{ color: '#06b6d4', weight: 3 }} />
    </MapContainer>
  );
}
