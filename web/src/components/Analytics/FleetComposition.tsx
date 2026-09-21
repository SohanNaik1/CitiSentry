'use client';

import { useTelemetryStore } from '../../stores/useTelemetryStore';

export default function FleetComposition() {
  const analyticsData = useTelemetryStore((state) => state.analyticsData);

  if (!analyticsData || !analyticsData.fleet_composition) {
    return (
      <div className="h-full flex items-center justify-center bg-zinc-950 border border-zinc-800 rounded-lg">
        <p className="font-mono text-[10px] tracking-widest text-zinc-500">
          AWAITING FLEET DATA...
        </p>
      </div>
    );
  }

  const fleet = analyticsData.fleet_composition;
  const entries = Object.entries(fleet).sort(([, a], [, b]) => b - a);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);

  return (
    <div className="h-full flex flex-col bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden text-zinc-300">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0">
        <h3 className="font-sans text-lg font-bold tracking-wide text-zinc-200 uppercase">
          STRATEGIC KPI & FLEET COMPOSITION
        </h3>
        <span className="font-sans text-sm tracking-wider text-zinc-400 uppercase">
          WINDOW: ROLLING 24H UTC
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-8">
        
        {/* KPI Row (Minimalist) */}
        <div className="flex gap-6">
          <div className="flex-1 border border-zinc-800 bg-zinc-900/50 p-6 rounded-lg flex flex-col gap-2 shadow-sm">
            <span className="font-sans text-sm font-semibold text-zinc-400 uppercase tracking-wider">TOTAL SCANS (24H)</span>
            <div className="flex items-baseline gap-3">
              <span className="font-sans text-5xl font-black text-zinc-100">
                {analyticsData.all_time_total ? analyticsData.all_time_total.toLocaleString() : "0"}
              </span>
              <span className="font-sans text-sm font-medium text-zinc-500 uppercase tracking-widest">LIVE</span>
            </div>
          </div>
          <div className="flex-1 border border-zinc-800 bg-zinc-900/50 p-6 rounded-lg flex flex-col gap-2 shadow-sm">
            <span className="font-sans text-sm font-semibold text-zinc-400 uppercase tracking-wider">ACTIVE NODES</span>
            <div className="flex items-baseline gap-3">
              <span className="font-sans text-5xl font-black text-zinc-100">{analyticsData.node_avg_speeds ? Object.keys(analyticsData.node_avg_speeds).length : 0}</span>
              <span className="font-sans text-sm font-medium text-emerald-online uppercase tracking-widest">ONLINE</span>
            </div>
          </div>
        </div>

        {/* Taxonomy Section */}
        <div className="flex flex-col gap-6 mt-4">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800/50">
            <span className="font-sans text-sm font-bold text-zinc-300 uppercase tracking-widest">AI VEHICLE CLASS TAXONOMY</span>
            <span className="font-sans text-sm font-medium text-zinc-500 uppercase tracking-wider">CONFIDENCE &gt; 94.6%</span>
          </div>

          <div className="grid grid-cols-2 gap-x-12 gap-y-6">
            {entries.map(([cls, count]) => {
              const pct = total > 0 ? ((count / total) * 100).toFixed(1) : "0.0";
              return (
                <div key={cls} className="flex flex-col gap-3">
                  <div className="flex justify-between items-baseline">
                    <span className="font-sans text-base font-bold text-zinc-200 tracking-wider uppercase">
                      {cls}
                    </span>
                    <div className="font-sans text-base font-semibold text-zinc-400">
                      <span className="text-zinc-100">{pct}%</span>
                      <span className="text-zinc-600 ml-2">({count.toLocaleString()})</span>
                    </div>
                  </div>
                  {/* Subtle bar indicator */}
                  <div className="w-full h-1.5 bg-zinc-900 overflow-hidden rounded-full">
                    <div className="h-full bg-zinc-600 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

      </div>
    </div>
  );
}
