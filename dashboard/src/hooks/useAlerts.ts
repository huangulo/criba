"use client";

import { useEffect, useState } from "react";
import { AlertMessage, getWsUrl } from "@/lib/api";

const RECONNECT_DELAY_MS = 5000;

export function useAlerts() {
  const [alerts, setAlerts] = useState<AlertMessage[]>([]);

  useEffect(() => {
    // Everything the connection needs lives inside the effect so unmount can
    // tear it all down: the socket, any pending reconnect timer, and the
    // disposed flag that keeps a late onclose from scheduling a zombie
    // reconnect after the component is gone.
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) return;

      ws = new WebSocket(getWsUrl());

      ws.onmessage = (event) => {
        try {
          const alert: AlertMessage = JSON.parse(event.data);
          setAlerts((prev) => [alert, ...prev].slice(0, 100));
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = (event) => {
        // 4401 = API key rejected. The key is baked in at build time, so
        // reconnecting with the same one can never succeed.
        if (disposed || event.code === 4401) return;
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          connect();
        }, RECONNECT_DELAY_MS);
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = null;
      if (ws && ws.readyState !== WebSocket.CLOSED) {
        ws.close();
      }
    };
  }, []);

  const highProbabilityAlerts = alerts.filter((a) => {
    const prob = (a.data as Record<string, unknown>)?.coordination_probability;
    return typeof prob === "number" && prob > 0.8;
  });

  return { alerts, highProbabilityAlerts };
}
