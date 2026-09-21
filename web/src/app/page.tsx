'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import VideoViewport from '../components/Video/VideoViewport';
import TargetDetails from '../components/Video/TargetDetails';
import EventPanel from '../components/Events/EventPanel';
import { useTelemetryStore } from '../stores/useTelemetryStore';
import FleetComposition from '../components/Analytics/FleetComposition';
import { useWebSocket } from '../hooks/useWebSocket';
import type { WebSocketStatus } from '../hooks/useWebSocket';
import { ThemeToggle } from '../components/ThemeToggle';
import TrafficFluxChart from '../components/Analytics/TrafficFluxChart';

const Map = dynamic(() => import('../components/Map'), { ssr: false, loading: () => (
  <div className="w-full h-full flex items-center justify-center bg-slate-100 dark:bg-zinc-950 text-cyan-telemetry font-mono text-xs animate-pulse tracking-widest">
    [ INITIATING TACTICAL MAP... ]
  </div>
) });

const STATUS_DISPLAY: Record<WebSocketStatus, { label: string; color: string; dotColor: string }> = {
  connected:    { label: 'LINK ACTIVE',    color: 'text-emerald-online border-emerald-online/30 bg-emerald-online/10', dotColor: 'bg-emerald-online' },
  connecting:   { label: 'CONNECTING',     color: 'text-amber-suspect border-amber-suspect/30 bg-amber-suspect/10',    dotColor: 'bg-amber-suspect' },
  disconnected: { label: 'LINK DOWN',      color: 'text-crimson-alert border-crimson-alert/30 bg-crimson-alert/10',    dotColor: 'bg-crimson-alert' },
};

export default function Home() {
  const setActiveCamera = useTelemetryStore((state) => state.setActiveCamera);
  const setTrackedPlate = useTelemetryStore((state) => state.setTrackedPlate);
  const clearState = useTelemetryStore((state) => state.clearState);
  const appMode = useTelemetryStore((state) => state.appMode);
  const setAppMode = useTelemetryStore((state) => state.setAppMode);

  // Sync initial mode with backend on mount
  useEffect(() => {
    fetch('http://127.0.0.1:5000/set_mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: appMode.toLowerCase() }),
    }).catch((err) => console.error('Failed to sync initial mode:', err));
  }, []);

  const [searchValue, setSearchValue] = useState('');

  // Connect to the Go broker's WebSocket hub for real-time telemetry
  const wsStatus = useWebSocket('ws://localhost:8080/ws');
  const statusInfo = STATUS_DISPLAY[wsStatus];

  const handleSearch = () => {
    const plate = searchValue.trim().toUpperCase();
    if (plate) {
      clearState();
      setTrackedPlate(plate);
      useTelemetryStore.getState().incrementTrackAttempt();
    }
  };

  const handleTrack = async () => {
    const plate = searchValue.trim().toUpperCase() || 'UNKNOWN';
    clearState();
    setTrackedPlate(plate);
    useTelemetryStore.getState().incrementTrackAttempt();
    
    try {
      await fetch(`http://127.0.0.1:5000/pause`, {
        method: 'POST',
      });
    } catch (err) {
      console.error('Failed to pause tracking:', err);
    }
  };

  const handleStop = async () => {
    try {
      // Clear local state
      useTelemetryStore.getState().setActiveTarget(null);
      useTelemetryStore.getState().setTrackedPlate(null);
      
      // Stop tracking on backend
      await fetch(`http://127.0.0.1:5000/reset`, {
        method: 'POST',
      });
    } catch (err) {
      console.error('Failed to stop tracking:', err);
    }
  };

  const handleDemoSimulation = async () => {
    const state = useTelemetryStore.getState();
    const activeTarget = state.activeTarget;
    
    // Inherit real details from the live AI tracking, or fallback if none active
    const simSystemId = activeTarget?.system_id || "TRK-999";
    const simOcr = activeTarget?.ocr_text || "UNKNOWN";
    const simClass = activeTarget?.vehicle_class || "SUV";
    const simColor = activeTarget?.locked_color || "SILVER";

    // Clean state so the map and telemetry panels are perfectly clean
    useTelemetryStore.setState({ telemetryLogs: [], alerts: [] });
    state.setActiveSystemId(simSystemId);
    
    // Switch to tactical
    setAppMode('TACTICAL');
    fetch('http://127.0.0.1:5000/set_mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'tactical' })
    }).catch(() => {});

    // Helper sleep
    const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

    const simulateTrack = (camId: string, speed: number) => {
      useTelemetryStore.getState().setActiveCamera(camId);
      
      const log = {
        camera_id: camId,
        timestamp: new Date().toISOString(),
        ocr_text: simOcr,
        vector: [],
        speed_kmh: speed,
        vehicle_class: simClass,
        locked_color: simColor,
        is_matched: true,
        system_id: simSystemId
      };
      
      // Inject into Zustand so Map polyline updates
      useTelemetryStore.getState().addTelemetryEvent(log);
      
      let videoPath = `../../web/public/videos/${camId.toLowerCase().replace('-', '')}.mp4`;
      
      // Dynamic mapping for AICity22 dataset
      if (camId.startsWith('CAM-0')) {
        const camNum = camId.split('-')[1]; // e.g. "024"
        videoPath = `../../web/public/videos/AICity22/S04/c${camNum}.avi`;
      }
      
      fetch('http://127.0.0.1:5000/switch_camera', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_path: videoPath, camera_id: camId })
      }).catch(() => {});
    };

    // The requested demo simulation path
    const demoCameras = ['CAM-024', 'CAM-023', 'CAM-022', 'CAM-025', 'CAM-026', 'CAM-027'];
    const demoSpeeds = [42.1, 38.4, 45.8, 41.2, 39.7, 43.5];

    for (let i = 0; i < demoCameras.length; i++) {
      simulateTrack(demoCameras[i], demoSpeeds[i]);
      
      // Wait for the video to play before handing off
      await sleep(5000);
      
      // Drop the target to trigger the visual handoff sequence
      if (i < demoCameras.length - 1) {
        useTelemetryStore.getState().addTelemetryEvent({
            camera_id: demoCameras[i], timestamp: new Date().toISOString(), ocr_text: simOcr, vector: [],
            speed_kmh: 0, vehicle_class: simClass, locked_color: simColor, is_matched: true, system_id: simSystemId
        });
      }
    }
  };

  return (
    <div className="h-screen w-full bg-slate-50 dark:bg-zinc-950 text-slate-800 dark:text-zinc-300 flex flex-col overflow-hidden transition-colors">
      {/* ── TOP NAV ────────────────────────────────────────────────── */}
      <header className="relative flex items-center justify-between px-6 py-4 bg-white dark:bg-zinc-900 border-b border-slate-200 dark:border-zinc-800 shrink-0 z-20 transition-colors">
        {/* Brand */}
        <div className="flex items-center shrink-0 gap-6">
          <span className="text-xl font-bold tracking-widest text-slate-900 dark:text-zinc-100 uppercase">
            CitiSentry
          </span>

          {/* ── MODE TOGGLE ── */}
          <div className="flex items-center bg-zinc-900 border border-zinc-700 rounded-md p-0.5">
            <button
              onClick={() => {
                setAppMode('TACTICAL');
                fetch('http://127.0.0.1:5000/set_mode', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ mode: 'tactical' }),
                }).catch(() => {});
              }}
              className={`px-4 py-1 text-xs font-bold tracking-widest rounded transition-all duration-200 ${
                appMode === 'TACTICAL'
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              TACTICAL
            </button>
            <button
              onClick={() => {
                setAppMode('STRATEGIC');
                fetch('http://127.0.0.1:5000/set_mode', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ mode: 'strategic' }),
                }).catch(() => {});
              }}
              className={`px-4 py-1 text-xs font-bold tracking-widest rounded transition-all duration-200 ${
                appMode === 'STRATEGIC'
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              STRATEGIC
            </button>
          </div>
        </div>

        {/* Center Search Bar */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-3 w-full max-w-[600px]">
          <div className="flex-1 flex items-center gap-3 bg-slate-100 dark:bg-zinc-950 border border-slate-300 dark:border-zinc-700 rounded-md px-4 py-2 transition-colors">
            <svg className="w-4 h-4 text-slate-500 dark:text-zinc-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search License Plate..."
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
              className="bg-transparent text-sm text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-600 outline-none w-full tracking-wider"
            />
          </div>
          <button
            onClick={handleTrack}
            className="px-5 py-2 text-xs font-bold tracking-widest bg-cyan-telemetry/10 border border-cyan-telemetry/40 text-cyan-600 dark:text-cyan-telemetry rounded-md hover:bg-cyan-telemetry/20 transition-colors uppercase"
          >
            TRACK
          </button>
          <button
            onClick={handleStop}
            className="px-5 py-2 text-xs font-bold tracking-widest bg-crimson-alert/10 border border-crimson-alert/40 text-red-600 dark:text-crimson-alert rounded-md hover:bg-crimson-alert/20 transition-colors uppercase"
          >
            STOP
          </button>
          <button
            onClick={handleDemoSimulation}
            className="px-5 py-2 text-xs font-bold tracking-widest bg-purple-600/20 border border-purple-500/50 text-purple-400 rounded-md hover:bg-purple-600/30 transition-colors uppercase shadow-[0_0_15px_rgba(168,85,247,0.4)]"
          >
            SIMULATE DEMO
          </button>
        </div>

        {/* Right Actions */}
        <div className="flex items-center shrink-0 gap-4">
          {/* WebSocket Status Indicator */}
          <div className={`flex items-center gap-2 px-3 py-1 rounded border text-[10px] font-bold tracking-widest ${statusInfo.color}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${statusInfo.dotColor} ${wsStatus === 'connected' ? 'animate-pulse' : ''}`} />
            {statusInfo.label}
          </div>
          <ThemeToggle />
        </div>
      </header>
      
      {/* ── MAIN GRID ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4 flex-1 p-4 min-h-0">

        {/* LEFT COLUMN */}
        <div className="flex flex-col gap-4 h-full min-h-0">
          {appMode === 'TACTICAL' ? (
            <>
              {/* Video – 65% */}
              <section className="flex-[65] min-h-0">
                <VideoViewport />
              </section>

              {/* Target Telemetry Grid – 35% */}
              <section className="flex-[35] min-h-0">
                <TargetDetails />
              </section>
            </>
          ) : (
            /* STRATEGIC MODE: 2x2 Grid Layout */
            <div className="flex flex-col gap-4 h-full min-h-0">
              {/* Map – 50% */}
              <section className="flex-1 min-h-0 bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden transition-colors">
                <Map />
              </section>
              
              {/* Video – 50% */}
              <section className="flex-1 min-h-0 bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden transition-colors">
                <VideoViewport />
              </section>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: Map/Events (Tactical) or Fleet/Events (Strategic) */}
        <div className="flex flex-col gap-4 h-full min-h-0">
          {appMode === 'TACTICAL' ? (
            <>
              {/* Map – 65% */}
              <section className="flex-[65] min-h-0 bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-lg overflow-hidden transition-colors">
                <Map />
              </section>

              {/* Tabbed Event Panel – 35% */}
              <section className="flex-[35] min-h-0">
                <EventPanel />
              </section>
            </>
          ) : (
            <>
              {/* Fleet Composition / KPIs – 50% */}
              <section className="flex-1 min-h-0 bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden transition-colors">
                <FleetComposition />
              </section>

              {/* Traffic Flux / Congestion – 50% */}
              <section className="flex-1 min-h-0 bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden transition-colors">
                <TrafficFluxChart />
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
