import { useEffect, useRef, useState, useCallback } from 'react';

interface WSEvent {
  topic?: string;
  customer_id?: string;
  event_type?: string;
  category?: string;
  [key: string]: unknown;
}

export function useWebSocket(path: string, maxEvents = 100) {
  const [events, setEvents] = useState<WSEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}${path}`;
    const ws = new WebSocket(url);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setTimeout(connect, 3000);
    };
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        setEvents((prev) => [data, ...prev].slice(0, maxEvents));
      } catch {
        // ignore non-JSON messages
      }
    };
    wsRef.current = ws;
  }, [path, maxEvents]);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, [connect]);

  const clear = useCallback(() => setEvents([]), []);

  return { events, connected, clear };
}
