import { useEffect, useRef, useCallback } from 'react';
import { useRigStore } from '@/stores/rigStore';
import type { ServerStatus } from '@/types';

const RECONNECT_DELAY_MS = 1500;

/**
 * WebSocket hook for real-time server status updates.
 * Automatically reconnects on disconnect.
 */
export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const setStatus = useRigStore((state) => state.setStatus);

  const connect = useCallback(() => {
    // Determine WebSocket URL based on current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WebSocket] Connected');
      };

      ws.onmessage = (event) => {
        try {
          const status: ServerStatus = JSON.parse(event.data);
          setStatus(status);
        } catch (e) {
          console.error('[WebSocket] Failed to parse message:', e);
        }
      };

      ws.onclose = () => {
        console.log('[WebSocket] Disconnected, reconnecting...');
        wsRef.current = null;
        scheduleReconnect();
      };

      ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
        try {
          ws.close();
        } catch {
          // Ignore close errors
        }
      };
    } catch (e) {
      console.error('[WebSocket] Failed to connect:', e);
      scheduleReconnect();
    }
  }, [setStatus]);

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    reconnectTimeoutRef.current = window.setTimeout(() => {
      connect();
    }, RECONNECT_DELAY_MS);
  }, [connect]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return wsRef;
}
