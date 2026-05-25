"use client";

import { useEffect, useState, useCallback } from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { fetchNarratives, Narrative } from "@/lib/api";

function statusColor(status: string): string {
  switch (status.toLowerCase()) {
    case "active":
      return "#ef4444";
    case "fading":
      return "#f59e0b";
    case "dead":
      return "#52525b";
    default:
      return "#3b82f6";
  }
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: Narrative & { cx?: number; cy?: number };
  }>;
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded border border-surface-border bg-surface-card px-3 py-2 shadow-xl text-sm">
      <p className="font-mono text-text-primary font-semibold">
        {d.label || d.id.slice(0, 8)}
      </p>
      <p className="text-text-muted font-mono text-xs mt-1">
        Posts: {d.post_count} &middot; Spread: {d.platform_spread}
      </p>
      <p className="font-mono text-xs mt-0.5" style={{ color: statusColor(d.status) }}>
        {d.status.toUpperCase()}
      </p>
    </div>
  );
}

interface NarrativeMapProps {
  onSelectNarrative?: (id: string, label: string | null) => void;
}

export default function NarrativeMap({
  onSelectNarrative,
}: NarrativeMapProps) {
  const [narratives, setNarratives] = useState<Narrative[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchNarratives()
      .then(setNarratives)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <div className="rounded border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
          Narrative Map
        </h2>
        <span className="text-xs font-mono text-text-muted">
          {narratives.length} narratives
        </span>
      </div>

      {error && (
        <p className="text-danger text-xs font-mono mb-2">{error}</p>
      )}

      {narratives.length === 0 && !error ? (
        <div className="h-64 flex items-center justify-center text-text-muted text-sm">
          No narrative data available
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#1e1e2e"
              vertical={false}
            />
            <XAxis
              type="number"
              dataKey="platform_spread"
              name="Platform Spread"
              tick={{ fill: "#71717a", fontSize: 11, fontFamily: "monospace" }}
              axisLine={{ stroke: "#1e1e2e" }}
              tickLine={false}
              label={{
                value: "Platform Spread",
                position: "bottom",
                fill: "#71717a",
                fontSize: 11,
                fontFamily: "monospace",
              }}
            />
            <YAxis
              type="number"
              dataKey="post_count"
              name="Post Count"
              tick={{ fill: "#71717a", fontSize: 11, fontFamily: "monospace" }}
              axisLine={{ stroke: "#1e1e2e" }}
              tickLine={false}
              label={{
                value: "Post Count",
                angle: -90,
                position: "insideLeft",
                fill: "#71717a",
                fontSize: 11,
                fontFamily: "monospace",
              }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Scatter
              data={narratives.map((n) => ({
                ...n,
                z: n.post_count,
              }))}
              onClick={(entry) => {
                if (onSelectNarrative && entry) {
                  const n = entry.payload as Narrative & {
                    cx?: number;
                    cy?: number;
                  };
                  onSelectNarrative(n.id, n.label);
                }
              }}
              style={{ cursor: onSelectNarrative ? "pointer" : "default" }}
            >
              {narratives.map((n, i) => (
                <Cell
                  key={i}
                  fill={statusColor(n.status)}
                  fillOpacity={0.8}
                  r={Math.max(6, Math.min(30, Math.sqrt(n.post_count) * 3))}
                  style={{ cursor: onSelectNarrative ? "pointer" : "default" }}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
