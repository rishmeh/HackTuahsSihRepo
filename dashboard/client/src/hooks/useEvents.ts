/**
 * useEvents — subscribes to the ML backend WebSocket for real-time events.
 * Reconnects automatically every 3 s if the connection drops.
 */
import { useEffect, useRef } from "react";

type WsEvent = Record<string, unknown>;

const ML_WS =
  (import.meta.env.VITE_ML_WS_URL as string | undefined) ??
  "ws://127.0.0.1:8000/ws/events";

export function useEvents(onEvent: (e: WsEvent) => void): void {
  const ref = useRef(onEvent);
  ref.current = onEvent;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let dead = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (dead) return;
      ws = new WebSocket(ML_WS);
      ws.onmessage = (e) => {
        try {
          ref.current(JSON.parse(e.data as string));
        } catch {
          // ignore malformed frames
        }
      };
      ws.onclose = () => {
        if (!dead) timer = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws?.close();
    }

    connect();
    return () => {
      dead = true;
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, []); // stable via ref — intentionally empty
}
