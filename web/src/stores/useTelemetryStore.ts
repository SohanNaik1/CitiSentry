import { create } from 'zustand'
import { TelemetryEvent, AlertEvent } from '../types/telemetry'

interface TelemetryState {
  activeCameraId: string | null;
  activeTarget: TelemetryEvent | null;
  telemetryLogs: TelemetryEvent[];
  alerts: AlertEvent[];
  trackedPlate: string | null;
  
  setActiveCamera: (id: string) => void;
  setActiveTarget: (target: TelemetryEvent | null) => void;
  addTelemetryEvent: (event: TelemetryEvent) => void;
  addAlert: (alert: AlertEvent) => void;
  setTrackedPlate: (plate: string | null) => void;
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

  setActiveCamera: (id: string) => set({ activeCameraId: id }),
  setActiveTarget: (target: TelemetryEvent | null) => set({ activeTarget: target }),
  setTrackedPlate: (plate: string | null) => set({ trackedPlate: plate }),
  incrementTrackAttempt: () => set((state) => ({ trackAttempt: state.trackAttempt + 1 })),

  clearState: () => set((state) => ({
    activeTarget: null,
    telemetryLogs: [],
    trackedPlate: null,
    // explicitly NOT resetting activeCameraId so the camera feed stays active
  })),

  addTelemetryEvent: (event: TelemetryEvent) => 
    set((state) => {
      const existingIdx = state.telemetryLogs.findIndex(l => l.license_plate.plate === event.license_plate.plate);
      if (existingIdx !== -1) {
        const newLogs = [...state.telemetryLogs];
        newLogs[existingIdx] = event; // Overwrite to prevent spam
        return { telemetryLogs: newLogs };
      }
      // Keep max 100 events to prevent memory leaks
      const newLogs = [event, ...state.telemetryLogs];
      if (newLogs.length > 100) {
        newLogs.length = 100;
      }
      return { telemetryLogs: newLogs };
    }),

  addAlert: (alert: AlertEvent) =>
    set((state) => ({ alerts: [alert, ...state.alerts] })),
}))
