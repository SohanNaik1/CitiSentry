'use client';

import { useTelemetryStore } from '../../stores/useTelemetryStore';

export default function AlertPanel() {
  const alerts = useTelemetryStore((state) => state.alerts);

  const getSeverityStyle = (severity: string) => {
    switch (severity) {
      case 'CRITICAL':
      case 'HIGH':
        return 'border-crimson-alert bg-crimson-alert/10 text-crimson-alert';
      case 'MEDIUM':
        return 'border-amber-suspect bg-amber-suspect/10 text-amber-suspect';
      default:
        return 'border-slate-500 bg-slate-800 text-slate-300';
    }
  };

  return (
    <section className="h-full border border-slate-800 p-4 rounded-lg bg-tactical-panel flex flex-col">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-3 mb-4 shrink-0">
        <div className="w-2 h-2 rounded-full bg-crimson-alert"></div>
        <h2 className="text-lg text-crimson-alert uppercase tracking-widest font-bold">
          SYSTEM ALERTS
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto pr-2">
        {alerts.length === 0 ? (
          <div className="h-full flex items-center justify-center border border-dashed border-slate-700 rounded bg-black/30">
            <span className="text-xs text-slate-600 animate-pulse font-mono tracking-widest">NO ACTIVE ALERTS</span>
          </div>
        ) : (
          alerts.map((alert, index) => (
            <div 
              key={`${alert.alert_id}-${index}`}
              className={`border p-3 rounded mb-3 font-mono text-xs ${getSeverityStyle(alert.severity)}`}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="font-bold">{alert.alert_type}</span>
                <span className="text-[10px]">{new Date(alert.created_at).toLocaleTimeString()}</span>
              </div>
              <div className="text-slate-300">
                Plate: <span className="font-bold text-white">{alert.target_plate}</span>
              </div>
              <div className="mt-1 text-slate-400">
                {alert.details}
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
