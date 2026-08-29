'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useTelemetryStore } from '../stores/useTelemetryStore';
import type { TelemetryEvent } from '../types/telemetry';

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
        const event = JSON.parse(messageEvent.data as string);

        // Dispatch based on event signature
        if (event.event_id && event.camera_id && event.license_plate) {
          addTelemetryEvent(event as TelemetryEvent);
        } else if (event.alert_id && event.alert_type) {
          addAlert(event);
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
  }, [url, addTelemetryEvent]);

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
