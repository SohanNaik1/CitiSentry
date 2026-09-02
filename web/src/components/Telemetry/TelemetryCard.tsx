import { TelemetryEvent } from '../../types/telemetry';

export default function TelemetryCard({ event }: { event: TelemetryEvent }) {
  const timestamp = new Date(event.timestamp).toLocaleTimeString();
  const conf = event.license_plate.confidence;
  const confColor = conf >= 0.85 ? 'text-emerald-online' : 'text-amber-suspect';

  return (
    <div className="border border-slate-700 bg-tactical-dark/50 p-3 rounded mb-3">
      <div className="flex justify-between items-start mb-2">
        <div className="flex flex-col gap-1">
          <div className="font-mono text-cyan-telemetry text-lg font-bold tracking-widest border border-cyan-telemetry/30 px-2 py-1 bg-cyan-telemetry/10 rounded w-fit">
            {event.license_plate.text}
          </div>
          {event.system_id && (
            <div className="text-[10px] text-slate-400 font-mono tracking-widest uppercase">
              ID: {event.system_id}
            </div>
          )}
        </div>
        <div className="text-xs text-slate-500 font-mono text-right">
          <div>{timestamp}</div>
          <div className="text-[10px] uppercase">{event.camera_id}</div>
        </div>
      </div>
      
      <div className="flex justify-between items-center text-xs font-mono">
        <div className="flex gap-2">
          <span className="bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">
            {event.vehicle_attributes.type}
          </span>
          <span className="bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">
            {event.vehicle_attributes.color}
          </span>
        </div>
        <div className={confColor}>
          CONF: {(conf * 100).toFixed(1)}%
        </div>
      </div>
    </div>
  );
}
