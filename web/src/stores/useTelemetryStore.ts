import { create } from 'zustand'
import { TelemetryEvent, AlertEvent, AnalyticsSnapshot } from '../types/telemetry'

type AppMode = 'TACTICAL' | 'STRATEGIC';

interface TelemetryState {
  activeCameraId: string | null;
  activeTarget: TelemetryEvent | null;
  telemetryLogs: TelemetryEvent[];
  alerts: AlertEvent[];
  trackedPlate: string | null;
  trackAttempt: number;
  activeSystemId: string | null;
  appMode: AppMode;
  analyticsData: AnalyticsSnapshot | null;
  fluxHistory: Array<{ time: string, total: number, congested: number }>;
  
  setActiveCamera: (id: string) => void;
  setActiveTarget: (target: TelemetryEvent | null) => void;
  addTelemetryEvent: (event: TelemetryEvent) => void;
  addAlert: (alert: AlertEvent) => void;
  setTrackedPlate: (plate: string | null) => void;
  setActiveSystemId: (id: string | null) => void;
  incrementTrackAttempt: () => void;
  clearState: () => void;
  setAppMode: (mode: AppMode) => void;
  setAnalyticsData: (data: AnalyticsSnapshot) => void;
}

export const useTelemetryStore = create<TelemetryState>()((set) => ({
  activeCameraId: null,
  activeTarget: null,
  telemetryLogs: [],
  alerts: [],
  trackedPlate: null,
  trackAttempt: 0,
  activeSystemId: null,
  appMode: 'TACTICAL',
  analyticsData: null,
  fluxHistory: [],

  setActiveCamera: (id: string) => set({ activeCameraId: id }),
  setActiveTarget: (target: TelemetryEvent | null) => set({ activeTarget: target }),
  setTrackedPlate: (plate: string | null) => set({ trackedPlate: plate }),
  setActiveSystemId: (id: string | null) => set({ activeSystemId: id }),
  incrementTrackAttempt: () => set((state) => ({ trackAttempt: state.trackAttempt + 1 })),
  setAppMode: (mode: AppMode) => set({ appMode: mode }),
  setAnalyticsData: (data: AnalyticsSnapshot) => set((state) => {
    let currentTotal = Object.values(data.fleet_composition || {}).reduce((sum, val) => sum + val, 0);
    currentTotal = Math.round(currentTotal / 30);
    
    // Calculate congested vehicles by finding ratio of actively congested nodes (speed < 15 and speed > 0)
    const nodeSpeeds = Object.values(data.node_avg_speeds || {});
    const congestedNodes = nodeSpeeds.filter(speed => speed > 0 && speed < 15.0).length;
    const congestedRatio = nodeSpeeds.length > 0 ? (congestedNodes / nodeSpeeds.length) : 0;
    const currentCongested = Math.round(currentTotal * congestedRatio);

    const newPoint = {
      time: new Date().toLocaleTimeString([], { minute: '2-digit', second: '2-digit' }),
      total: currentTotal,
      congested: currentCongested
    };
    return {
      analyticsData: data,
      fluxHistory: [...state.fluxHistory, newPoint].slice(-20)
    };
  }),

  clearState: () => set((state) => ({
    activeTarget: null,
    trackedPlate: null,
    // explicitly NOT resetting activeCameraId or telemetryLogs so data stays active
  })),

  addTelemetryEvent: (event: TelemetryEvent) => 
    set((state) => {
      let nextTrackedPlate = state.trackedPlate;
      let nextActiveTarget = state.activeTarget;
      
      let nextActiveSystemId = state.activeSystemId;
      
      // If we initiated a track on an UNKNOWN plate and the backend locked it,
      // or if it matches the plate we are currently tracking, update the target!
      if (state.trackedPlate === "UNKNOWN" || state.trackedPlate === event.ocr_text) {
        nextTrackedPlate = event.ocr_text;
        nextActiveTarget = event;
        if (event.system_id) {
          nextActiveSystemId = event.system_id;
        }
      }

      const existingIdx = state.telemetryLogs.findIndex(l => l.system_id === event.system_id && l.camera_id === event.camera_id);
      if (existingIdx !== -1) {
        const newLogs = [...state.telemetryLogs];
        newLogs[existingIdx] = event; // Overwrite for the SAME camera to prevent spam
        return { telemetryLogs: newLogs, activeTarget: nextActiveTarget, trackedPlate: nextTrackedPlate, activeSystemId: nextActiveSystemId };
      }
      
      // Keep max 100 events to prevent memory leaks
      const newLogs = [event, ...state.telemetryLogs].slice(0, 100);
      return { telemetryLogs: newLogs, activeTarget: nextActiveTarget, trackedPlate: nextTrackedPlate, activeSystemId: nextActiveSystemId };
    }),

  addAlert: (alert: AlertEvent) =>
    set((state) => ({ alerts: [alert, ...state.alerts] })),
}))
