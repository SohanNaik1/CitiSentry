'use client';

import { useTelemetryStore } from '../../stores/useTelemetryStore';
import TelemetryCard from './TelemetryCard';

export default function TelemetryFeed() {
  const telemetryLogs = useTelemetryStore((state) => state.telemetryLogs);

  return (
    <section className="h-full border border-slate-800 shadow-[0_0_15px_rgba(0,0,0,0.5)] p-4 rounded-lg bg-tactical-panel flex flex-col">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-3 mb-4 shrink-0">
        <div className="w-2 h-2 rounded-full bg-cyan-telemetry animate-ping shadow-[0_0_8px_rgba(6,182,212,1)]"></div>
        <h2 className="text-lg text-cyan-telemetry uppercase tracking-widest font-bold">
          LIVE TELEMETRY STREAM
        </h2>
      </div>
      
      <div className="flex-1 overflow-y-auto pr-2">
        {telemetryLogs.length === 0 ? (
          <div className="h-full flex items-center justify-center border border-dashed border-slate-700 rounded bg-black/30">
            <span className="text-xs text-slate-600 animate-pulse font-mono tracking-widest">AWAITING EVENTS...</span>
          </div>
        ) : (
          telemetryLogs.map((log, index) => (
            <TelemetryCard key={`${log.event_id}-${index}`} event={log} />
          ))
        )}
      </div>
    </section>
  );
}
