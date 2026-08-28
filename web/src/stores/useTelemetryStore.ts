import { create } from 'zustand'
import { TelemetryEvent, AlertEvent } from '../types/telemetry'

interface TelemetryState {
  activeCameraId: string | null;
  activeTarget: TelemetryEvent | null;
  telemetryLogs: TelemetryEvent[];
  alerts: AlertEvent[];
  
  setActiveCamera: (id: string) => void;
  setActiveTarget: (target: TelemetryEvent | null) => void;
  addTelemetryEvent: (event: TelemetryEvent) => void;
  addAlert: (alert: AlertEvent) => void;
}

export const useTelemetryStore = create<TelemetryState>()((set) => ({
  activeCameraId: null,
  activeTarget: null,
  telemetryLogs: [],
  alerts: [],

  setActiveCamera: (id: string) => set({ activeCameraId: id }),
  setActiveTarget: (target: TelemetryEvent | null) => set({ activeTarget: target }),

  addTelemetryEvent: (event: TelemetryEvent) => 
    set((state) => {
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
