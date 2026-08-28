'use client';

import { useEffect, useRef, useState } from 'react';
import { useTelemetryStore } from '../../stores/useTelemetryStore';
import cameraNodes from '../../../../contracts/topology/camera_nodes.json';

export default function VideoViewport() {
  const activeTarget = useTelemetryStore((state) => state.activeTarget);
  const activeCameraId = useTelemetryStore((state) => state.activeCameraId);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [currentTime, setCurrentTime] = useState('');

  // Update clock every second
  useEffect(() => {
    const tick = () => setCurrentTime(new Date().toLocaleTimeString('en-GB'));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const activeCamera = cameraNodes.find((n) => n.camera_id === activeCameraId);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resizeCanvas = () => {
      canvas.width = canvas.clientWidth;
      canvas.height = canvas.clientHeight;
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (activeTarget && activeTarget.bounding_box) {
        const [xmin, ymin, xmax, ymax] = activeTarget.bounding_box;
        const x = xmin * canvas.width;
        const y = ymin * canvas.height;
        const w = (xmax - xmin) * canvas.width;
        const h = (ymax - ymin) * canvas.height;

        const isSuspect = activeTarget.license_plate.confidence < 0.85;
        const color = isSuspect ? '#ef4444' : '#06b6d4';

        // Dashed main box
        ctx.setLineDash([6, 3]);
        ctx.strokeStyle = color + '88';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x, y, w, h);
        ctx.setLineDash([]);

        // Solid corner brackets
        const bL = Math.min(18, w * 0.2, h * 0.2);
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        [
          [[x, y + bL], [x, y], [x + bL, y]],
          [[x + w - bL, y], [x + w, y], [x + w, y + bL]],
          [[x, y + h - bL], [x, y + h], [x + bL, y + h]],
          [[x + w - bL, y + h], [x + w, y + h], [x + w, y + h - bL]],
        ].forEach(([[ax, ay], [bx, by], [cx, cy]]) => {
          ctx.beginPath();
          ctx.moveTo(ax, ay);
          ctx.lineTo(bx, by);
          ctx.lineTo(cx, cy);
          ctx.stroke();
        });

        // Label pill
        const label = `${activeTarget.license_plate.text}  ${activeTarget.speed_kmh} km/h`;
        ctx.font = 'bold 11px monospace';
        const tw = ctx.measureText(label).width;
        const lx = Math.max(x, 4);
        const ly = y > 22 ? y - 22 : y + h + 4;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.roundRect(lx, ly, tw + 16, 20, 4);
        ctx.fill();
        ctx.fillStyle = '#09090b';
        ctx.fillText(label, lx + 8, ly + 14);
      }
    };

    draw();
    return () => window.removeEventListener('resize', resizeCanvas);
  }, [activeTarget, activeCameraId]);

  return (
    <div className="flex flex-col h-full bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      {/* Camera header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-950 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-online shadow-[0_0_6px_#10b981] inline-block"></span>
          <span className="font-mono text-xs text-cyan-telemetry tracking-widest">
            {activeCamera ? `[ ${activeCamera.camera_id} : ${activeCamera.name.toUpperCase()} ]` : '[ NO CAMERA SOURCE ]'}
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[10px] text-zinc-500">
          {activeCamera && <span>{activeCamera.fps} FPS</span>}
          <span className="text-zinc-400">{currentTime}</span>
        </div>
      </div>

      {/* Video + Canvas */}
      <div className="relative flex-1 bg-black flex items-center justify-center">
        {activeCameraId ? (
          <>
            <video
              className="absolute inset-0 w-full h-full object-cover"
              autoPlay loop muted playsInline
              src="https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
            />
            <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" />
          </>
        ) : (
          <span className="text-zinc-600 animate-pulse font-mono tracking-widest text-sm">
            [ AWAITING CAMERA STREAM ]
          </span>
        )}
      </div>
    </div>
  );
}
