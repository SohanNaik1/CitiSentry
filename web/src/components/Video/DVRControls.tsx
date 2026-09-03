'use client';

import { useEffect, useState, useRef, useCallback } from 'react';

interface DVRState {
  effective_time: number;
  master_cycle_sec: number;
  is_paused: boolean;
  camera_id: string;
}

/**
 * Format seconds as MM:SS.d (e.g., 01:11.0)
 */
function formatTimecode(seconds: number): string {
  const clamped = Math.max(0, seconds);
  const mins = Math.floor(clamped / 60);
  const secs = clamped % 60;
  return `${String(mins).padStart(2, '0')}:${secs < 10 ? '0' : ''}${secs.toFixed(1)}`;
}

const VISION_URL = 'http://localhost:5000';

export default function DVRControls() {
  const [dvrState, setDvrState] = useState<DVRState>({
    effective_time: 0,
    master_cycle_sec: 71.0,
    is_paused: false,
    camera_id: 'CAM-001',
  });
  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Poll DVR status every 500ms ──────────────────────────────────────
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${VISION_URL}/dvr/status`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) {
        const data: DVRState = await res.json();
        setDvrState(data);
      }
    } catch {
      // Vision node not reachable — silently retry on next tick
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, 500);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchStatus]);

  // ── Toggle Pause ─────────────────────────────────────────────────────
  const handleTogglePause = useCallback(async () => {
    try {
      const res = await fetch(`${VISION_URL}/dvr/toggle_pause`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setDvrState((prev) => ({
          ...prev,
          is_paused: data.status === 'paused',
          effective_time: data.effective_time,
        }));
      }
    } catch {
      // Silently fail
    }
  }, []);

  // ── Seek ─────────────────────────────────────────────────────────────
  const handleSeek = useCallback(async (seekSec: number) => {
    const clamped = Math.max(0, Math.min(seekSec, dvrState.master_cycle_sec - 0.01));
    try {
      const res = await fetch(`${VISION_URL}/dvr/seek`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seek_sec: clamped }),
      });
      if (res.ok) {
        const data = await res.json();
        setDvrState((prev) => ({
          ...prev,
          effective_time: data.effective_time,
        }));
      }
    } catch {
      // Silently fail
    }
  }, [dvrState.master_cycle_sec]);

  // ── Jump Controls ────────────────────────────────────────────────────
  const handleJump = useCallback(
    (delta: number) => {
      const currentTime = isDragging ? dragValue : dvrState.effective_time;
      handleSeek(currentTime + delta);
    },
    [isDragging, dragValue, dvrState.effective_time, handleSeek]
  );

  const handleRewind = useCallback(() => {
    handleSeek(0);
  }, [handleSeek]);

  // ── Keyboard shortcut: spacebar toggles pause ────────────────────────
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // Only fire if no input/textarea is focused
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === 'Space') {
        e.preventDefault();
        handleTogglePause();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handleTogglePause]);

  // ── Slider event handlers ────────────────────────────────────────────
  const handleSliderInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setDragValue(val);
    setIsDragging(true);
  };

  const handleSliderCommit = () => {
    setIsDragging(false);
    handleSeek(dragValue);
  };

  const displayTime = isDragging ? dragValue : dvrState.effective_time;
  const progressPct = (displayTime / dvrState.master_cycle_sec) * 100;

  return (
    <div
      className="flex items-center gap-3 px-3 py-2 border-t border-zinc-800/80"
      style={{ background: '#111318' }}
    >
      {/* ── Play / Pause Button ──────────────────────────────────────── */}
      <button
        onClick={handleTogglePause}
        className="flex items-center justify-center w-8 h-8 rounded border transition-colors duration-150 flex-shrink-0"
        style={{
          borderColor: dvrState.is_paused ? '#f59e0b' : '#10b981',
          color: dvrState.is_paused ? '#f59e0b' : '#10b981',
          background: dvrState.is_paused ? 'rgba(245,158,11,0.08)' : 'rgba(16,185,129,0.08)',
        }}
        title={dvrState.is_paused ? 'Resume (Space)' : 'Pause (Space)'}
      >
        {dvrState.is_paused ? (
          /* Play triangle */
          <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
            <polygon points="3,1 12,7 3,13" />
          </svg>
        ) : (
          /* Pause bars */
          <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
            <rect x="2" y="1" width="3.5" height="12" rx="0.5" />
            <rect x="8.5" y="1" width="3.5" height="12" rx="0.5" />
          </svg>
        )}
      </button>

      {/* ── Rewind Button ────────────────────────────────────────────── */}
      <button
        onClick={handleRewind}
        className="text-[10px] font-mono font-bold tracking-wider px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-cyan-telemetry hover:border-cyan-telemetry/40 transition-colors duration-150 flex-shrink-0"
        title="Rewind to 0:00"
      >
        |◀
      </button>

      {/* ── Jump -5s ─────────────────────────────────────────────────── */}
      <button
        onClick={() => handleJump(-5)}
        className="text-[10px] font-mono font-bold tracking-wider px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-cyan-telemetry hover:border-cyan-telemetry/40 transition-colors duration-150 flex-shrink-0"
        title="Jump back 5 seconds"
      >
        -5s
      </button>

      {/* ── Timeline Scrubber ────────────────────────────────────────── */}
      <div className="flex-1 relative flex items-center min-w-0">
        {/* Progress track background */}
        <div className="absolute inset-0 h-[6px] top-1/2 -translate-y-1/2 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className="h-full rounded-full transition-[width] duration-100"
            style={{
              width: `${progressPct}%`,
              background: dvrState.is_paused
                ? 'linear-gradient(90deg, #f59e0b 0%, #d97706 100%)'
                : 'linear-gradient(90deg, #06b6d4 0%, #0891b2 100%)',
            }}
          />
        </div>
        <input
          type="range"
          min={0}
          max={dvrState.master_cycle_sec}
          step={0.1}
          value={displayTime}
          onChange={handleSliderInput}
          onMouseUp={handleSliderCommit}
          onTouchEnd={handleSliderCommit}
          className="relative w-full h-5 opacity-0 cursor-pointer z-10"
          style={{ margin: 0 }}
        />
      </div>

      {/* ── Jump +5s ─────────────────────────────────────────────────── */}
      <button
        onClick={() => handleJump(5)}
        className="text-[10px] font-mono font-bold tracking-wider px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-cyan-telemetry hover:border-cyan-telemetry/40 transition-colors duration-150 flex-shrink-0"
        title="Jump forward 5 seconds"
      >
        +5s
      </button>

      {/* ── Timecode Readout ─────────────────────────────────────────── */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        <span
          className="font-mono text-[11px] tracking-wider tabular-nums"
          style={{ color: dvrState.is_paused ? '#f59e0b' : '#06b6d4' }}
        >
          {formatTimecode(displayTime)}
        </span>
        <span className="font-mono text-[11px] text-zinc-600">/</span>
        <span className="font-mono text-[11px] text-zinc-500 tracking-wider tabular-nums">
          {formatTimecode(dvrState.master_cycle_sec)}
        </span>
      </div>

      {/* ── Sync Status Badge ────────────────────────────────────────── */}
      <div
        className="text-[8px] font-bold tracking-[0.15em] uppercase px-2 py-0.5 rounded flex-shrink-0"
        style={{
          color: dvrState.is_paused ? '#f59e0b' : '#10b981',
          background: dvrState.is_paused ? 'rgba(245,158,11,0.1)' : 'rgba(16,185,129,0.1)',
          border: `1px solid ${dvrState.is_paused ? 'rgba(245,158,11,0.25)' : 'rgba(16,185,129,0.25)'}`,
        }}
      >
        {dvrState.is_paused ? 'PAUSED' : 'SYNC: LOCKED'}
      </div>
    </div>
  );
}
