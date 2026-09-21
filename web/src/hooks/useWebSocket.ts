'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useTelemetryStore } from '../stores/useTelemetryStore';
import type { TelemetryEvent, AnalyticsSnapshot } from '../types/telemetry';

export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected';

const RECONNECT_DELAY_MS = 3000;

/**
 * useWebSocket — Custom React hook that manages a persistent WebSocket
 * connection to the Go broker's /ws endpoint.
 *
 * It parses incoming JSON telemetry events and dispatches them into the
 * Zustand global state store. Auto-reconnects on close or error with a
 * 3-second backoff. Safe for Next.js SSR — all browser-only logic runs
 * inside useEffect which only executes on the client.
 */
export function useWebSocket(url: string): WebSocketStatus {
  const [status, setStatus] = useState<WebSocketStatus>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const addTelemetryEvent = useTelemetryStore((state) => state.addTelemetryEvent);
  const addAlert = useTelemetryStore((state) => state.addAlert);
  const setAnalyticsData = useTelemetryStore((state) => state.setAnalyticsData);

  const connect = useCallback(() => {
    // Guard: only run in the browser
    if (typeof window === 'undefined') return;

    // Clean up any existing connection before creating a new one
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
    }

    setStatus('connecting');

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('connected');
    };

    ws.onmessage = (messageEvent: MessageEvent) => {
      try {
        const parsed = JSON.parse(messageEvent.data as string);

        // Dispatch based on message type
        if (parsed.type === 'ANALYTICS_UPDATE' && parsed.data) {
          setAnalyticsData(parsed.data as AnalyticsSnapshot);
        } else if (parsed.type === 'HANDOFF' && parsed.new_camera_id) {
          // Automatic camera handoff triggered by the Go broker
          const setActiveCamera = useTelemetryStore.getState().setActiveCamera;
          setActiveCamera(parsed.new_camera_id);
        } else if (parsed.camera_id && parsed.ocr_text) {
          addTelemetryEvent(parsed as TelemetryEvent);
        } else if (parsed.alert_id && parsed.alert_type) {
          addAlert(parsed);
        }
      } catch {
        // Silently drop malformed messages
      }
    };

    ws.onclose = () => {
      setStatus('disconnected');
      wsRef.current = null;
      scheduleReconnect();
    };

    ws.onerror = () => {
      // The onerror event is always followed by onclose in the browser
      // WebSocket spec, so reconnect logic is handled there.
      ws.close();
    };
  }, [url, addTelemetryEvent, setAnalyticsData]);

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }
    reconnectTimerRef.current = setTimeout(() => {
      connect();
    }, RECONNECT_DELAY_MS);
  }, [connect]);

  useEffect(() => {
    connect();

    return () => {
      // Cleanup on unmount: cancel any pending reconnect and close the socket
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on intentional unmount
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return status;
}
