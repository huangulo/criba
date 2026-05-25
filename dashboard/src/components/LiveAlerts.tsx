"use client";

import { useState, useRef, useEffect } from "react";
import { Bell, ChevronDown, ChevronUp } from "lucide-react";
import { useAlerts } from "@/hooks/useAlerts";

export default function LiveAlerts() {
  const { alerts, highProbabilityAlerts } = useAlerts();
  const [open, setOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const hasHighAlerts = highProbabilityAlerts.length > 0;

  useEffect(() => {
    if (open && listRef.current) {
      listRef.current.scrollTop = 0;
    }
  }, [alerts.length, open]);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded border border-surface-border bg-surface-card hover:bg-surface-border transition-colors"
      >
        <span className="relative flex h-2.5 w-2.5">
          {hasHighAlerts && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-danger opacity-75" />
          )}
          <span
            className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
              hasHighAlerts ? "bg-danger animate-pulse-glow" : "bg-text-muted"
            }`}
          />
        </span>
        <Bell className="w-4 h-4 text-text-muted" />
        {alerts.length > 0 && (
          <span className="text-xs font-mono text-text-muted">
            {alerts.length}
          </span>
        )}
        {open ? (
          <ChevronUp className="w-3 h-3 text-text-muted" />
        ) : (
          <ChevronDown className="w-3 h-3 text-text-muted" />
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-96 max-h-80 overflow-y-auto rounded border border-surface-border bg-surface-card shadow-2xl z-50">
          <div className="sticky top-0 bg-surface-card border-b border-surface-border px-3 py-2 flex items-center justify-between">
            <span className="text-xs font-mono text-text-muted uppercase tracking-wider">
              Live Alerts
            </span>
            {hasHighAlerts && (
              <span className="text-xs font-mono text-danger">
                {highProbabilityAlerts.length} high probability
              </span>
            )}
          </div>
          <div ref={listRef} className="divide-y divide-surface-border">
            {alerts.length === 0 ? (
              <div className="px-3 py-6 text-center text-text-muted text-sm">
                No alerts received
              </div>
            ) : (
              alerts.map((alert, i) => {
                const isHigh =
                  typeof (alert.data as Record<string, unknown>)
                    ?.coordination_probability === "number" &&
                  ((alert.data as Record<string, unknown>)
                    .coordination_probability as number) > 0.8;
                return (
                  <div
                    key={`${alert.event_type}-${i}`}
                    className={`px-3 py-2.5 animate-slide-in ${
                      isHigh ? "bg-danger/5" : ""
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      {isHigh && (
                        <span className="mt-1 flex h-2 w-2 rounded-full bg-danger animate-pulse-glow shrink-0" />
                      )}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono uppercase text-text-muted">
                            {alert.event_type}
                          </span>
                        </div>
                        <p className="text-sm text-text-primary mt-0.5 leading-snug truncate">
                          {alert.message}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
