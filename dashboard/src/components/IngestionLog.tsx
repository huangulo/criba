"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { X, Radio } from "lucide-react";
import {
  fetchIngestionLogs,
  type IngestionLogPost,
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

function scoreColor(score: number | null): string {
  if (score === null) return "#71717a";
  if (score < 0.3) return "#22c55e";
  if (score < 0.5) return "#f59e0b";
  if (score < 0.7) return "#f97316";
  return "#ef4444";
}

interface IngestionLogProps {
  projectId: string;
  open: boolean;
  onClose: () => void;
}

const PLATFORM_OPTIONS = [
  "twitter",
  "telegram",
  "reddit",
  "bluesky",
  "rss",
  "facebook",
  "instagram",
  "tiktok",
];

export default function IngestionLog({ projectId, open, onClose }: IngestionLogProps) {
  const [posts, setPosts] = useState<IngestionLogPost[]>([]);
  const [loading, setLoading] = useState(false);
  const [platformFilter, setPlatformFilter] = useState<string>("");
  const [maxScore, setMaxScore] = useState(0.6);
  const loadRequestId = useRef(0);

  const load = useCallback(() => {
    // Slider drags and filter changes fire many loads in quick succession;
    // responses can resolve out of order, so only the most recently issued
    // request may apply its result.
    const request = ++loadRequestId.current;
    setLoading(true);
    fetchIngestionLogs(projectId, {
      platform: platformFilter || undefined,
      max_score: maxScore,
      limit: 200,
    })
      .then((result) => {
        if (loadRequestId.current !== request) return;
        setPosts(result);
      })
      .catch(() => {
        if (loadRequestId.current !== request) return;
        setPosts([]);
      })
      .finally(() => {
        if (loadRequestId.current === request) setLoading(false);
      });
  }, [projectId, platformFilter, maxScore]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  return (
    <div
      className={`fixed inset-0 z-50 transition-opacity duration-300 ${
        open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
      }`}
    >
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div
        className={`absolute right-0 top-0 h-full w-full max-w-[600px] bg-surface-card border-l border-surface-border transform transition-transform duration-300 ease-in-out flex flex-col ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-border shrink-0">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-info" />
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
                Raw Ingestion Log
              </h2>
              <p className="text-xs font-mono text-text-muted mt-0.5">
                Unflagged posts &amp; baseline noise
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-surface-border/60 transition-colors text-text-muted"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-3 border-b border-surface-border shrink-0">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-[10px] font-mono text-text-muted uppercase">
                Platform
              </label>
              <select
                value={platformFilter}
                onChange={(e) => setPlatformFilter(e.target.value)}
                className="rounded border border-surface-border bg-surface-bg px-2 py-1 text-xs font-mono text-text-primary focus:outline-none focus:border-info"
              >
                <option value="">All</option>
                {PLATFORM_OPTIONS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2 flex-1">
              <label className="text-[10px] font-mono text-text-muted uppercase whitespace-nowrap">
                Max Score
              </label>
              <input
                type="range"
                min="0.1"
                max="1.0"
                step="0.1"
                value={maxScore}
                onChange={(e) => setMaxScore(parseFloat(e.target.value))}
                className="flex-1 accent-info"
              />
              <span className="text-xs font-mono text-text-primary w-10 text-right">
                {Math.round(maxScore * 100)}%
              </span>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="p-5 space-y-3 animate-pulse">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-16 rounded bg-surface-border/40" />
              ))}
            </div>
          )}

          {!loading && posts.length === 0 && open && (
            <div className="px-5 py-8 text-center">
              <p className="text-xs font-mono text-text-muted">
                No posts match current filters
              </p>
            </div>
          )}

          {!loading && posts.map((post) => {
            const pc = platformColor(post.platform);
            return (
              <div
                key={post.id}
                className="px-5 py-3 border-b border-surface-border hover:bg-surface-border/20 transition-colors"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono uppercase"
                    style={{
                      backgroundColor: `${pc}20`,
                      color: pc,
                    }}
                  >
                    {post.platform}
                  </span>
                  <span className="text-xs font-mono text-text-primary truncate">
                    {post.author_handle || "unknown"}
                  </span>
                  {post.composite_score !== null && (
                    <span
                      className="text-[10px] font-mono ml-auto shrink-0"
                      style={{ color: scoreColor(post.composite_score) }}
                    >
                      {(post.composite_score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <p className="text-xs font-mono text-text-muted leading-relaxed">
                  {post.content.length > 150
                    ? `${post.content.slice(0, 150)}...`
                    : post.content}
                </p>
                <p className="text-[10px] font-mono text-text-muted mt-1">
                  {new Date(post.published_at).toLocaleString("en-US", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
