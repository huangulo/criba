"use client";

import { useEffect, useState, useCallback } from "react";
import { X, Sliders, FolderPlus, LayoutGrid, Trash2, Plus } from "lucide-react";
import {
  fetchBaselineSettings,
  updateBaselineSettings,
  fetchProjects,
  createProject,
  deleteProject,
  type BaselineSettings,
  type Project,
} from "@/lib/api";

const PLATFORM_COLORS: Record<string, string> = {
  twitter: "#1da1f2",
  x: "#1da1f2",
  telegram: "#0088cc",
  reddit: "#ff4500",
  bluesky: "#0085ff",
  rss: "#22c55e",
  youtube: "#ff0000",
};

function platformColor(platform: string): string {
  return PLATFORM_COLORS[platform.toLowerCase()] || "#71717a";
}

const PLATFORM_OPTIONS = ["twitter", "telegram", "reddit", "bluesky", "rss", "youtube"];
const TARGET_TYPE_OPTIONS = ["keyword", "handle"];

type Tab = "baseline" | "projects" | "active";

interface PendingTarget {
  platform: string;
  target_type: string;
  value: string;
}

interface ProjectConsoleProps {
  open: boolean;
  onClose: () => void;
  onProjectsChange?: () => void;
}

export default function ProjectConsole({ open, onClose, onProjectsChange }: ProjectConsoleProps) {
  const [activeTab, setActiveTab] = useState<Tab>("baseline");

  const [baseline, setBaseline] = useState<BaselineSettings>({
    heuristic_threshold: 0.6,
    copypasta_threshold: 10,
    temporal_cluster_min: 5,
    new_account_days: 7,
  });
  const [baselineLoading, setBaselineLoading] = useState(false);
  const [baselineSaving, setBaselineSaving] = useState(false);
  const [baselineSaved, setBaselineSaved] = useState(false);

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);

  const [projectName, setProjectName] = useState("");
  const [projectDesc, setProjectDesc] = useState("");
  const [targetPlatform, setTargetPlatform] = useState("twitter");
  const [targetType, setTargetType] = useState("keyword");
  const [targetValue, setTargetValue] = useState("");
  const [pendingTargets, setPendingTargets] = useState<PendingTarget[]>([]);
  const [creating, setCreating] = useState(false);

  const loadBaseline = useCallback(() => {
    setBaselineLoading(true);
    fetchBaselineSettings()
      .then(setBaseline)
      .catch(() => {})
      .finally(() => setBaselineLoading(false));
  }, []);

  const loadProjects = useCallback(() => {
    setProjectsLoading(true);
    fetchProjects()
      .then(setProjects)
      .catch(() => {})
      .finally(() => setProjectsLoading(false));
  }, []);

  useEffect(() => {
    if (open) {
      loadBaseline();
      loadProjects();
    }
  }, [open, loadBaseline, loadProjects]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const handleBaselineChange = (key: keyof BaselineSettings, value: number) => {
    setBaseline((prev) => ({ ...prev, [key]: value }));
    setBaselineSaved(false);
  };

  const handleBaselineSave = () => {
    setBaselineSaving(true);
    updateBaselineSettings(baseline)
      .then((updated) => {
        setBaseline(updated);
        setBaselineSaved(true);
      })
      .catch(() => {})
      .finally(() => setBaselineSaving(false));
  };

  const handleAddTarget = () => {
    if (!targetValue.trim()) return;
    setPendingTargets((prev) => [
      ...prev,
      { platform: targetPlatform, target_type: targetType, value: targetValue.trim() },
    ]);
    setTargetValue("");
  };

  const handleRemoveTarget = (index: number) => {
    setPendingTargets((prev) => prev.filter((_, i) => i !== index));
  };

  const handleCreateProject = () => {
    if (!projectName.trim() || pendingTargets.length === 0) return;
    setCreating(true);
    createProject({
      name: projectName.trim(),
      description: projectDesc.trim() || undefined,
      targets: pendingTargets,
    })
      .then(() => {
        setProjectName("");
        setProjectDesc("");
        setPendingTargets([]);
        loadProjects();
        onProjectsChange?.();
      })
      .catch(() => {})
      .finally(() => setCreating(false));
  };

  const handleDeleteProject = (id: string) => {
    deleteProject(id)
      .then(() => {
        setProjects((prev) => prev.filter((p) => p.id !== id));
        onProjectsChange?.();
      })
      .catch(() => {});
  };

  const tabs: { key: Tab; label: string; icon: typeof Sliders }[] = [
    { key: "baseline", label: "Baseline", icon: Sliders },
    { key: "projects", label: "Projects", icon: FolderPlus },
    { key: "active", label: "Active", icon: LayoutGrid },
  ];

  return (
    <div
      className={`fixed inset-0 z-50 transition-opacity duration-300 ${
        open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
      }`}
    >
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div
        className={`absolute right-0 top-0 h-full w-full max-w-[640px] bg-surface-card border-l border-surface-border transform transition-transform duration-300 ease-in-out flex flex-col ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-border shrink-0">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
              Projects &amp; Settings
            </h2>
            <p className="text-xs font-mono text-text-muted mt-0.5">
              Baseline thresholds &amp; project management
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-surface-border/60 transition-colors text-text-muted"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex items-center gap-1 px-5 py-3 border-b border-surface-border shrink-0">
          {tabs.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono transition-colors ${
                activeTab === key
                  ? "bg-surface-border text-text-primary"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto">
          {activeTab === "baseline" && (
            <div className="px-5 py-4 space-y-5">
              {baselineLoading ? (
                <div className="space-y-4 animate-pulse">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="h-14 rounded bg-surface-border/40" />
                  ))}
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
                      Heuristic Threshold
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={baseline.heuristic_threshold}
                        onChange={(e) =>
                          handleBaselineChange("heuristic_threshold", parseFloat(e.target.value))
                        }
                        className="flex-1 accent-info"
                      />
                      <span className="text-sm font-mono text-text-primary w-14 text-right">
                        {Math.round(baseline.heuristic_threshold * 100)}%
                      </span>
                    </div>
                    <p className="text-[10px] font-mono text-text-muted mt-1">
                      Composite score above this triggers LLM analysis
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
                      Copypasta Threshold
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min="1"
                        max="50"
                        step="1"
                        value={baseline.copypasta_threshold}
                        onChange={(e) =>
                          handleBaselineChange("copypasta_threshold", parseInt(e.target.value))
                        }
                        className="flex-1 accent-info"
                      />
                      <span className="text-sm font-mono text-text-primary w-10 text-right">
                        {baseline.copypasta_threshold}
                      </span>
                    </div>
                    <p className="text-[10px] font-mono text-text-muted mt-1">
                      Flag if this many similar posts appear in 72h
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
                      Temporal Cluster Min
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min="1"
                        max="20"
                        step="1"
                        value={baseline.temporal_cluster_min}
                        onChange={(e) =>
                          handleBaselineChange("temporal_cluster_min", parseInt(e.target.value))
                        }
                        className="flex-1 accent-info"
                      />
                      <span className="text-sm font-mono text-text-primary w-10 text-right">
                        {baseline.temporal_cluster_min}
                      </span>
                    </div>
                    <p className="text-[10px] font-mono text-text-muted mt-1">
                      Minimum posts in an anomalous time window to flag
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
                      New Account Days
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min="1"
                        max="90"
                        step="1"
                        value={baseline.new_account_days}
                        onChange={(e) =>
                          handleBaselineChange("new_account_days", parseInt(e.target.value))
                        }
                        className="flex-1 accent-info"
                      />
                      <span className="text-sm font-mono text-text-primary w-10 text-right">
                        {baseline.new_account_days}
                      </span>
                    </div>
                    <p className="text-[10px] font-mono text-text-muted mt-1">
                      Flag accounts younger than this many days
                    </p>
                  </div>
                </>
              )}
            </div>
          )}

          {activeTab === "projects" && (
            <div className="px-5 py-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-text-muted mb-1">
                  Project Name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. Election Monitor 2026"
                  className="w-full rounded border border-surface-border bg-surface-bg px-3 py-2 text-xs font-mono text-text-primary placeholder:text-text-muted/40 focus:outline-none focus:border-info"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-text-muted mb-1">
                  Description
                </label>
                <input
                  type="text"
                  value={projectDesc}
                  onChange={(e) => setProjectDesc(e.target.value)}
                  placeholder="Optional description"
                  className="w-full rounded border border-surface-border bg-surface-bg px-3 py-2 text-xs font-mono text-text-primary placeholder:text-text-muted/40 focus:outline-none focus:border-info"
                />
              </div>

              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <label className="block text-[10px] font-mono text-text-muted uppercase mb-1">
                    Platform
                  </label>
                  <select
                    value={targetPlatform}
                    onChange={(e) => setTargetPlatform(e.target.value)}
                    className="w-full rounded border border-surface-border bg-surface-bg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-info"
                  >
                    {PLATFORM_OPTIONS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex-1">
                  <label className="block text-[10px] font-mono text-text-muted uppercase mb-1">
                    Target Type
                  </label>
                  <select
                    value={targetType}
                    onChange={(e) => setTargetType(e.target.value)}
                    className="w-full rounded border border-surface-border bg-surface-bg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-info"
                  >
                    {TARGET_TYPE_OPTIONS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex-[2]">
                  <label className="block text-[10px] font-mono text-text-muted uppercase mb-1">
                    Value
                  </label>
                  <input
                    type="text"
                    value={targetValue}
                    onChange={(e) => setTargetValue(e.target.value)}
                    placeholder="e.g. @handle or keyword"
                    className="w-full rounded border border-surface-border bg-surface-bg px-3 py-2 text-xs font-mono text-text-primary placeholder:text-text-muted/40 focus:outline-none focus:border-info"
                  />
                </div>
                <button
                  onClick={handleAddTarget}
                  disabled={!targetValue.trim()}
                  className="rounded border border-surface-border bg-surface-card hover:bg-surface-border text-text-muted hover:text-text-primary px-3 py-2 text-xs font-mono transition-colors disabled:opacity-50 shrink-0"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
              </div>

              {pendingTargets.length > 0 && (
                <div className="space-y-1.5">
                  <span className="text-[10px] font-mono text-text-muted uppercase">
                    Targets ({pendingTargets.length})
                  </span>
                  {pendingTargets.map((t, i) => {
                    const pc = platformColor(t.platform);
                    return (
                      <div
                        key={i}
                        className="flex items-center gap-2 rounded border border-surface-border bg-surface-bg px-3 py-2"
                      >
                        <span
                          className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono uppercase shrink-0"
                          style={{
                            backgroundColor: `${pc}20`,
                            color: pc,
                          }}
                        >
                          {t.platform}
                        </span>
                        <span className="text-[10px] font-mono text-text-muted uppercase shrink-0">
                          {t.target_type}
                        </span>
                        <span className="text-xs font-mono text-text-primary truncate flex-1">
                          {t.value}
                        </span>
                        <button
                          onClick={() => handleRemoveTarget(i)}
                          className="text-text-muted hover:text-danger transition-colors shrink-0"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              <button
                onClick={handleCreateProject}
                disabled={creating || !projectName.trim() || pendingTargets.length === 0}
                className="w-full rounded bg-info px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white hover:bg-info/80 transition-colors disabled:opacity-50"
              >
                {creating ? "Creating..." : "Create Project"}
              </button>
            </div>
          )}

          {activeTab === "active" && (
            <div className="px-5 py-4 space-y-3">
              {projectsLoading ? (
                <div className="space-y-3 animate-pulse">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="h-28 rounded-lg bg-surface-border/40" />
                  ))}
                </div>
              ) : projects.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="text-xs font-mono text-text-muted">
                    No projects yet. Create one in the Projects tab.
                  </p>
                </div>
              ) : (
                projects.map((project) => (
                  <div
                    key={project.id}
                    className="rounded-lg border border-surface-border bg-surface-bg p-4"
                  >
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="min-w-0">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-text-primary truncate">
                          {project.name}
                        </h4>
                        {project.description && (
                          <p className="text-[10px] font-mono text-text-muted mt-0.5 truncate">
                            {project.description}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => handleDeleteProject(project.id)}
                        className="text-text-muted hover:text-danger transition-colors shrink-0"
                        title="Delete project"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    {project.targets.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {project.targets.map((target) => {
                          const pc = platformColor(target.platform);
                          return (
                            <span
                              key={target.id}
                              className="inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono border border-surface-border"
                            >
                              <span
                                className="w-1.5 h-1.5 rounded-full shrink-0"
                                style={{ backgroundColor: pc }}
                              />
                              <span className="uppercase text-text-muted">{target.target_type}</span>
                              <span className="text-text-primary">{target.value}</span>
                            </span>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="text-[10px] font-mono text-text-muted">No targets</p>
                    )}
                    <p className="text-[10px] font-mono text-text-muted mt-2">
                      Created {new Date(project.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                    </p>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {activeTab === "baseline" && (
          <div className="px-5 py-4 border-t border-surface-border shrink-0">
            <button
              onClick={handleBaselineSave}
              disabled={baselineSaving}
              className="w-full rounded bg-info px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white hover:bg-info/80 transition-colors disabled:opacity-50"
            >
              {baselineSaving ? "Saving..." : baselineSaved ? "\u2713 Saved" : "Save Changes"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
