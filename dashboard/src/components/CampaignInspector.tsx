"use client";

import { useEffect, useState, useCallback, useMemo, useRef, type ReactNode } from "react";
import { AlertTriangle, X } from "lucide-react";
import {
  fetchCampaignInspect,
  type CampaignInspectData,
  type CopypastaPhrase,
} from "@/lib/api";

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
  rss: "#22c55e",
};

function platformColor(platform: string): string {
  return PLATFORM_COLORS[platform.toLowerCase()] || "#71717a";
}

function highlightCopypasta(content: string, phrases: CopypastaPhrase[]): ReactNode {
  if (phrases.length === 0) return content;

  const sorted = [...phrases].sort((a, b) => b.phrase.length - a.phrase.length);
  const pattern = sorted.map((p) => p.phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const regex = new RegExp(`(${pattern})`, "gi");
  const parts = content.split(regex);

  return parts.map((part, i) => {
    const isMatch = sorted.some((p) => p.phrase.toLowerCase() === part.toLowerCase());
    if (isMatch) {
      return (
        <mark key={i} className="bg-danger/30 text-text-primary rounded px-0.5">
          {part}
        </mark>
      );
    }
    return part;
  });
}

function identityColor(ratio: number): string {
  if (ratio > 0.7) return "#ef4444";
  if (ratio > 0.4) return "#f59e0b";
  return "#22c55e";
}

interface CampaignInspectorProps {
  campaignId: string | null;
  projectId: string;
  onClose: () => void;
}

export default function CampaignInspector({ campaignId, projectId, onClose }: CampaignInspectorProps) {
  const [data, setData] = useState<CampaignInspectData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const loadRequestId = useRef(0);

  const load = useCallback(() => {
    if (!campaignId) return;
    // Switching campaigns quickly can resolve responses out of order; only
    // the most recently issued request may apply its result.
    const request = ++loadRequestId.current;
    setError(null);
    fetchCampaignInspect(campaignId, projectId)
      .then((result) => {
        if (loadRequestId.current !== request) return;
        setData(result);
      })
      .catch((err) => {
        if (loadRequestId.current !== request) return;
        setError(err.message);
      });
  }, [campaignId, projectId]);

  useEffect(() => {
    if (!campaignId) {
      loadRequestId.current++; // invalidate any in-flight load
      setData(null);
      setError(null);
      return;
    }
    load();
  }, [campaignId, load]);

  useEffect(() => {
    if (!campaignId) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [campaignId, onClose]);

  const isOpen = campaignId !== null;

  const contentVariants = useMemo(() => {
    if (!data) return [] as Array<[string, number]>;
    // Single pass with a Map: filtering all posts per post (the previous
    // approach) was O(n^2) string comparisons recomputed on every render.
    const counts = new Map<string, number>();
    for (const post of data.posts) {
      counts.set(post.content, (counts.get(post.content) ?? 0) + 1);
    }
    return Array.from(counts.entries());
  }, [data]);

  return (
    <>
      <div
        className={`fixed inset-0 z-50 transition-opacity duration-300 ${
          isOpen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
      >
        <div className="absolute inset-0 bg-black/50" onClick={onClose} />
        <div
          ref={panelRef}
          className={`absolute right-0 top-0 h-full w-full max-w-[600px] bg-surface-card border-l border-surface-border transform transition-transform duration-300 ease-in-out flex flex-col ${
            isOpen ? "translate-x-0" : "translate-x-full"
          }`}
        >
          <div className="flex items-center justify-between px-5 py-4 border-b border-surface-border shrink-0">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
                Campaign Inspector
              </h2>
              <p className="text-xs font-mono text-text-primary mt-0.5 truncate">
                {data?.campaign_label || campaignId?.slice(0, 8) || "—"}
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded hover:bg-surface-border/60 transition-colors text-text-muted hover:text-text-primary shrink-0"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-0">
            {error && (
              <p className="text-danger text-xs font-mono">{error}</p>
            )}

            {!data && !error && isOpen && (
              <div className="space-y-4 animate-pulse">
                <div className="h-32 rounded-lg bg-surface-border/40" />
                <div className="h-20 rounded bg-surface-border/40" />
                <div className="h-20 rounded bg-surface-border/40" />
                <div className="h-40 rounded bg-surface-border/40" />
              </div>
            )}

            {data && (
              <>
                <div className="rounded-lg border border-danger/30 bg-danger/5 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="w-5 h-5 text-danger" />
                    <h3 className="text-sm font-semibold uppercase tracking-wider text-danger">
                      Case for Coordination
                    </h3>
                  </div>
                  <p className="text-text-primary font-mono text-sm leading-relaxed">
                    {data.evidence_summary}
                  </p>
                  <div className="grid grid-cols-4 gap-3 mt-4">
                    <div className="rounded bg-surface-card border border-surface-border p-2 text-center">
                      <div
                        className="text-lg font-mono font-semibold"
                        style={{ color: identityColor(data.identity_ratio) }}
                      >
                        {(data.identity_ratio * 100).toFixed(0)}%
                      </div>
                      <div className="text-[10px] font-mono text-text-muted uppercase">
                        Identity
                      </div>
                    </div>
                    <div className="rounded bg-surface-card border border-surface-border p-2 text-center">
                      <div className="text-lg font-mono font-semibold text-text-primary">
                        {data.unique_authors}
                      </div>
                      <div className="text-[10px] font-mono text-text-muted uppercase">
                        Authors
                      </div>
                    </div>
                    <div className="rounded bg-surface-card border border-surface-border p-2 text-center">
                      <div className="text-lg font-mono font-semibold text-text-primary">
                        {data.unique_platforms}
                      </div>
                      <div className="text-[10px] font-mono text-text-muted uppercase">
                        Platforms
                      </div>
                    </div>
                    <div className="rounded bg-surface-card border border-surface-border p-2 text-center">
                      <div className="text-lg font-mono font-semibold text-text-primary">
                        {data.time_span_minutes?.toFixed(0) ?? "—"}
                      </div>
                      <div className="text-[10px] font-mono text-text-muted uppercase">
                        Minutes
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-6">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-text-muted mb-3">
                    Lexical Heatmap
                  </h3>
                  <div className="space-y-2">
                    {data.copypasta_phrases.map((phrase, i) => (
                      <div
                        key={i}
                        className="rounded border border-surface-border bg-surface-card p-3"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-mono text-text-muted">
                            {phrase.count} posts · {phrase.unique_authors} authors ·{" "}
                            {phrase.percentage}%
                          </span>
                          <div className="w-16 h-1.5 rounded-full bg-surface-border overflow-hidden">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${phrase.percentage}%`,
                                backgroundColor:
                                  phrase.percentage > 80
                                    ? "#ef4444"
                                    : phrase.percentage > 50
                                      ? "#f59e0b"
                                      : "#3b82f6",
                              }}
                            />
                          </div>
                        </div>
                        <code className="text-xs font-mono text-text-primary bg-surface-bg rounded px-1.5 py-0.5">
                          &quot;{phrase.phrase}&quot;
                        </code>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="mt-6">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-text-muted mb-3">
                    Content Variants
                  </h3>
                  {contentVariants.map(([content, count], i) => (
                    <div
                      key={i}
                      className="rounded border border-surface-border bg-surface-card p-3 mb-2"
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-xs font-mono text-danger font-semibold">
                          {count}×
                        </span>
                        <span className="text-xs font-mono text-text-muted">
                          identical posts
                        </span>
                      </div>
                      <div className="text-xs font-mono text-text-primary leading-relaxed">
                        {highlightCopypasta(content, data.copypasta_phrases)}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="mt-6">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-text-muted mb-3">
                    Platform Bleed Timeline
                  </h3>
                  <div className="relative ml-4">
                    <div className="absolute left-0 top-0 bottom-0 w-px bg-surface-border" />
                    {data.platform_bleed.map((step, i) => {
                      const isFirst = i === 0;
                      const pc = platformColor(step.platform);
                      return (
                        <div key={i} className="relative pl-6 pb-4 last:pb-0">
                          <div
                            className="absolute left-0 top-1 w-2 h-2 rounded-full -translate-x-[3.5px]"
                            style={{ backgroundColor: pc }}
                          />
                          <div className="flex items-start gap-3">
                            <div>
                              <div className="flex items-center gap-2">
                                <span
                                  className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono uppercase"
                                  style={{
                                    backgroundColor: `${pc}20`,
                                    color: pc,
                                  }}
                                >
                                  {step.platform}
                                </span>
                                {step.delay_minutes !== null && !isFirst && (
                                  <span className="text-[10px] font-mono text-text-muted">
                                    +{step.delay_minutes} min
                                  </span>
                                )}
                                {isFirst && (
                                  <span className="text-[10px] font-mono text-text-muted">
                                    origin
                                  </span>
                                )}
                              </div>
                              <div className="text-xs font-mono text-text-muted mt-1">
                                {step.post_count} posts · {step.unique_authors} authors ·{" "}
                                {new Date(step.first_seen).toLocaleTimeString("en-US", {
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="mt-6 pb-4">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-text-muted mb-3">
                    Flagged Posts ({data.total_posts})
                  </h3>
                  <div className="space-y-1 max-h-64 overflow-y-auto">
                    {data.posts.map((post) => {
                      const pc = platformColor(post.source);
                      return (
                        <div
                          key={post.id}
                          className="flex items-center gap-3 px-3 py-2 rounded hover:bg-surface-border/40 transition-colors"
                        >
                          <span
                            className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono uppercase shrink-0"
                            style={{
                              backgroundColor: `${pc}15`,
                              color: pc,
                            }}
                          >
                            {post.source}
                          </span>
                          <span className="text-xs font-mono text-text-primary truncate flex-1">
                            {post.author_handle || post.author_id.slice(0, 8)}
                          </span>
                          <span className="text-[10px] font-mono text-text-muted shrink-0">
                            {post.composite_score !== null
                              ? `${(post.composite_score * 100).toFixed(0)}%`
                              : "—"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
