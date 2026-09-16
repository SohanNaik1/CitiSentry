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
  activeTrajectory: string[];
  
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
  activeTrajectory: [],

  setActiveCamera: (id: string) => set({ activeCameraId: id }),
  setActiveTarget: (target: TelemetryEvent | null) => set({ activeTarget: target }),
  setTrackedPlate: (plate: string | null) => set({ trackedPlate: plate }),
  setActiveSystemId: (id: string | null) => set({ activeSystemId: id }),
  incrementTrackAttempt: () => set((state) => ({ trackAttempt: state.trackAttempt + 1 })),

  clearState: () => set((state) => ({
    activeTarget: null,
    trackedPlate: null,
    activeTrajectory: [],
    // explicitly NOT resetting activeCameraId or telemetryLogs so data stays active
  })),

  addTelemetryEvent: (event: TelemetryEvent) => 
    set((state) => {
      let nextTrackedPlate = state.trackedPlate;
      let nextActiveTarget = state.activeTarget;
      
      let nextActiveSystemId = state.activeSystemId;
      
      let nextActiveCameraId = state.activeCameraId;
      let nextTrajectory = state.activeTrajectory;

      if (state.trackedPlate === "UNKNOWN" || state.trackedPlate === event.license_plate.text) {
        nextTrackedPlate = event.license_plate.text;
        nextActiveTarget = event;
        if (event.system_id) {
          if (state.activeSystemId !== event.system_id) {
            nextActiveSystemId = event.system_id;
            nextTrajectory = [event.camera_id]; // Reset trajectory for new system
          } else {
            // Append camera to trajectory if it's new or moving to a different one
            if (nextTrajectory.length === 0 || nextTrajectory[nextTrajectory.length - 1] !== event.camera_id) {
               if (!nextTrajectory.includes(event.camera_id)) {
                  nextTrajectory = [...nextTrajectory, event.camera_id];
               }
            }
          }
        }
        // AUTOMATIC CAMERA SWITCHING:
        // If the target moved to a new camera, switch the active camera automatically!
        if (event.camera_id !== state.activeCameraId) {
          nextActiveCameraId = event.camera_id;
        }
      }

      const existingIdx = state.telemetryLogs.findIndex(l => l.system_id === event.system_id && l.camera_id === event.camera_id);
      if (existingIdx !== -1) {
        const newLogs = [...state.telemetryLogs];
        const existingEvent = newLogs[existingIdx];
        newLogs[existingIdx] = { 
          ...event, 
          timestamp: existingEvent.timestamp, 
          epoch_ms: existingEvent.epoch_ms 
        }; // Overwrite but preserve initial timestamp to prevent map path fluctuation
        return { telemetryLogs: newLogs, activeTarget: nextActiveTarget, trackedPlate: nextTrackedPlate, activeSystemId: nextActiveSystemId, activeCameraId: nextActiveCameraId, activeTrajectory: nextTrajectory };
      }
      
      // Keep max 100 events to prevent memory leaks
      const newLogs = [event, ...state.telemetryLogs].slice(0, 100);
      return { telemetryLogs: newLogs, activeTarget: nextActiveTarget, trackedPlate: nextTrackedPlate, activeSystemId: nextActiveSystemId, activeCameraId: nextActiveCameraId, activeTrajectory: nextTrajectory };
    }),

  addAlert: (alert: AlertEvent) =>
    set((state) => ({ alerts: [alert, ...state.alerts] })),
}))
