import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { useTelemetryStore } from '../../stores/useTelemetryStore';

export default function TrafficFluxChart() {
  const fluxHistory = useTelemetryStore((state) => state.fluxHistory);

  return (
    <div className="w-full h-full flex flex-col p-4">
      <div className="text-zinc-400 font-mono text-xs uppercase tracking-widest mb-4 font-bold border-b border-zinc-800 pb-2 flex justify-between">
        <span>[ TRAFFIC FLUX & CONGESTION ]</span>
        <span className="text-zinc-600">LIVE</span>
      </div>
      
      <div className="flex-1 w-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={fluxHistory} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
            <XAxis 
              dataKey="time" 
              axisLine={false} 
              tickLine={false} 
              tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'monospace' }} 
              minTickGap={20}
            />
            <YAxis 
              axisLine={false} 
              tickLine={false} 
              tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'monospace' }} 
              domain={[0, 'dataMax + 5']}
              allowDecimals={false}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#18181b', 
                borderColor: '#27272a', 
                color: '#e4e4e7', 
                fontFamily: 'monospace',
                fontSize: '12px'
              }}
              itemStyle={{ color: '#e4e4e7' }}
              labelStyle={{ color: '#a1a1aa', marginBottom: '4px' }}
            />
            <Area 
              type="monotone" 
              dataKey="total" 
              stroke="#06b6d4" 
              fill="#06b6d4" 
              fillOpacity={0.2} 
              strokeWidth={2}
              isAnimationActive={false}
            />
            <Area 
              type="monotone" 
              dataKey="congested" 
              stroke="#ef4444" 
              fill="#ef4444" 
              fillOpacity={0.4} 
              strokeWidth={2}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
