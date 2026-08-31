import dynamic from 'next/dynamic';

const Map = dynamic(() => import('./MapContent'), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-tactical-dark text-cyan-telemetry font-mono border border-slate-800">
      <div className="animate-pulse tracking-widest">[ INITIATING TACTICAL MAP... ]</div>
    </div>
  ),
});

export default Map;
