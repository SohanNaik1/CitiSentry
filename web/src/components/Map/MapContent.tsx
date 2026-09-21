'use client';

import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Circle, CircleMarker, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import cameraNodes from '../../../../contracts/topology/camera_nodes.json';
import MarkerClusterGroup from 'react-leaflet-cluster';
import { useTelemetryStore } from '../../stores/useTelemetryStore';

// Create bounds that encapsulate all cameras
const globalBounds = L.latLngBounds(cameraNodes.map(node => [node.lat, node.lng] as [number, number]));

function MapBounds() {
  const map = useMap();
  const appMode = useTelemetryStore((state) => state.appMode);
  
  useEffect(() => {
    map.fitBounds(globalBounds, { padding: [50, 50] });
  }, [map, appMode]);

  return null;
}

function StrategicHeatmapNode({ node, speed, count, color }: any) {
  const map = useMap();
  const [zoom, setZoom] = React.useState(map.getZoom());

  useEffect(() => {
    const onZoom = () => setZoom(map.getZoom());
    map.on('zoom', onZoom);
    return () => { map.off('zoom', onZoom); };
  }, [map]);

  // Hide the gradient when zoomed out to globe/continent level
  if (zoom < 11) return null; 

  // Dynamically scale pixel radius based on map zoom so it mimics geographic scaling
  const baseRadius = 20 + (count * 3);
  const scale = Math.pow(2, zoom - 17);
  // Cap the radius at 100px so it doesn't swallow the whole screen at high zooms
  const radius = Math.min(Math.max(10, baseRadius * scale), 100);

  const glowIcon = L.divIcon({
    className: '',
    html: `<div style="width: 0px; height: 0px; box-shadow: 0 0 ${radius}px ${radius}px ${color}; border-radius: 50%; opacity: 0.5;"></div>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0]
  });

  return (
    <Marker
      position={[node.lat, node.lng]}
      icon={glowIcon}
    />
  );
}

export default function MapContent() {
  const activeCameraId = useTelemetryStore((state) => state.activeCameraId);
  const analyticsData = useTelemetryStore((state) => state.analyticsData);
  const activeSystemId = useTelemetryStore((state) => state.activeSystemId);
  const telemetryLogs = useTelemetryStore((state) => state.telemetryLogs);

  // Center on average coords
  const avgLat = cameraNodes.reduce((sum, node) => sum + node.lat, 0) / cameraNodes.length || 12.97;
  const avgLng = cameraNodes.reduce((sum, node) => sum + node.lng, 0) / cameraNodes.length || 77.59;

  const setActiveCamera = useTelemetryStore((state) => state.setActiveCamera);

  // Build trajectory polyline from telemetry logs for the active tracked target
  const cameraLookup = Object.fromEntries(cameraNodes.map(n => [n.camera_id, [n.lat, n.lng] as [number, number]]));
  const trajectoryCoords: [number, number][] = [];
  const visitedCameras: string[] = [];
  
  if (activeSystemId) {
    const matchingLogs = telemetryLogs
      .filter(log => log.system_id === activeSystemId && log.camera_id)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    
    // Extract unique camera sequence (deduplicate consecutive duplicates)
    for (const log of matchingLogs) {
      if (visitedCameras[visitedCameras.length - 1] !== log.camera_id) {
        visitedCameras.push(log.camera_id);
      }
    }
    
    for (const camId of visitedCameras) {
      const coord = cameraLookup[camId];
      if (coord) trajectoryCoords.push(coord);
    }
  }

  const [routedPolyline, setRoutedPolyline] = useState<[number, number][]>([]);

  // Effect to fetch OSRM routing when the visited camera path changes
  useEffect(() => {
    if (trajectoryCoords.length < 2) {
      setRoutedPolyline([]);
      return;
    }
    
    const fetchRoute = async () => {
      try {
        // OSRM uses [lng, lat] format
        const coordString = trajectoryCoords.map(c => `${c[1]},${c[0]}`).join(';');
        const res = await fetch(`https://router.project-osrm.org/route/v1/driving/${coordString}?overview=full&geometries=geojson`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.routes && data.routes[0]) {
          const coords = data.routes[0].geometry.coordinates;
          // Convert [lng, lat] back to Leaflet's [lat, lng]
          setRoutedPolyline(coords.map((c: any) => [c[1], c[0]] as [number, number]));
        }
      } catch (e) {
        console.error("OSRM Routing failed", e);
      }
    };
    fetchRoute();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visitedCameras.join(',')]);

  // Use the routed polyline if available, otherwise fallback to straight pin-to-pin lines
  const displayPolyline = routedPolyline.length > 0 ? routedPolyline : trajectoryCoords;

  // Function to create a sleek custom map pin icon
  const createIcon = (isActive: boolean, speed?: number) => {
    let pinColor = 'bg-blue-600';
    let ringColor = 'ring-blue-500/50';

    if (speed !== undefined) {
      if (speed < 15) {
        pinColor = 'bg-red-600';
        ringColor = 'ring-red-500/80 animate-pulse'; // Severe Traffic (Pulse)
      } else if (speed < 30) {
        pinColor = 'bg-amber-500';
        ringColor = 'ring-amber-500/50'; // Moderate Traffic
      } else {
        pinColor = 'bg-emerald-500';
        ringColor = 'ring-emerald-500/50'; // Clear Traffic
      }
    }

    const ringClass = isActive 
      ? `ring-4 ${ringColor}`
      : 'ring-2 ring-white/50 border border-black/10';

    return L.divIcon({
      className: 'bg-transparent',
      html: `<div class="relative flex items-center justify-center w-6 h-6 ${pinColor} rounded-t-full rounded-bl-full rotate-45 shadow-lg border-2 border-white ${ringClass} ${isActive ? 'glow-pin-active' : ''}">
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

  const appMode = useTelemetryStore((state) => state.appMode);

  return (
    <MapContainer 
      bounds={globalBounds}
      className="w-full h-full bg-tactical-dark z-0"
      zoomControl={false}
    >
      <TileLayer
        url={`https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=cb1_2hnp_1_939456ea1a6f1ca94af2c299`}
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        maxZoom={19}
      />
      <MapBounds />
      
      {appMode === 'TACTICAL' ? (
        <MarkerClusterGroup 
          chunkedLoading 
          iconCreateFunction={createClusterCustomIcon}
        >
          {cameraNodes.map((node) => {
            const speed = analyticsData?.node_avg_speeds?.[node.camera_id];
            return (
              <Marker 
                key={node.camera_id} 
                position={[node.lat, node.lng]} 
                icon={createIcon(activeCameraId === node.camera_id, speed)}
                eventHandlers={{ click: () => handleCameraClick(node) }}
              >
                <Popup className="tactical-popup">
                  <div className="font-mono text-tactical-dark text-xs p-1">
                    <strong>{node.camera_id}</strong>
                    <br />
                    {node.name}
                    {speed !== undefined && (
                      <>
                        <br />
                        <strong>Speed: {speed.toFixed(1)} km/h</strong>
                      </>
                    )}
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MarkerClusterGroup>
      ) : (
        <>
          {/* STRATEGIC MODE THERMAL HEATMAP (Circles render underneath) */}
          {cameraNodes.map((node) => {
            const speed = analyticsData?.node_avg_speeds?.[node.camera_id];
            const count = Math.round((analyticsData?.fleet_composition ? Object.values(analyticsData.fleet_composition).reduce((a, b) => a + b, 0) : 0) / 30);
          
            let color = '#10b981'; // Emerald
            if (speed !== undefined) {
              if (speed < 15) color = '#ef4444'; // Red
              else if (speed < 30) color = '#f59e0b'; // Amber
            }

            return <StrategicHeatmapNode key={`glow-${node.camera_id}`} node={node} speed={speed} count={count} color={color} />;
          })}

          {/* CLUSTERED MAP PINS (Exactly like Tactical) */}
          <MarkerClusterGroup 
            chunkedLoading 
            iconCreateFunction={createClusterCustomIcon}
          >
            {cameraNodes.map((node) => {
              const speed = analyticsData?.node_avg_speeds?.[node.camera_id];
              return (
                <Marker 
                  key={`marker-${node.camera_id}`}
                  position={[node.lat, node.lng]} 
                  icon={createIcon(activeCameraId === node.camera_id, speed)}
                  eventHandlers={{ click: () => handleCameraClick(node) }}
                />
              );
            })}
          </MarkerClusterGroup>
        </>
      )}

      {/* Trajectory Polyline for tracked vehicle handoff path */}
      {displayPolyline.length >= 2 && (
        <Polyline 
          positions={displayPolyline} 
          pathOptions={{ color: '#0ea5e9', weight: 4, dashArray: '10, 15', opacity: 0.8, className: 'animated-polyline' }} 
        />
      )}
    </MapContainer>
  );
}
