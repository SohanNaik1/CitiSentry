'use client';

import { useTelemetryStore } from '../../stores/useTelemetryStore';

function DataPill({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded p-2">
      <div className="text-[9px] font-mono text-zinc-600 uppercase tracking-widest mb-1">{label}</div>
      <div className={`font-mono text-sm font-semibold ${accent ?? 'text-zinc-200'}`}>{value}</div>
    </div>
  );
}

export default function TargetDetails() {
  const activeTarget = useTelemetryStore((state) => state.activeTarget);

  // Always render the full grid; populate with dashes if no target
  const plate = activeTarget?.license_plate.text ?? '—';
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
        ? 'text-emerald-online'
        : 'text-amber-suspect'
      : 'text-zinc-500';

  const reidAccent =
    activeTarget
      ? activeTarget.license_plate.is_clean
        ? 'text-emerald-online'
        : 'text-crimson-alert'
      : 'text-zinc-500';

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex flex-col gap-2">
      {/* Large plate display */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[9px] font-mono text-zinc-600 tracking-widest mb-0.5">LOCKED PLATE</div>
          <div
            className={`font-mono text-2xl font-bold tracking-widest ${activeTarget ? 'text-cyan-telemetry' : 'text-zinc-600'}`}
          >
            {plate}
          </div>
        </div>
        {activeTarget && (
          <div className="text-right">
            <div className="text-[9px] font-mono text-zinc-600 tracking-widest mb-0.5">CAMERA</div>
            <div className="font-mono text-xs text-zinc-300">{activeTarget.camera_id}</div>
          </div>
        )}
      </div>

      {/* 5-pill grid */}
      <div className="grid grid-cols-5 gap-2">
        <DataPill label="Confidence" value={conf} accent={confAccent} />
        <DataPill label="Class" value={vehicleClass} />
        <DataPill label="Color" value={color} />
        <DataPill label="Speed" value={speed} accent="text-amber-suspect" />
        <DataPill label="Re-ID Status" value={reid} accent={reidAccent} />
      </div>
    </div>
  );
}
