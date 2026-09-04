import { create } from 'zustand'
import { TelemetryEvent, AlertEvent } from '../types/telemetry'

interface TelemetryState {
  activeCameraId: string | null;
  activeTarget: TelemetryEvent | null;
  telemetryLogs: TelemetryEvent[];
  alerts: AlertEvent[];
  trackedPlate: string | null;
  trackAttempt: number;
  activeSystemId: string | null;
  
  setActiveCamera: (id: string) => void;
  setActiveTarget: (target: TelemetryEvent | null) => void;
  addTelemetryEvent: (event: TelemetryEvent) => void;
  addAlert: (alert: AlertEvent) => void;
  setTrackedPlate: (plate: string | null) => void;
  setActiveSystemId: (id: string | null) => void;
  incrementTrackAttempt: () => void;
  clearState: () => void;
}

export const useTelemetryStore = create<TelemetryState>()((set) => ({
  activeCameraId: null,
  activeTarget: null,
  telemetryLogs: [],
  alerts: [],
  trackedPlate: null,
  trackAttempt: 0,
  activeSystemId: null,

  setActiveCamera: (id: string) => set({ activeCameraId: id }),
  setActiveTarget: (target: TelemetryEvent | null) => set({ activeTarget: target }),
  setTrackedPlate: (plate: string | null) => set({ trackedPlate: plate }),
  setActiveSystemId: (id: string | null) => set({ activeSystemId: id }),
  incrementTrackAttempt: () => set((state) => ({ trackAttempt: state.trackAttempt + 1 })),

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
      if (state.trackedPlate === "UNKNOWN" || state.trackedPlate === event.license_plate.text) {
        nextTrackedPlate = event.license_plate.text;
        nextActiveTarget = event;
        if (event.system_id) {
          nextActiveSystemId = event.system_id;
        }
      }

      const existingIdx = state.telemetryLogs.findIndex(l => l.system_id === event.system_id && l.camera_id === event.camera_id);
      if (existingIdx !== -1) {
        const newLogs = [...state.telemetryLogs];
        newLogs[existingIdx] = event; // Overwrite only for the same camera to prevent spam, but keep history across cameras
        return { telemetryLogs: newLogs, activeTarget: nextActiveTarget, trackedPlate: nextTrackedPlate, activeSystemId: nextActiveSystemId };
      }
      
      // Keep max 100 events to prevent memory leaks
      const newLogs = [event, ...state.telemetryLogs].slice(0, 100);
      return { telemetryLogs: newLogs, activeTarget: nextActiveTarget, trackedPlate: nextTrackedPlate, activeSystemId: nextActiveSystemId };
    }),

  addAlert: (alert: AlertEvent) =>
    set((state) => ({ alerts: [alert, ...state.alerts] })),
}))
