"use client";

import { useState } from "react";
import { Settings } from "lucide-react";
import StatsSummary from "@/components/StatsSummary";
import NarrativeMap from "@/components/NarrativeMap";
import CampaignList from "@/components/CampaignList";
import LiveAlerts from "@/components/LiveAlerts";
import NetworkGraph from "@/components/NetworkGraph";
import CampaignInspector from "@/components/CampaignInspector";
import AlertSettings from "@/components/AlertSettings";

export default function Home() {
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
          </div>
          <div className="flex items-center gap-2">
            <LiveAlerts />
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
        <StatsSummary />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <NarrativeMap onSelectNarrative={handleSelectNarrative} />
          <CampaignList onSelectCampaign={setSelectedCampaignId} />
        </div>
        <NetworkGraph
          narrativeId={selectedNarrativeId}
          narrativeLabel={selectedNarrativeLabel}
        />
      </div>
      <CampaignInspector
        campaignId={selectedCampaignId}
        onClose={() => setSelectedCampaignId(null)}
      />
      <AlertSettings open={alertSettingsOpen} onClose={() => setAlertSettingsOpen(false)} />
    </main>
  );
}
