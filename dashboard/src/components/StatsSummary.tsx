"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Shield,
  GitBranch,
  Brain,
  Network,
} from "lucide-react";
import { fetchStats } from "@/lib/api";
import type { StatsSummary } from "@/lib/api";

interface StatCardProps {
  icon: React.ReactNode;
  value: number;
  label: string;
  accent: string;
}

function StatCard({ icon, value, label, accent }: StatCardProps) {
  return (
    <div className="flex items-center gap-4 rounded border border-surface-border bg-surface-card px-4 py-3">
      <div
        className="flex items-center justify-center w-10 h-10 rounded-full shrink-0"
        style={{ backgroundColor: `${accent}15` }}
      >
        <div style={{ color: accent }}>{icon}</div>
      </div>
      <div>
        <div className="text-2xl font-mono font-semibold text-text-primary tabular-nums">
          {value.toLocaleString()}
        </div>
        <div className="text-xs text-text-muted uppercase tracking-wide">
          {label}
        </div>
      </div>
    </div>
  );
}

export default function StatsSummary() {
  const [stats, setStats] = useState<StatsSummary | null>(null);

  useEffect(() => {
    fetchStats()
      .then(setStats)
      .catch(() => {});

    const interval = setInterval(() => {
      fetchStats()
        .then(setStats)
        .catch(() => {});
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  if (!stats) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-[76px] rounded border border-surface-border bg-surface-card animate-pulse"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      <StatCard
        icon={<Activity className="w-5 h-5" />}
        value={stats.total_posts}
        label="Total Posts"
        accent="#3b82f6"
      />
      <StatCard
        icon={<AlertTriangle className="w-5 h-5" />}
        value={stats.flagged_posts}
        label="Flagged Posts"
        accent="#f59e0b"
      />
      <StatCard
        icon={<Shield className="w-5 h-5" />}
        value={stats.active_campaigns}
        label="Active Campaigns"
        accent={stats.active_campaigns > 0 ? "#ef4444" : "#22c55e"}
      />
      <StatCard
        icon={<GitBranch className="w-5 h-5" />}
        value={stats.active_narratives}
        label="Active Narratives"
        accent="#3b82f6"
      />
      <StatCard
        icon={<Brain className="w-5 h-5" />}
        value={stats.analyzed_posts}
        label="Analyzed Posts"
        accent="#3b82f6"
      />
      <StatCard
        icon={<Network className="w-5 h-5" />}
        value={stats.clustered_posts}
        label="Clustered Posts"
        accent="#3b82f6"
      />
    </div>
  );
}
