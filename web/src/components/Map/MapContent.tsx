'use client';

import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import cameraNodes from '../../../../contracts/topology/camera_nodes.json';
import MarkerClusterGroup from 'react-leaflet-cluster';
import { useTelemetryStore } from '../../stores/useTelemetryStore';

export default function MapContent() {
  const activeCameraId = useTelemetryStore((state) => state.activeCameraId);
  const activeSystemId = useTelemetryStore((state) => state.activeSystemId);
  const telemetryLogs = useTelemetryStore((state) => state.telemetryLogs);

  // Center on average coords
  const avgLat = cameraNodes.reduce((sum, node) => sum + node.lat, 0) / cameraNodes.length || 12.97;
  const avgLng = cameraNodes.reduce((sum, node) => sum + node.lng, 0) / cameraNodes.length || 77.59;

  const setActiveCamera = useTelemetryStore((state) => state.setActiveCamera);

  const activeTrajectory = useTelemetryStore((state) => state.activeTrajectory);

  // Map to coordinates for the Polyline
  const pathCoords = activeTrajectory
    .map((camId) => {
      const node = cameraNodes.find((n) => n.camera_id === camId);
      return node ? ([node.lat, node.lng] as [number, number]) : null;
    })
    .filter(Boolean) as [number, number][];

  // Identify the most recent camera where the suspect was seen
  const lastVisitedCameraId = activeTrajectory.length > 0 ? activeTrajectory[activeTrajectory.length - 1] : null;

  // 2. The Green Pin (100% Certainty)
  // Function to create a sleek custom map pin icon
  const createIcon = (camId: string, isActive: boolean) => {
    const isTargetLocation = camId === lastVisitedCameraId;
    
    const bgColor = isTargetLocation ? 'bg-emerald-500' : 'bg-blue-600';
    const ringClass = isTargetLocation 
      ? 'ring-4 ring-emerald-500/50 border-emerald-300'
      : (isActive ? 'ring-4 ring-blue-500/50 border-white' : 'ring-2 ring-white/50 border border-black/10');

    return L.divIcon({
      className: 'bg-transparent',
      html: `<div class="relative flex items-center justify-center w-6 h-6 ${bgColor} rounded-t-full rounded-bl-full rotate-45 shadow-lg border-2 ${ringClass}">
               <div class="w-2 h-2 bg-white rounded-full -rotate-45"></div>
             </div>`,
      iconSize: [24, 24],
      iconAnchor: [12, 24], // Bottom tip of the pin points to coordinate
    });
  };

  const createClusterCustomIcon = (cluster: any) => {
    const count = cluster.getChildCount();
    return L.divIcon({
      html: `<div class="bg-blue-600 text-white rounded-full flex items-center justify-center border-2 border-white shadow-md w-10 h-10 font-bold">${count}</div>`,
      className: 'bg-transparent',
      iconSize: L.point(40, 40, true),
    });
  };

  const handleCameraClick = async (node: any) => {
    setActiveCamera(node.camera_id);
    
    // Construct local path: e.g. CAM-002 -> cam002.mp4
    let videoPath;
    if (node.video_file) {
      videoPath = `../../web/public/videos/${node.video_file}`;
    } else {
      const videoFileName = node.camera_id.toLowerCase().replace('-', '') + '.mp4';
      videoPath = `../../web/public/videos/${videoFileName}`;
    }

    try {
      await fetch('http://127.0.0.1:5000/switch_camera', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_path: videoPath,
          camera_id: node.camera_id
        })
      });
    } catch (e) {
      console.error('Failed to switch camera:', e);
    }
  };

  // Create bounds that encapsulate all cameras
  const bounds = L.latLngBounds(cameraNodes.map(node => [node.lat, node.lng] as [number, number]));

  return (
    <MapContainer 
      bounds={bounds}
      className="w-full h-full bg-tactical-dark z-0"
      zoomControl={false}
    >
      <TileLayer
        url={`https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=cb1_2hnp_1_939456ea1a6f1ca94af2c299`}
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        maxZoom={19}
      />
      
      <MarkerClusterGroup 
        chunkedLoading 
        iconCreateFunction={createClusterCustomIcon}
      >
        {cameraNodes.map((node) => (
          <Marker 
            key={node.camera_id} 
            position={[node.lat, node.lng]} 
            icon={createIcon(node.camera_id, activeCameraId === node.camera_id)}
            eventHandlers={{ click: () => handleCameraClick(node) }}
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
      </MarkerClusterGroup>

      {/* Polyline for trajectories (Outside MarkerClusterGroup) */}
      {pathCoords.length > 1 && (
        <Polyline 
          positions={pathCoords} 
          pathOptions={{ color: '#10b981', weight: 4, dashArray: '10, 10', opacity: 0.8 }} 
        />
      )}
    </MapContainer>
  );
}
