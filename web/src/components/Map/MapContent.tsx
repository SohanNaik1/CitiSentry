'use client';

import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import cameraNodes from '../../../../contracts/topology/camera_nodes.json';
import MarkerClusterGroup from 'react-leaflet-cluster';
import { useTelemetryStore } from '../../stores/useTelemetryStore';

export default function MapContent() {
  const activeCameraId = useTelemetryStore((state) => state.activeCameraId);

  // Center on average coords
  const avgLat = cameraNodes.reduce((sum, node) => sum + node.lat, 0) / cameraNodes.length || 12.97;
  const avgLng = cameraNodes.reduce((sum, node) => sum + node.lng, 0) / cameraNodes.length || 77.59;

  const setActiveCamera = useTelemetryStore((state) => state.setActiveCamera);

  // Function to create a sleek custom blue map pin icon (teardrop)
  const createIcon = (isActive: boolean) => {
    const ringClass = isActive 
      ? 'ring-4 ring-blue-500/50'
      : 'ring-2 ring-white/50 border border-black/10';

    return L.divIcon({
      className: 'bg-transparent',
      html: `<div class="relative flex items-center justify-center w-6 h-6 bg-blue-600 rounded-t-full rounded-bl-full rotate-45 shadow-lg border-2 border-white ${ringClass}">
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
    const videoFileName = node.camera_id.toLowerCase().replace('-', '') + '.mp4';
    const videoPath = `../../web/public/videos/${videoFileName}`;

    try {
      await fetch('http://localhost:5000/switch_camera', {
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

  return (
    <MapContainer 
      center={[avgLat, avgLng]} 
      zoom={13} 
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
            icon={createIcon(activeCameraId === node.camera_id)}
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

      {/* Polyline for trajectories (Preparation) */}
      <Polyline positions={[]} pathOptions={{ color: '#06b6d4', weight: 3 }} />
    </MapContainer>
  );
}
