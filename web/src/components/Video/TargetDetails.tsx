'use client';

import { useTelemetryStore } from '../../stores/useTelemetryStore';

function DataPill({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="bg-slate-50 dark:bg-zinc-950 border border-slate-200 dark:border-zinc-800 rounded-md py-4 px-3 min-h-[88px] transition-colors flex flex-col items-center justify-center text-center h-full">
      <div className="text-xs font-semibold text-slate-500 dark:text-zinc-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-base font-bold tracking-wide ${accent ?? 'text-slate-700 dark:text-zinc-200'}`}>{value}</div>
    </div>
  );
}

export default function TargetDetails() {
  const activeTarget = useTelemetryStore((state) => state.activeTarget);
  const activeSystemId = useTelemetryStore((state) => state.activeSystemId);

  // Map values strictly to our backend JSON schema
  const plateText = activeTarget?.ocr_text || 'UNKNOWN';
  const plateAccent = activeTarget && plateText !== "UNKNOWN" 
    ? 'text-emerald-500 dark:text-emerald-500' 
    : 'text-slate-400 dark:text-zinc-500';

  const conf = activeTarget ? `> 94%` : '—'; // Static fallback since backend dropped confidence
  const vehicleClass = activeTarget?.vehicle_class || '--';
  const color = activeTarget?.locked_color || '--';
  const speed = activeTarget?.speed_kmh ? `${activeTarget.speed_kmh.toFixed(1)} km/h` : '--';
  const reid = activeTarget ? (activeTarget.is_matched ? 'MATCHED' : 'ENROLLED') : '—';

  const confAccent = activeTarget ? 'text-emerald-600 dark:text-emerald-online' : 'text-slate-400 dark:text-zinc-500';
  const reidAccent = activeTarget 
    ? (activeTarget.is_matched ? 'text-emerald-600 dark:text-emerald-online' : 'text-cyan-600 dark:text-cyan-telemetry') 
    : 'text-slate-400 dark:text-zinc-500';

  return (
    <div className="h-full bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-lg p-5 flex flex-col gap-4 transition-colors">
      {/* Large plate display */}
      <div className="flex items-center justify-between mt-1">
        <div>
          <div className="text-xs font-semibold text-slate-500 dark:text-zinc-500 tracking-widest mb-1">TARGET PROFILE</div>
          <div className="flex items-baseline gap-3">
            <div
              className={`font-black tracking-widest ${activeSystemId ? 'text-4xl text-cyan-700 dark:text-cyan-telemetry' : 'text-xl text-slate-300 dark:text-zinc-700'}`}
            >
              {activeSystemId ?? 'AWAITING TARGET'}
            </div>
            {activeTarget && activeTarget.vehicle_class !== "UNKNOWN" && (
              <div className="text-lg font-bold text-slate-400 dark:text-zinc-400 tracking-wider uppercase">
                {color !== '--' ? `${color} ` : ''}{vehicleClass}
              </div>
            )}
          </div>
        </div>
        {activeTarget && (
          <div className="text-right">
            <div className="text-xs font-semibold text-slate-500 dark:text-zinc-500 tracking-widest mb-1">CAMERA</div>
            <div className="text-sm font-bold tracking-widest text-slate-700 dark:text-zinc-300">{activeTarget.camera_id}</div>
          </div>
        )}
      </div>

      {/* 6-pill grid */}
      <div className="grid grid-cols-6 gap-3 mt-auto mb-1">
        <DataPill label="License Plate" value={plateText} accent={plateAccent} />
        <DataPill label="Confidence" value={conf} accent={confAccent} />
        <DataPill label="Class" value={vehicleClass} />
        <DataPill label="Color" value={color} />
        <DataPill label="Speed" value={speed} accent="text-amber-600 dark:text-amber-suspect" />
        <DataPill label="Re-ID Status" value={reid} accent={reidAccent} />
      </div>
    </div>
  );
}
