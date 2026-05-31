"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchCampaigns, Campaign } from "@/lib/api";

function confidenceColor(conf: number): string {
  if (conf > 0.7) return "#ef4444";
  if (conf > 0.4) return "#f59e0b";
  return "#22c55e";
}

const PLATFORM_COLORS: Record<string, string> = {
  twitter: "#1da1f2",
  x: "#1da1f2",
  telegram: "#0088cc",
  reddit: "#ff4500",
  facebook: "#1877f2",
  instagram: "#e1306c",
  tiktok: "#ff0050",
  truth_social: "#c19a6b",
  mastodon: "#6364ff",
  bluesky: "#0085ff",
  threads: "#000000",
};

function platformPillColor(platform: string): string {
  return PLATFORM_COLORS[platform.toLowerCase()] || "#71717a";
}

interface CampaignListProps {
  projectId: string;
  onSelectCampaign?: (id: string) => void;
}

export default function CampaignList({ projectId, onSelectCampaign }: CampaignListProps) {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchCampaigns(projectId)
      .then((data) => {
        const sorted = [...data].sort((a, b) => {
          const ca = a.confidence ?? 0;
          const cb = b.confidence ?? 0;
          return cb - ca;
        });
        setCampaigns(sorted);
      })
      .catch((err) => setError(err.message));
  }, [projectId]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <div className="rounded border border-surface-border bg-surface-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
          Campaigns
        </h2>
        <span className="text-xs font-mono text-text-muted">
          {campaigns.length} detected
        </span>
      </div>

      {error && (
        <p className="text-danger text-xs font-mono px-4 py-2">{error}</p>
      )}

      {campaigns.length === 0 && !error ? (
        <div className="px-4 py-12 text-center text-text-muted text-sm">
          No campaigns detected
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border text-left">
                <th className="px-4 py-2.5 text-xs font-mono uppercase text-text-muted tracking-wider font-medium">
                  Label
                </th>
                <th className="px-4 py-2.5 text-xs font-mono uppercase text-text-muted tracking-wider font-medium">
                  Confidence
                </th>
                <th className="px-4 py-2.5 text-xs font-mono uppercase text-text-muted tracking-wider font-medium">
                  Authors
                </th>
                <th className="px-4 py-2.5 text-xs font-mono uppercase text-text-muted tracking-wider font-medium">
                  Posts
                </th>
                <th className="px-4 py-2.5 text-xs font-mono uppercase text-text-muted tracking-wider font-medium">
                  Platforms
                </th>
                <th className="px-4 py-2.5 text-xs font-mono uppercase text-text-muted tracking-wider font-medium">
                  Detected
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {campaigns.map((c) => {
                const conf = c.confidence ?? 0;
                return (
                  <tr
                    key={c.id}
                    className={`hover:bg-surface-border/40 transition-colors ${onSelectCampaign ? "cursor-pointer" : ""}`}
                    onClick={() => onSelectCampaign?.(c.id)}
                  >
                    <td className="px-4 py-3 font-mono text-text-primary">
                      {c.label || c.id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 rounded-full bg-surface-border overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${Math.round(conf * 100)}%`,
                              backgroundColor: confidenceColor(conf),
                            }}
                          />
                        </div>
                        <span
                          className="font-mono text-xs tabular-nums"
                          style={{ color: confidenceColor(conf) }}
                        >
                          {Math.round(conf * 100)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-text-muted tabular-nums">
                      {c.account_count ?? "—"}
                    </td>
                    <td className="px-4 py-3 font-mono text-text-muted tabular-nums">
                      {c.post_count ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {c.platforms?.map((p) => (
                          <span
                            key={p}
                            className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono uppercase"
                            style={{
                              backgroundColor: `${platformPillColor(p)}20`,
                              color: platformPillColor(p),
                            }}
                          >
                            {p}
                          </span>
                        )) ?? <span className="text-text-muted">—</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-text-muted">
                      {new Date(c.detected_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
