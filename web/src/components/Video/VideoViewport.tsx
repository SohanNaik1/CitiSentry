'use client';

import { useEffect, useRef, useState, MouseEvent } from 'react';
import { useTelemetryStore } from '../../stores/useTelemetryStore';
import DVRControls from './DVRControls';

export default function VideoViewport() {
  const trackedPlate = useTelemetryStore((state) => state.trackedPlate);
  const trackAttempt = useTelemetryStore((state) => state.trackAttempt);
  const [currentTime, setCurrentTime] = useState('');
  const [videoRetry, setVideoRetry] = useState(0);

  // Update clock every second
  useEffect(() => {
    const tick = () => setCurrentTime(new Date().toLocaleTimeString('en-GB'));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  
  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState({ x: 0, y: 0 });
  const [currentPos, setCurrentPos] = useState({ x: 0, y: 0 });
  const [isSelectingMode, setIsSelectingMode] = useState(false);

  useEffect(() => {
    // Also reset video to beginning on mount
    fetch('http://127.0.0.1:5000/reset', { method: 'POST' }).catch(() => {});
  }, []);

  useEffect(() => {
    setIsDrawing(false);
  }, [trackedPlate, trackAttempt]);

  const handleMouseDown = (e: MouseEvent) => {
    if (!isSelectingMode) return;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setStartPos({ x, y });
    setCurrentPos({ x, y });
    setIsDrawing(true);
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDrawing || !isSelectingMode) return;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setCurrentPos({ x, y });
  };

  const handleMouseUp = async () => {
    if (!isDrawing || !isSelectingMode) return;
    setIsDrawing(false);
    setIsSelectingMode(false);

    if (!imgRef.current || !containerRef.current) return;

    // To accurately map the coordinates over object-contain image:
    const img = imgRef.current;
    const rect = containerRef.current.getBoundingClientRect();
    
    // Fallback if naturalWidth isn't available right away
    const intrinsicW = img.naturalWidth || 1280;
    const intrinsicH = img.naturalHeight || 720;
    
    // Calculate the scale and rendered dimensions
    const scale = Math.min(rect.width / intrinsicW, rect.height / intrinsicH);
    const renderedW = intrinsicW * scale;
    const renderedH = intrinsicH * scale;

    // Calculate offsets (the letterbox/pillarbox empty spaces)
    const offsetX = (rect.width - renderedW) / 2;
    const offsetY = (rect.height - renderedH) / 2;

    const xminRaw = Math.min(startPos.x, currentPos.x) - offsetX;
    const yminRaw = Math.min(startPos.y, currentPos.y) - offsetY;
    const xmaxRaw = Math.max(startPos.x, currentPos.x) - offsetX;
    const ymaxRaw = Math.max(startPos.y, currentPos.y) - offsetY;

    // Normalize against the *rendered* image dimensions
    const xmin = Math.max(0, Math.min(1, xminRaw / renderedW));
    const ymin = Math.max(0, Math.min(1, yminRaw / renderedH));
    const xmax = Math.max(0, Math.min(1, xmaxRaw / renderedW));
    const ymax = Math.max(0, Math.min(1, ymaxRaw / renderedH));

    try {
      // 1. Get system ID from Go Broker
      const brokerRes = await fetch('http://localhost:8080/api/v1/track/start', {
        method: 'POST',
      });
      const brokerData = await brokerRes.json();
      
      // 2. Save activeSystemId to store
      useTelemetryStore.getState().setActiveSystemId(brokerData.system_id);

      // 3. Start tracking on vision node
      await fetch('http://127.0.0.1:5000/set_target', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate: trackedPlate || "UNKNOWN", roi: [xmin, ymin, xmax, ymax] }),
      });
    } catch (err) {
      console.error('Failed to set target on vision node:', err);
    }
  };

  return (
    <div className="relative w-full h-full bg-black rounded overflow-hidden border border-zinc-800">
      {/* Top Bar HUD */}
      <div className="absolute top-0 left-0 w-full p-2 flex items-center justify-between z-10 bg-black/60 pointer-events-none">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold tracking-widest text-emerald-online uppercase">
            [ VIDEO FEED ]
          </span>
          <button 
            onClick={() => setIsSelectingMode(!isSelectingMode)}
            className={`pointer-events-auto px-2 py-1 ml-2 text-[10px] font-bold tracking-widest rounded ${isSelectingMode ? 'bg-amber-suspect/20 text-amber-suspect border-amber-suspect' : 'bg-slate-800 text-slate-400 border-slate-700'} border uppercase`}
          >
            {isSelectingMode ? 'CANCEL DRAW' : 'DRAW ROI'}
          </button>
          <button 
            onClick={() => fetch('http://localhost:5000/reset_sync', { method: 'POST' }).catch(() => {})}
            className="pointer-events-auto px-2 py-1 ml-2 text-[10px] font-bold tracking-widest rounded bg-slate-800 text-slate-400 border-slate-700 border uppercase hover:bg-slate-700"
          >
            RESET LOOP
          </button>
        </div>

      {/* The MJPEG Stream with Robust Auto-Reconnect */}
      <img
        ref={imgRef}
        src={`http://localhost:5000/video_feed?t=${videoRetry}`}
        className="w-full h-full object-contain pointer-events-none"
        alt="Camera Feed"
        draggable={false}
        onError={() => {
          // If the feed fails (backend booting or model downloading), wait 2s and try again
          setTimeout(() => setVideoRetry(prev => prev + 1), 2000);
        }}
      />

        {/* Overlay for ROI Dragging */}
        <div
          ref={containerRef}
          className={`absolute inset-0 z-20 ${isSelectingMode ? 'cursor-crosshair' : 'pointer-events-none'}`}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
        >
          {isDrawing && (
            <div
              className="absolute border border-cyan-telemetry bg-cyan-telemetry/10"
              style={{
                left: Math.min(startPos.x, currentPos.x),
                top: Math.min(startPos.y, currentPos.y),
                width: Math.abs(currentPos.x - startPos.x),
                height: Math.abs(currentPos.y - startPos.y),
              }}
            />
          )}
        </div>

        {isSelectingMode && !isDrawing && (
          <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-cyan-telemetry text-[10px] font-bold bg-black/80 px-4 py-2 border border-cyan-telemetry/30 rounded pointer-events-none uppercase tracking-widest z-30 animate-pulse">
            DRAW ROI OVER TARGET
          </div>
        )}
      </div>

      {/* ── DVR Tactical Scrubber ─────────────────────────────── */}
      <DVRControls />
    </div>
  );
}
