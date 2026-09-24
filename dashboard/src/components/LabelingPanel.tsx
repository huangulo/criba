"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { X, Tag, ChevronLeft, ChevronRight, ChevronDown, ChevronRight as CaretRight, User, Copy } from "lucide-react";
import {
  fetchEvalQueue,
  submitEvalLabel,
  fetchEvalEvidence,
  type EvalQueueItem,
  type EvalEvidenceResponse,
} from "@/lib/api";

function scoreBar(value: number, color: string) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 rounded-full bg-surface-border overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${Math.min(value * 100, 100)}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-[10px] font-mono w-8 text-right" style={{ color }}>
        {(value * 100).toFixed(0)}%
      </span>
    </div>
  );
}

const LABEL_COLORS: Record<string, string> = {
  organic: "#22c55e",
  coordinated: "#ef4444",
  uncertain: "#f59e0b",
};

interface LabelingPanelProps {
  projectId: string;
  open: boolean;
  onClose: () => void;
}

export default function LabelingPanel({ projectId, open, onClose }: LabelingPanelProps) {
  const [queue, setQueue] = useState<EvalQueueItem[]>([]);
  const [remaining, setRemaining] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [labeledSession, setLabeledSession] = useState(0);
  const [feedback, setFeedback] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const evidenceCache = useRef<Map<string, EvalEvidenceResponse>>(new Map());
  const loadRequestId = useRef(0);
  const latestEvidencePostId = useRef<string | null>(null);
  const [evidence, setEvidence] = useState<EvalEvidenceResponse | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [showSimilar, setShowSimilar] = useState(false);
  const [showAuthor, setShowAuthor] = useState(false);

  const currentPostId = queue[0]?.post_id;

  const loadQueue = useCallback(async () => {
    if (!projectId) return;
    // Only the most recently issued load may apply its result: rapid
    // re-loads (project switch, refetch near the end of a batch) can
    // resolve out of order, and a stale response must not overwrite
    // the newer queue.
    const request = ++loadRequestId.current;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchEvalQueue(projectId, 25, 0.5);
      if (loadRequestId.current !== request) return;
      setQueue(resp.posts);
      setRemaining(resp.remaining_unlabeled);
    } catch (e) {
      if (loadRequestId.current !== request) return;
      setError(e instanceof Error ? e.message : "Failed to load queue");
    } finally {
      if (loadRequestId.current === request) setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (open) loadQueue();
  }, [open, loadQueue]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const handleLabel = useCallback(
    async (label: "organic" | "coordinated" | "uncertain") => {
      if (queue.length === 0) return;
      const post = queue[0];
      try {
        await submitEvalLabel(post.post_id, label);
        setQueue((prev) => prev.slice(1));
        setLabeledSession((n) => n + 1);
        setRemaining((n) => Math.max(0, n - 1));
        setFeedback(`Labeled: ${label}`);
        setTimeout(() => setFeedback(null), 800);
        if (queue.length <= 2) loadQueue();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to submit label");
      }
    },
    [queue, loadQueue],
  );

  const loadEvidence = useCallback(async (postId: string) => {
    if (evidenceCache.current.has(postId)) {
      setEvidence(evidenceCache.current.get(postId)!);
      return;
    }
    // Guard against fast labeling: a slow fetch for a previous post must
    // not install its evidence under the current one.
    latestEvidencePostId.current = postId;
    setEvidenceLoading(true);
    try {
      const data = await fetchEvalEvidence(postId);
      evidenceCache.current.set(postId, data);
      if (latestEvidencePostId.current !== postId) return;
      setEvidence(data);
    } catch {
      if (latestEvidencePostId.current !== postId) return;
      setEvidence(null);
    } finally {
      if (latestEvidencePostId.current === postId) setEvidenceLoading(false);
    }
  }, []);

  useEffect(() => {
    setShowSimilar(false);
    setShowAuthor(false);
    setEvidence(null);
  }, [currentPostId]);

  useEffect(() => {
    if (currentPostId && (showSimilar || showAuthor) && !evidence && !evidenceLoading) {
      loadEvidence(currentPostId);
    }
  }, [currentPostId, showSimilar, showAuthor, evidence, evidenceLoading, loadEvidence]);

  useEffect(() => {
    if (!open || queue.length === 0) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "1") handleLabel("organic");
      else if (e.key === "2") handleLabel("coordinated");
      else if (e.key === "3") handleLabel("uncertain");
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, queue, handleLabel]);

  const current = queue.length > 0 ? queue[0] : null;

  return (
    <div
      className={`fixed inset-0 z-50 transition-opacity duration-300 ${
        open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
      }`}
    >
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div
        ref={panelRef}
        className={`absolute right-0 top-0 h-full w-full max-w-[600px] bg-surface-card border-l border-surface-border transform transition-transform duration-300 ease-in-out flex flex-col ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-border shrink-0">
          <div className="flex items-center gap-2">
            <Tag className="w-4 h-4 text-warning" />
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
                Label Posts
              </h2>
              <p className="text-xs font-mono text-text-muted mt-0.5">
                Labeled this session: {labeledSession} — Remaining: {remaining}
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

        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="p-5 space-y-3 animate-pulse">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-24 rounded bg-surface-border/40" />
              ))}
            </div>
          )}

          {error && (
            <div className="px-5 py-3 text-xs font-mono text-danger">{error}</div>
          )}

          {!loading && !current && !error && (
            <div className="px-5 py-12 text-center">
              <p className="text-xs font-mono text-text-muted">
                No more unlabeled posts in this project
              </p>
            </div>
          )}

          {!loading && current && (
            <div className="p-5 space-y-4">
              <div className="flex items-center gap-2 mb-1">
                <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-info/20 text-info">
                  {current.source}
                </span>
                <span className="text-xs font-mono text-text-primary">
                  {current.author_handle || "unknown"}
                </span>
                {current.account_age_days !== null && (
                  <span className="text-[10px] font-mono text-text-muted">
                    ({Math.round(current.account_age_days)}d old)
                  </span>
                )}
                {current.account_age_days === null && (
                  <span className="text-[10px] font-mono text-text-muted">(age unknown)</span>
                )}
                <span className="text-[10px] font-mono text-text-muted ml-auto">
                  {new Date(current.published_at).toLocaleString("en-US", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>

              <div className="rounded border border-surface-border bg-surface-bg p-3">
                <p className="text-xs font-mono text-text-primary leading-relaxed whitespace-pre-wrap">
                  {current.content}
                </p>
              </div>

              <div className="space-y-1.5 rounded border border-surface-border bg-surface-bg p-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono text-text-muted uppercase">Copypasta</span>
                  {scoreBar(current.copypasta_score, current.copypasta_score > 0.5 ? "#ef4444" : "#22c55e")}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono text-text-muted uppercase">Temporal</span>
                  {scoreBar(current.temporal_anomaly, current.temporal_anomaly > 0.5 ? "#ef4444" : "#22c55e")}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono text-text-muted uppercase">Account Age</span>
                  {scoreBar(current.account_age_flag, current.account_age_flag > 0.5 ? "#ef4444" : "#22c55e")}
                </div>
                <div className="border-t border-surface-border my-1" />
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono text-text-muted uppercase font-bold">Composite</span>
                  {scoreBar(current.composite_score, current.composite_score > 0.6 ? "#ef4444" : "#f59e0b")}
                </div>
              </div>

              <div className="space-y-1">
                <button
                  onClick={() => setShowSimilar(!showSimilar)}
                  className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-[10px] font-mono uppercase tracking-wider text-text-muted hover:bg-surface-border/40 transition-colors"
                >
                  <Copy className="w-3 h-3" />
                  {showSimilar ? <ChevronDown className="w-3 h-3" /> : <CaretRight className="w-3 h-3" />}
                  Similar posts{evidence ? ` (${evidence.similar_posts.length})` : ""}
                </button>
                {showSimilar && (
                  <div className="ml-4 space-y-1.5">
                    {evidenceLoading && <div className="text-[10px] font-mono text-text-muted animate-pulse">Loading...</div>}
                    {!evidenceLoading && evidence && evidence.similar_posts.length === 0 && (
                      <div className="text-[10px] font-mono text-text-muted">No similar posts found (score may be from diffuse matches)</div>
                    )}
                    {evidence?.similar_posts.map((sp) => (
                      <div key={sp.post_id} className="rounded border border-surface-border bg-surface-bg p-2 space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <span className="inline-block px-1 py-0.5 rounded text-[9px] font-mono uppercase bg-info/20 text-info">{sp.source}</span>
                          <span className="text-[10px] font-mono text-text-primary">{sp.author_handle || "unknown"}</span>
                          <span className="text-[9px] font-mono ml-auto" style={{ color: sp.similarity >= 0.7 ? "#ef4444" : "#f59e0b" }}>
                            {(sp.similarity * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="text-[10px] font-mono text-text-muted leading-relaxed">{sp.content.length > 120 ? `${sp.content.slice(0, 120)}...` : sp.content}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-1">
                <button
                  onClick={() => setShowAuthor(!showAuthor)}
                  className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-[10px] font-mono uppercase tracking-wider text-text-muted hover:bg-surface-border/40 transition-colors"
                >
                  <User className="w-3 h-3" />
                  {showAuthor ? <ChevronDown className="w-3 h-3" /> : <CaretRight className="w-3 h-3" />}
                  This author{evidence ? ` (${evidence.author_stats.total_posts_in_project} posts)` : ""}
                </button>
                {showAuthor && (
                  <div className="ml-4 space-y-1.5">
                    {evidenceLoading && <div className="text-[10px] font-mono text-text-muted animate-pulse">Loading...</div>}
                    {evidence && (
                      <>
                        <div className="rounded border border-surface-border bg-surface-bg p-2 space-y-0.5">
                          <div className="flex items-center gap-2 text-[10px] font-mono text-text-muted">
                            <span>{evidence.author_stats.author_handle || "unknown"}</span>
                            {evidence.author_stats.account_age_days !== null && (
                              <span>({Math.round(evidence.author_stats.account_age_days)}d old)</span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 text-[9px] font-mono text-text-muted">
                            <span>{evidence.author_stats.total_posts_in_project} posts</span>
                            {evidence.author_stats.first_seen && (
                              <span>first {new Date(evidence.author_stats.first_seen).toLocaleDateString()}</span>
                            )}
                            {evidence.author_stats.last_seen && (
                              <span>last {new Date(evidence.author_stats.last_seen).toLocaleDateString()}</span>
                            )}
                          </div>
                          {evidence.author_stats.distinct_sources.length > 0 && (
                            <div className="flex items-center gap-1 flex-wrap">
                              {evidence.author_stats.distinct_sources.map((s) => (
                                <span key={s} className="px-1 py-0.5 rounded text-[9px] font-mono bg-info/10 text-info">{s}</span>
                              ))}
                            </div>
                          )}
                        </div>
                        {evidence.author_recent_posts.map((ap) => (
                          <div key={ap.post_id} className="rounded border border-surface-border bg-surface-bg p-2 space-y-0.5">
                            <div className="flex items-center gap-1.5">
                              <span className="inline-block px-1 py-0.5 rounded text-[9px] font-mono uppercase bg-info/20 text-info">{ap.source}</span>
                              <span className="text-[9px] font-mono text-text-muted">{new Date(ap.published_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                              {ap.composite_score !== null && (
                                <span className="text-[9px] font-mono ml-auto" style={{ color: ap.composite_score > 0.6 ? "#ef4444" : "#71717a" }}>
                                  {(ap.composite_score * 100).toFixed(0)}%
                                </span>
                              )}
                            </div>
                            <p className="text-[10px] font-mono text-text-muted leading-relaxed">{ap.content.length > 120 ? `${ap.content.slice(0, 120)}...` : ap.content}</p>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <div className="flex gap-2">
                  <button
                    onClick={() => handleLabel("organic")}
                    className="flex-1 py-2 rounded border text-xs font-mono uppercase tracking-wider transition-colors"
                    style={{
                      borderColor: LABEL_COLORS.organic,
                      color: LABEL_COLORS.organic,
                      backgroundColor: "transparent",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = `${LABEL_COLORS.organic}20`)}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                  >
                    Organic (1)
                  </button>
                  <button
                    onClick={() => handleLabel("coordinated")}
                    className="flex-1 py-2 rounded border text-xs font-mono uppercase tracking-wider transition-colors"
                    style={{
                      borderColor: LABEL_COLORS.coordinated,
                      color: LABEL_COLORS.coordinated,
                      backgroundColor: "transparent",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = `${LABEL_COLORS.coordinated}20`)}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                  >
                    Coordinated (2)
                  </button>
                  <button
                    onClick={() => handleLabel("uncertain")}
                    className="flex-1 py-2 rounded border text-xs font-mono uppercase tracking-wider transition-colors"
                    style={{
                      borderColor: LABEL_COLORS.uncertain,
                      color: LABEL_COLORS.uncertain,
                      backgroundColor: "transparent",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = `${LABEL_COLORS.uncertain}20`)}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                  >
                    Uncertain (3)
                  </button>
                </div>
                <p className="text-[10px] font-mono text-text-muted text-center leading-relaxed">
                  Judge coordination, not opinion: high copypasta / temporal / new-account signals = likely coordinated. A strongly partisan but normal post is organic.
                </p>
              </div>

              {feedback && (
                <div className="text-center text-xs font-mono text-safe animate-pulse">
                  {feedback}
                </div>
              )}

              {queue.length > 1 && (
                <div className="flex items-center justify-between pt-2 border-t border-surface-border">
                  <span className="text-[10px] font-mono text-text-muted">
                    {queue.length - 1} remaining in batch
                  </span>
                  <div className="flex gap-1">
                    <ChevronLeft className="w-3 h-3 text-text-muted" />
                    <span className="text-[10px] font-mono text-text-muted">navigating via labels</span>
                    <ChevronRight className="w-3 h-3 text-text-muted" />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
