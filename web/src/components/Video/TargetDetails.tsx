'use client';

import { useTelemetryStore } from '../../stores/useTelemetryStore';

function DataPill({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="bg-slate-50 dark:bg-zinc-950 border border-slate-200 dark:border-zinc-800 rounded-md p-3 transition-colors">
      <div className="text-xs font-semibold text-slate-500 dark:text-zinc-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-base font-bold tracking-wide ${accent ?? 'text-slate-700 dark:text-zinc-200'}`}>{value}</div>
    </div>
  );
}

export default function TargetDetails() {
  const activeTarget = useTelemetryStore((state) => state.activeTarget);

  // Always render the full grid; populate with dashes if no target
  const plate = activeTarget?.license_plate.text ?? 'AWAITING TARGET';
  const conf = activeTarget ? `${(activeTarget.license_plate.confidence * 100).toFixed(1)}%` : '—';
  const vehicleClass = activeTarget?.vehicle_attributes.type ?? '—';
  const color = activeTarget?.vehicle_attributes.color ?? '—';
  const speed = activeTarget ? `${activeTarget.speed_kmh} km/h` : '—';
  const reid = activeTarget
    ? activeTarget.license_plate.is_clean
      ? 'VERIFIED'
      : 'MISMATCH'
    : '—';

  const confAccent =
    activeTarget
      ? activeTarget.license_plate.confidence >= 0.85
        ? 'text-emerald-600 dark:text-emerald-online'
        : 'text-amber-600 dark:text-amber-suspect'
      : 'text-slate-400 dark:text-zinc-500';

  const reidAccent =
    activeTarget
      ? activeTarget.license_plate.is_clean
        ? 'text-emerald-600 dark:text-emerald-online'
        : 'text-red-600 dark:text-crimson-alert'
      : 'text-slate-400 dark:text-zinc-500';

  return (
    <div className="h-full bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-lg p-5 flex flex-col gap-4 transition-colors">
      {/* Large plate display */}
      <div className="flex items-center justify-between mt-1">
        <div>
          <div className="text-xs font-semibold text-slate-500 dark:text-zinc-500 tracking-widest mb-1">LOCKED PLATE</div>
          <div
            className={`font-black tracking-widest ${activeTarget ? 'text-4xl text-cyan-700 dark:text-cyan-telemetry' : 'text-xl text-slate-300 dark:text-zinc-700'}`}
          >
            {plate}
          </div>
        </div>
        {activeTarget && (
          <div className="text-right">
            <div className="text-xs font-semibold text-slate-500 dark:text-zinc-500 tracking-widest mb-1">CAMERA</div>
            <div className="text-sm font-bold tracking-widest text-slate-700 dark:text-zinc-300">{activeTarget.camera_id}</div>
          </div>
        )}
      </div>

      {/* 5-pill grid */}
      <div className="grid grid-cols-5 gap-3 mt-auto mb-1">
        <DataPill label="Confidence" value={conf} accent={confAccent} />
        <DataPill label="Class" value={vehicleClass} />
        <DataPill label="Color" value={color} />
        <DataPill label="Speed" value={speed} accent="text-amber-600 dark:text-amber-suspect" />
        <DataPill label="Re-ID Status" value={reid} accent={reidAccent} />
      </div>
    </div>
  );
}
