'use client';

import { useState } from 'react';
import { useTelemetryStore } from '../../stores/useTelemetryStore';

type Tab = 'telemetry' | 'alerts';

const STATUS_COLORS: Record<string, string> = {
  HOTLIST_HIT: 'text-crimson-alert',
  CLONED_PLATE_SPOOF: 'text-crimson-alert',
  SPEED_VIOLATION: 'text-amber-suspect',
  BLIND_SPOT_DEVIATION: 'text-amber-suspect',
};

export default function EventPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('telemetry');
  const telemetryLogs = useTelemetryStore((state) => state.telemetryLogs);
  const alerts = useTelemetryStore((state) => state.alerts);

  return (
    <div className="flex flex-col h-full bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      {/* Tab Header */}
      <div className="flex items-center border-b border-zinc-800 shrink-0 bg-zinc-950">
        {(['telemetry', 'alerts'] as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 font-mono text-xs uppercase tracking-widest border-r border-zinc-800 transition-colors ${
              activeTab === tab
                ? tab === 'alerts'
                  ? 'bg-zinc-900 text-crimson-alert border-b-2 border-b-crimson-alert'
                  : 'bg-zinc-900 text-cyan-telemetry border-b-2 border-b-cyan-telemetry'
                : 'text-zinc-500 hover:text-zinc-300 bg-transparent'
            }`}
          >
            {tab === 'telemetry' ? (
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-telemetry animate-ping inline-block"></span>
                Live Telemetry
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-crimson-alert inline-block"></span>
                Critical Alerts
                {alerts.length > 0 && (
                  <span className="ml-1 bg-crimson-alert text-white rounded-full text-[9px] px-1.5 py-0.5">
                    {alerts.length}
                  </span>
                )}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Column Headers */}
      <div className="grid grid-cols-[120px_80px_1fr_80px_120px] gap-2 px-3 py-1.5 bg-zinc-950/60 border-b border-zinc-800 shrink-0">
        {['TIMESTAMP', 'NODE', 'PLATE', 'SPEED', 'STATUS'].map((h) => (
          <span key={h} className="font-mono text-[9px] text-zinc-600 tracking-widest uppercase">{h}</span>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {activeTab === 'telemetry' ? (
          telemetryLogs.length === 0 ? (
            <EmptyState label="AWAITING TELEMETRY EVENTS..." />
          ) : (
            telemetryLogs.map((log, i) => {
              const conf = log.license_plate.confidence;
              const statusColor = conf >= 0.85 ? 'text-emerald-online' : 'text-amber-suspect';
              const statusLabel = conf >= 0.85 ? 'CLEAN' : 'SUSPECT';
              return (
                <div
                  key={`${log.event_id}-${i}`}
                  className="grid grid-cols-[120px_80px_1fr_80px_120px] gap-2 px-3 py-2 border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors"
                >
                  <span className="font-mono text-[10px] text-zinc-500">{new Date(log.timestamp).toLocaleTimeString()}</span>
                  <span className="font-mono text-[10px] text-zinc-400">{log.camera_id}</span>
                  <span className="font-mono text-[10px] text-cyan-telemetry font-semibold">{log.license_plate.text}</span>
                  <span className="font-mono text-[10px] text-amber-suspect">{log.speed_kmh} km/h</span>
                  <span className={`font-mono text-[10px] font-semibold ${statusColor}`}>{statusLabel}</span>
                </div>
              );
            })
          )
        ) : alerts.length === 0 ? (
          <EmptyState label="NO ACTIVE ALERTS" />
        ) : (
          alerts.map((alert, i) => (
            <div
              key={`${alert.alert_id}-${i}`}
              className="grid grid-cols-[120px_80px_1fr_80px_120px] gap-2 px-3 py-2 border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors"
            >
              <span className="font-mono text-[10px] text-zinc-500">{new Date(alert.created_at).toLocaleTimeString()}</span>
              <span className="font-mono text-[10px] text-zinc-400">{alert.source_camera_id}</span>
              <span className="font-mono text-[10px] text-crimson-alert font-semibold">{alert.target_plate}</span>
              <span className="font-mono text-[10px] text-zinc-500">—</span>
              <span className={`font-mono text-[10px] font-semibold ${STATUS_COLORS[alert.alert_type] ?? 'text-zinc-400'}`}>
                {alert.severity}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="h-full flex items-center justify-center">
      <span className="text-[10px] text-zinc-600 font-mono tracking-widest animate-pulse">{label}</span>
    </div>
  );
}
