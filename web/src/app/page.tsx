'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import VideoViewport from '../components/Video/VideoViewport';
import TargetDetails from '../components/Video/TargetDetails';
import EventPanel from '../components/Events/EventPanel';
import { useTelemetryStore } from '../stores/useTelemetryStore';
import { useWebSocket } from '../hooks/useWebSocket';
import type { WebSocketStatus } from '../hooks/useWebSocket';
import { ThemeToggle } from '../components/ThemeToggle';

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
      await fetch(`http://localhost:5000/pause`, {
        method: 'POST',
      });
      
      const logs = useTelemetryStore.getState().telemetryLogs;
      const targetEvent = logs.find(l => l.license_plate.text === plate);
      
      if (targetEvent && targetEvent.bounding_box) {
        const brokerRes = await fetch('http://localhost:8080/api/v1/track/start', { method: 'POST' });
        const brokerData = await brokerRes.json();
        useTelemetryStore.getState().setActiveSystemId(brokerData.system_id);
        
        await fetch('http://localhost:5000/set_target', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ plate: plate, roi: targetEvent.bounding_box }),
        });
      }
    } catch (err) {
      console.error('Failed to start tracking:', err);
    }
  };

  const handleStop = async () => {
    try {
      // Just clear local state, tracking will be orphaned on the backend
      useTelemetryStore.getState().setActiveTarget(null);
      useTelemetryStore.getState().setTrackedPlate(null);
    } catch (err) {
      console.error('Failed to stop tracking:', err);
    }
  };

  return (
    <div className="h-screen w-full bg-slate-50 dark:bg-zinc-950 text-slate-800 dark:text-zinc-300 flex flex-col overflow-hidden transition-colors">
      {/* ── TOP NAV ────────────────────────────────────────────────── */}
      <header className="relative flex items-center justify-between px-6 py-4 bg-white dark:bg-zinc-900 border-b border-slate-200 dark:border-zinc-800 shrink-0 z-20 transition-colors">
        {/* Brand */}
        <div className="flex items-center shrink-0">
          <span className="text-xl font-bold tracking-widest text-slate-900 dark:text-zinc-100 uppercase">
            CitiSentry
          </span>
        </div>

        {/* Center Search Bar */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-3 w-full max-w-lg">
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
        </div>

        {/* Right Actions */}
        <div className="flex items-center shrink-0">
          <ThemeToggle />
        </div>
      </header>
      
      {/* ── MAIN GRID ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4 flex-1 p-4 min-h-0">

        {/* LEFT COLUMN: Video (65%) + Target (35%) */}
        <div className="flex flex-col gap-4 h-full min-h-0">
          {/* Video – 65% */}
          <section className="flex-[65] min-h-0">
            <VideoViewport />
          </section>

          {/* Target Telemetry Grid – 35% */}
          <section className="flex-[35] min-h-0">
            <TargetDetails />
          </section>
        </div>

        {/* RIGHT COLUMN: Map (65%) + Events (35%) */}
        <div className="flex flex-col gap-4 h-full min-h-0">
          {/* Map – 65% */}
          <section className="flex-[65] min-h-0 bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-lg overflow-hidden transition-colors">
            <Map />
          </section>

          {/* Tabbed Event Panel – 35% */}
          <section className="flex-[35] min-h-0">
            <EventPanel />
          </section>
        </div>
      </div>
    </div>
  );
}
