'use client';

import dynamic from 'next/dynamic';
import VideoViewport from '../components/Video/VideoViewport';
import TargetDetails from '../components/Video/TargetDetails';
import EventPanel from '../components/Events/EventPanel';
import { useTelemetryStore } from '../stores/useTelemetryStore';

const Map = dynamic(() => import('../components/Map'), { ssr: false, loading: () => (
  <div className="w-full h-full flex items-center justify-center bg-zinc-950 text-cyan-telemetry font-mono text-xs animate-pulse tracking-widest">
    [ INITIATING TACTICAL MAP... ]
  </div>
) });

const SCENARIOS = [
  { label: 'Pursuit #1', id: 1 },
  { label: 'Ambiguity #2', id: 2 },
  { label: 'Cloned #3', id: 3 },
];

export default function Home() {
  const setActiveCamera = useTelemetryStore((state) => state.setActiveCamera);

  // Scenario switcher pre-wires cameras for demo – broker integration in next task
  const handleScenario = (id: number) => {
    setActiveCamera(`CAM-00${id}`);
  };

  return (
    <div className="h-screen w-full bg-zinc-950 font-mono text-zinc-400 flex flex-col overflow-hidden">
      {/* ── TOP NAV ────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between gap-4 px-4 py-2 bg-zinc-900 border-b border-zinc-800 shrink-0 z-20">
        {/* Brand */}
        <div className="flex items-center gap-2.5 shrink-0">
          <span className="w-2 h-2 rounded-full bg-emerald-online shadow-[0_0_8px_#10b981] animate-pulse"></span>
          <span className="text-sm text-zinc-100 font-bold tracking-widest uppercase">
            CitiSentry
          </span>
          <span className="text-zinc-700 text-sm">//</span>
          <span className="text-[11px] text-zinc-500 tracking-widest uppercase">ANPR Tactical Engine</span>
          <span className="ml-1 px-2 py-0.5 text-[9px] font-bold tracking-widest bg-emerald-online/10 text-emerald-online border border-emerald-online/30 rounded-full uppercase">
            SYSTEM ARMED
          </span>
        </div>

        {/* Search */}
        <div className="flex items-center gap-2 flex-1 max-w-sm">
          <div className="flex-1 flex items-center gap-2 bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5">
            <svg className="w-3 h-3 text-zinc-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search License Plate..."
              className="bg-transparent text-xs text-zinc-300 placeholder-zinc-600 outline-none w-full tracking-widest"
            />
          </div>
          <button className="px-3 py-1.5 text-[10px] font-bold tracking-widest bg-cyan-telemetry/10 border border-cyan-telemetry/40 text-cyan-telemetry rounded hover:bg-cyan-telemetry/20 transition-colors uppercase">
            TRACK
          </button>
        </div>

        {/* Scenario Switcher */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[9px] text-zinc-600 uppercase tracking-widest mr-1">Scenario:</span>
          {SCENARIOS.map((s) => (
            <button
              key={s.id}
              onClick={() => handleScenario(s.id)}
              className="px-2.5 py-1 text-[10px] font-bold tracking-widest border border-zinc-700 text-zinc-400 rounded hover:border-cyan-telemetry/50 hover:text-cyan-telemetry transition-colors uppercase"
            >
              {s.label}
            </button>
          ))}
        </div>
      </header>

      {/* ── MAIN GRID ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 flex-1 p-3 min-h-0">

        {/* LEFT COLUMN: Video (65%) + Target (35%) */}
        <div className="flex flex-col gap-3 h-full min-h-0">
          {/* Video – 65% */}
          <section className="flex-[65] min-h-0">
            <VideoViewport />
          </section>

          {/* Target Telemetry Grid – 35% */}
          <section className="flex-[35] min-h-0">
            <TargetDetails />
          </section>
        </div>

        {/* RIGHT COLUMN: Map (55%) + Events (45%) */}
        <div className="flex flex-col gap-3 h-full min-h-0">
          {/* Map – 55% */}
          <section className="flex-[55] min-h-0 bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
            <Map />
          </section>

          {/* Tabbed Event Panel – 45% */}
          <section className="flex-[45] min-h-0">
            <EventPanel />
          </section>
        </div>
      </div>
    </div>
  );
}
