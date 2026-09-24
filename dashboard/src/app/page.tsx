"use client";

import { useState, useEffect } from "react";
import { Settings, Radio, FolderKanban, Tag } from "lucide-react";
import StatsSummary from "@/components/StatsSummary";
import NarrativeMap from "@/components/NarrativeMap";
import CampaignList from "@/components/CampaignList";
import LiveAlerts from "@/components/LiveAlerts";
import NetworkGraph from "@/components/NetworkGraph";
import CampaignInspector from "@/components/CampaignInspector";
import AlertSettings from "@/components/AlertSettings";
import IngestionLog from "@/components/IngestionLog";
import ProjectConsole from "@/components/ProjectConsole";
import LabelingPanel from "@/components/LabelingPanel";
import { fetchProjects, type Project } from "@/lib/api";

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [selectedNarrativeId, setSelectedNarrativeId] = useState<string | null>(
    null,
  );
  const [selectedNarrativeLabel, setSelectedNarrativeLabel] = useState<
    string | null
  >(null);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(
    null,
  );
  const [alertSettingsOpen, setAlertSettingsOpen] = useState(false);
  const [ingestionLogOpen, setIngestionLogOpen] = useState(false);
  const [projectConsoleOpen, setProjectConsoleOpen] = useState(false);
  const [labelingPanelOpen, setLabelingPanelOpen] = useState(false);

  useEffect(() => {
    fetchProjects().then((data) => {
      setProjects(data);
      if (data.length > 0) {
        setActiveProjectId(data[0].id);
      }
    }).catch(() => {});
  }, []);

  // A narrative or campaign selection belongs to the project it was made
  // in; otherwise the network graph keeps querying the old narrative
  // against the new project. Adjusted during render (the React-documented
  // pattern for resetting state on prop change) rather than in an effect,
  // which would cascade an extra render.
  const [selectionProjectId, setSelectionProjectId] = useState(activeProjectId);
  if (activeProjectId !== selectionProjectId) {
    setSelectionProjectId(activeProjectId);
    setSelectedNarrativeId(null);
    setSelectedNarrativeLabel(null);
    setSelectedCampaignId(null);
  }

  const refreshProjects = () => {
    fetchProjects().then((data) => {
      setProjects(data);
      if (activeProjectId && !data.find((p) => p.id === activeProjectId)) {
        setActiveProjectId(data.length > 0 ? data[0].id : null);
      }
    }).catch(() => {});
  };

  const handleSelectNarrative = (id: string, label: string | null) => {
    setSelectedNarrativeId(id);
    setSelectedNarrativeLabel(label);
  };

  return (
    <main className="min-h-screen bg-[#0a0a0f] text-[#e4e4e7]">
      <header className="border-b border-surface-border px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold tracking-tight">Criba</h1>
            <span className="text-xs text-text-muted font-mono">
              Narrative Intelligence
            </span>
            {projects.length > 0 && activeProjectId && (
              <select
                value={activeProjectId}
                onChange={(e) => setActiveProjectId(e.target.value)}
                className="ml-3 rounded border border-surface-border bg-surface-card px-3 py-1 text-xs font-mono text-text-primary focus:outline-none focus:border-info"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="flex items-center gap-2">
            <LiveAlerts />
            <button
              onClick={() => setIngestionLogOpen(true)}
              className="flex items-center gap-2 px-3 py-1.5 rounded border border-surface-border bg-surface-card hover:bg-surface-border transition-colors text-text-muted hover:text-text-primary"
              title="Raw Ingestion Log"
            >
              <Radio className="w-4 h-4" />
              <span className="text-xs font-mono">Firehose</span>
            </button>
            <button
              onClick={() => setLabelingPanelOpen(true)}
              className="flex items-center gap-2 px-3 py-1.5 rounded border border-surface-border bg-surface-card hover:bg-surface-border transition-colors text-text-muted hover:text-text-primary"
              title="Label Posts for Eval"
            >
              <Tag className="w-4 h-4" />
              <span className="text-xs font-mono">Label</span>
            </button>
            <button
              onClick={() => setProjectConsoleOpen(true)}
              className="flex items-center gap-2 px-3 py-1.5 rounded border border-surface-border bg-surface-card hover:bg-surface-border transition-colors text-text-muted hover:text-text-primary"
              title="Projects & Settings"
            >
              <FolderKanban className="w-4 h-4" />
              <span className="text-xs font-mono">Projects</span>
            </button>
            <button
              onClick={() => setAlertSettingsOpen(true)}
              className="p-2 rounded border border-surface-border bg-surface-card hover:bg-surface-border transition-colors text-text-muted hover:text-text-primary"
              title="Alert Settings"
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      <div className="p-6 space-y-6">
        {activeProjectId ? (
          <>
            <StatsSummary projectId={activeProjectId} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <NarrativeMap projectId={activeProjectId} onSelectNarrative={handleSelectNarrative} />
              <CampaignList projectId={activeProjectId} onSelectCampaign={setSelectedCampaignId} />
            </div>
            <NetworkGraph
              narrativeId={selectedNarrativeId}
              narrativeLabel={selectedNarrativeLabel}
              projectId={activeProjectId}
            />
          </>
        ) : (
          <div className="flex items-center justify-center py-20 text-text-muted text-sm font-mono">
            No projects configured. Create a project in the Projects console to begin monitoring.
          </div>
        )}
      </div>
      <CampaignInspector
        campaignId={selectedCampaignId}
        projectId={activeProjectId ?? ""}
        onClose={() => setSelectedCampaignId(null)}
      />
      <AlertSettings open={alertSettingsOpen} onClose={() => setAlertSettingsOpen(false)} />
      <IngestionLog projectId={activeProjectId ?? ""} open={ingestionLogOpen} onClose={() => setIngestionLogOpen(false)} />
      <ProjectConsole open={projectConsoleOpen} onClose={() => setProjectConsoleOpen(false)} onProjectsChange={refreshProjects} />
      <LabelingPanel projectId={activeProjectId ?? ""} open={labelingPanelOpen} onClose={() => setLabelingPanelOpen(false)} />
    </main>
  );
}
