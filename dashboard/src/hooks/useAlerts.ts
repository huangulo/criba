"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { AlertMessage, getWsUrl } from "@/lib/api";

export function useAlerts() {
  const [alerts, setAlerts] = useState<AlertMessage[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    const ws = new WebSocket(getWsUrl());

    ws.onmessage = (event) => {
      try {
        const alert: AlertMessage = JSON.parse(event.data);
        setAlerts((prev) => [alert, ...prev].slice(0, 100));
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setTimeout(connect, 5000);
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  const highProbabilityAlerts = alerts.filter((a) => {
    const prob = (a.data as Record<string, unknown>)?.coordination_probability;
    return typeof prob === "number" && prob > 0.8;
  });

  return { alerts, highProbabilityAlerts };
}
