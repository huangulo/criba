"use client";

import { useEffect, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import {
  fetchNotificationSettings,
  updateNotificationSettings,
  testAlertConnection,
  type NotificationSettings,
  type TestAlertResult,
} from "@/lib/api";

interface ChannelSectionProps {
  title: string;
  icon: ReactNode;
  fields: Array<{
    key: string;
    label: string;
    type: "text" | "password";
    placeholder: string;
  }>;
  channel: "slack" | "discord" | "telegram";
  settings: NotificationSettings;
  onChange: (key: string, value: string) => void;
  onTest: (channel: "slack" | "discord" | "telegram") => void;
  testing: string | null;
  testResult: TestAlertResult | null;
}

function ChannelSection({
  title,
  icon,
  fields,
  channel,
  settings,
  onChange,
  onTest,
  testing,
  testResult,
}: ChannelSectionProps) {
  return (
    <div className="px-5 py-4 border-b border-surface-border">
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          {title}
        </h3>
      </div>
      {fields.map((field) => (
        <div key={field.key} className="mb-3">
          <label className="block text-[10px] font-mono text-text-muted uppercase mb-1">
            {field.label}
          </label>
          <input
            type={field.type}
            value={settings[field.key as keyof NotificationSettings] as string}
            onChange={(e) => onChange(field.key, e.target.value)}
            placeholder={field.placeholder}
            className="w-full rounded border border-surface-border bg-surface-bg px-3 py-2 text-xs font-mono text-text-primary placeholder:text-text-muted/40 focus:outline-none focus:border-info"
          />
        </div>
      ))}
      <button
        onClick={() => onTest(channel)}
        disabled={testing === channel}
        className="text-xs font-mono px-3 py-1.5 rounded border border-surface-border bg-surface-bg hover:bg-surface-border transition-colors text-text-muted hover:text-text-primary disabled:opacity-50"
      >
        {testing === channel ? "Testing..." : "Test Connection"}
      </button>
      {testResult && testResult.channel === channel && (
        <span
          className={`ml-2 text-xs font-mono ${testResult.success ? "text-safe" : "text-danger"}`}
        >
          {testResult.success ? "\u2713 Connected" : `\u2717 ${testResult.error || "Failed"}`}
        </span>
      )}
    </div>
  );
}

interface AlertSettingsProps {
  open: boolean;
  onClose: () => void;
}

export default function AlertSettings({ open, onClose }: AlertSettingsProps) {
  const [settings, setSettings] = useState<NotificationSettings>({
    slack_webhook_url: "",
    discord_webhook_url: "",
    telegram_bot_token: "",
    telegram_chat_id: "",
    confidence_threshold: 0.85,
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestAlertResult | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (open) {
      fetchNotificationSettings().then(setSettings).catch(() => {});
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const handleChange = (key: string, value: string | number) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  const handleSave = () => {
    setSaving(true);
    updateNotificationSettings(settings)
      .then((updated) => {
        setSettings(updated);
        setSaved(true);
        setSaving(false);
      })
      .catch(() => setSaving(false));
  };

  const handleTest = (channel: "slack" | "discord" | "telegram") => {
    setTesting(channel);
    setTestResult(null);
    testAlertConnection(channel)
      .then((result) => {
        setTestResult(result);
        setTesting(null);
      })
      .catch((err) => {
        setTestResult({ channel, success: false, error: err.message });
        setTesting(null);
      });
  };

  return (
    <div
      className={`fixed inset-0 z-50 transition-opacity duration-300 ${
        open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
      }`}
    >
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div
        className={`absolute right-0 top-0 h-full w-full max-w-[480px] bg-surface-card border-l border-surface-border transform transition-transform duration-300 ease-in-out flex flex-col ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-border shrink-0">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
              Alert Settings
            </h2>
            <p className="text-xs font-mono text-text-muted mt-0.5">
              Configure notification channels
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-surface-border/60 transition-colors text-text-muted"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="px-5 py-4 border-b border-surface-border">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-3">
              Alert Threshold
            </h3>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min="0.5"
                max="1.0"
                step="0.05"
                value={settings.confidence_threshold}
                onChange={(e) =>
                  handleChange("confidence_threshold", parseFloat(e.target.value))
                }
                className="flex-1 accent-info"
              />
              <span className="text-sm font-mono text-text-primary w-12 text-right">
                {Math.round(settings.confidence_threshold * 100)}%
              </span>
            </div>
            <p className="text-[10px] font-mono text-text-muted mt-1">
              Alert when campaign confidence exceeds this threshold
            </p>
          </div>

          <ChannelSection
            title="Slack"
            icon={
              <span className="inline-flex items-center justify-center w-4 h-4 rounded text-[9px] font-bold bg-[#4a154b] text-white">
                S
              </span>
            }
            fields={[
              {
                key: "slack_webhook_url",
                label: "Webhook URL",
                type: "text",
                placeholder: "https://hooks.slack.com/services/...",
              },
            ]}
            channel="slack"
            settings={settings}
            onChange={(key, value) => handleChange(key, value)}
            onTest={handleTest}
            testing={testing}
            testResult={testResult}
          />

          <ChannelSection
            title="Discord"
            icon={
              <span className="inline-flex items-center justify-center w-4 h-4 rounded text-[9px] font-bold bg-[#5865f2] text-white">
                D
              </span>
            }
            fields={[
              {
                key: "discord_webhook_url",
                label: "Webhook URL",
                type: "text",
                placeholder: "https://discord.com/api/webhooks/...",
              },
            ]}
            channel="discord"
            settings={settings}
            onChange={(key, value) => handleChange(key, value)}
            onTest={handleTest}
            testing={testing}
            testResult={testResult}
          />

          <ChannelSection
            title="Telegram"
            icon={
              <span className="inline-flex items-center justify-center w-4 h-4 rounded text-[9px] font-bold bg-[#0088cc] text-white">
                T
              </span>
            }
            fields={[
              {
                key: "telegram_bot_token",
                label: "Bot Token",
                type: "password",
                placeholder: "123456:ABC-DEF...",
              },
              {
                key: "telegram_chat_id",
                label: "Chat ID",
                type: "text",
                placeholder: "-1001234567890",
              },
            ]}
            channel="telegram"
            settings={settings}
            onChange={(key, value) => handleChange(key, value)}
            onTest={handleTest}
            testing={testing}
            testResult={testResult}
          />
        </div>

        <div className="px-5 py-4 border-t border-surface-border shrink-0">
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full rounded bg-info px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white hover:bg-info/80 transition-colors disabled:opacity-50"
          >
            {saving ? "Saving..." : saved ? "\u2713 Saved" : "Save Settings"}
          </button>
        </div>
      </div>
    </div>
  );
}
