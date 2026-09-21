'use client';

import { useState } from 'react';
import { useTelemetryStore } from '../../stores/useTelemetryStore';

type Tab = 'telemetry' | 'alerts';

const STATUS_COLORS: Record<string, string> = {
  HOTLIST_HIT: 'text-red-600 dark:text-crimson-alert',
  CLONED_PLATE_SPOOF: 'text-red-600 dark:text-crimson-alert',
  SPEED_VIOLATION: 'text-amber-600 dark:text-amber-suspect',
  BLIND_SPOT_DEVIATION: 'text-amber-600 dark:text-amber-suspect',
};

export default function EventPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('telemetry');
  const telemetryLogs = useTelemetryStore((state) => state.telemetryLogs);
  const alerts = useTelemetryStore((state) => state.alerts);

  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-lg overflow-hidden transition-colors">
      {/* Tab Header */}
      <div className="flex items-center border-b border-slate-200 dark:border-zinc-800 shrink-0 bg-slate-50 dark:bg-zinc-950 transition-colors">
        {(['telemetry', 'alerts'] as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-5 py-3 text-sm font-semibold uppercase tracking-wider border-r border-slate-200 dark:border-zinc-800 transition-colors ${
              activeTab === tab
                ? tab === 'alerts'
                  ? 'bg-white dark:bg-zinc-900 text-red-600 dark:text-crimson-alert border-b-2 border-b-red-600 dark:border-b-crimson-alert'
                  : 'bg-white dark:bg-zinc-900 text-cyan-700 dark:text-cyan-telemetry border-b-2 border-b-cyan-700 dark:border-b-cyan-telemetry'
                : 'text-slate-500 dark:text-zinc-500 hover:text-slate-700 dark:hover:text-zinc-300 bg-transparent'
            }`}
          >
            {tab === 'telemetry' ? (
              <span>Live Telemetry</span>
            ) : (
              <span className="flex items-center gap-2">
                Critical Alerts
                {alerts.length > 0 && (
                  <span className="bg-red-600 dark:bg-crimson-alert text-white rounded-full text-xs px-2 py-0.5">
                    {alerts.length}
                  </span>
                )}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Column Headers */}
      <div className="grid grid-cols-[120px_80px_1fr_100px_80px_120px] gap-2 px-4 py-2 bg-slate-50/60 dark:bg-zinc-950/60 border-b border-slate-200 dark:border-zinc-800 shrink-0 transition-colors">
        {['TIMESTAMP', 'NODE', 'PLATE', 'TARGET ID', 'SPEED', 'STATUS'].map((h) => (
          <span key={h} className="text-xs text-slate-500 dark:text-zinc-600 tracking-wider uppercase font-semibold">{h}</span>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {activeTab === 'telemetry' ? (
          telemetryLogs.length === 0 ? (
            <EmptyState label="AWAITING TELEMETRY EVENTS..." />
          ) : (
            telemetryLogs.slice(0, 10).map((log, i) => {
              const isViolation = log.speed_kmh > 60;
              const badgeClass = isViolation 
                ? 'text-red-500 bg-red-500/10 border border-red-500/30' 
                : 'text-emerald-500 bg-emerald-500/10 border border-emerald-500/30';
              const statusLabel = isViolation ? 'SPEED VIOLATION' : 'NOMINAL';
              return (
                <div
                  key={`${log.camera_id}-${log.timestamp}-${i}`}
                  className="grid grid-cols-[120px_80px_1fr_100px_80px_140px] gap-2 px-4 py-3 border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors items-center"
                >
                  <span className="text-xs text-zinc-500 font-medium font-mono">{new Date(log.timestamp).toLocaleTimeString()}</span>
                  <span className="text-xs text-zinc-400 font-medium font-mono">{log.camera_id}</span>
                  <span className="text-xs text-zinc-300 font-bold tracking-wider font-mono">{log.ocr_text || 'UNKNOWN'}</span>
                  <span className="text-xs text-zinc-400 font-medium tracking-wider font-mono">{log.system_id || '—'}</span>
                  <span className="text-xs text-zinc-300 font-medium font-mono">{log.speed_kmh?.toFixed(1) || '0.0'} km/h</span>
                  <div>
                    <span className={`text-[9px] font-bold px-2 py-0.5 rounded tracking-widest ${badgeClass}`}>
                      {statusLabel}
                    </span>
                  </div>
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
              className="grid grid-cols-[120px_80px_1fr_100px_80px_120px] gap-2 px-4 py-3 border-b border-slate-100 dark:border-zinc-800/50 hover:bg-slate-50 dark:hover:bg-zinc-800/40 transition-colors"
            >
              <span className="text-sm text-slate-500 dark:text-zinc-500 font-medium">{new Date(alert.created_at).toLocaleTimeString()}</span>
              <span className="text-sm text-slate-600 dark:text-zinc-400 font-medium">{alert.source_camera_id}</span>
              <span className="text-sm text-red-600 dark:text-crimson-alert font-bold tracking-wider">{alert.target_plate}</span>
              <span className="text-sm text-slate-500 dark:text-zinc-500 font-medium">—</span>
              <span className="text-sm text-slate-500 dark:text-zinc-500 font-medium">—</span>
              <span className={`text-sm font-bold ${STATUS_COLORS[alert.alert_type] ?? 'text-slate-400 dark:text-zinc-400'}`}>
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
      <span className="text-sm text-slate-400 dark:text-zinc-600 tracking-wider animate-pulse font-medium">{label}</span>
    </div>
  );
}
