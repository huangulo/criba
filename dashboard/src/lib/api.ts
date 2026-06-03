const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8030";

export interface Narrative {
  id: string;
  label: string | null;
  post_count: number;
  platform_spread: number;
  status: string;
  first_seen: string | null;
  last_seen: string | null;
}

export interface Campaign {
  id: string;
  label: string | null;
  confidence: number | null;
  account_count: number | null;
  post_count: number | null;
  platforms: string[] | null;
  status: string;
  detected_at: string;
}

export interface FlaggedPost {
  id: string;
  content: string;
  source: string;
  author_handle: string | null;
  published_at: string;
  anomaly_score: number;
  narrative_category: string | null;
  coordination_probability: number | null;
  recommended_action: string | null;
}

export interface StatsSummary {
  total_posts: number;
  flagged_posts: number;
  analyzed_posts: number;
  active_narratives: number;
  active_campaigns: number;
  clustered_posts: number;
}

export interface AlertMessage {
  event_type: string;
  message: string;
  data: Record<string, unknown>;
}

export async function fetchNarratives(projectId: string): Promise<Narrative[]> {
  const res = await fetch(`${API_BASE}/api/narratives?project_id=${projectId}`);
  if (!res.ok) throw new Error("Failed to fetch narratives");
  return res.json();
}

export async function fetchCampaigns(projectId: string): Promise<Campaign[]> {
  const res = await fetch(`${API_BASE}/api/campaigns?project_id=${projectId}`);
  if (!res.ok) throw new Error("Failed to fetch campaigns");
  return res.json();
}

export async function fetchFlaggedPosts(projectId: string): Promise<FlaggedPost[]> {
  const res = await fetch(`${API_BASE}/api/posts/flagged?project_id=${projectId}`);
  if (!res.ok) throw new Error("Failed to fetch flagged posts");
  return res.json();
}

export async function fetchStats(projectId: string): Promise<StatsSummary> {
  const res = await fetch(`${API_BASE}/api/stats/summary?project_id=${projectId}`);
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export function getWsUrl(): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}/ws/alerts`;
}

export interface NetworkNode {
  id: string;
  handle: string | null;
  platform: string | null;
  degree: number;
  is_cluster: boolean;
  cluster_id: number | null;
}

export interface NetworkLink {
  source: string;
  target: string;
  interaction: string;
  weight: number;
}

export interface NetworkGraphData {
  narrative_id: string;
  narrative_label: string | null;
  nodes: NetworkNode[];
  links: NetworkLink[];
  clusters: string[][];
  total_authors: number;
  total_interactions: number;
}

export async function fetchNetworkGraph(narrativeId: string, projectId: string): Promise<NetworkGraphData> {
  const res = await fetch(`${API_BASE}/api/network/${narrativeId}?project_id=${projectId}`);
  if (!res.ok) throw new Error("Failed to fetch network graph");
  return res.json();
}

export interface InspectPost {
  id: string;
  source: string;
  author_id: string;
  author_handle: string | null;
  content: string;
  published_at: string;
  composite_score: number | null;
  coordination_probability: number | null;
  narrative_category: string | null;
}

export interface CopypastaPhrase {
  phrase: string;
  count: number;
  unique_authors: number;
  percentage: number;
}

export interface PlatformBleedStep {
  platform: string;
  first_seen: string;
  post_count: number;
  unique_authors: number;
  delay_minutes: number | null;
}

export interface CampaignInspectData {
  campaign_id: string;
  campaign_label: string | null;
  confidence: number | null;
  posts: InspectPost[];
  total_posts: number;
  unique_authors: number;
  unique_platforms: number;
  identity_ratio: number;
  copypasta_phrases: CopypastaPhrase[];
  platform_bleed: PlatformBleedStep[];
  time_span_minutes: number | null;
  evidence_summary: string;
}

export async function fetchCampaignInspect(campaignId: string, projectId: string): Promise<CampaignInspectData> {
  const res = await fetch(`${API_BASE}/api/campaigns/${campaignId}/inspect?project_id=${projectId}`);
  if (!res.ok) throw new Error("Failed to fetch campaign inspection");
  return res.json();
}

export interface NotificationSettings {
  slack_webhook_url: string;
  discord_webhook_url: string;
  telegram_bot_token: string;
  telegram_chat_id: string;
  confidence_threshold: number;
}

export interface TestAlertResult {
  channel: string;
  success: boolean;
  error: string | null;
}

export async function fetchNotificationSettings(): Promise<NotificationSettings> {
  const res = await fetch(`${API_BASE}/api/settings/notifications`);
  if (!res.ok) throw new Error("Failed to fetch notification settings");
  return res.json();
}

export async function updateNotificationSettings(
  settings: Partial<NotificationSettings>,
): Promise<NotificationSettings> {
  const res = await fetch(`${API_BASE}/api/settings/notifications`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!res.ok) throw new Error("Failed to update notification settings");
  return res.json();
}

export async function testAlertConnection(
  channel: "slack" | "discord" | "telegram",
): Promise<TestAlertResult> {
  const res = await fetch(`${API_BASE}/api/alerts/test/${channel}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to test alert connection");
  return res.json();
}

export interface IngestionLogPost {
  id: string;
  content: string;
  platform: string;
  author_handle: string | null;
  published_at: string;
  composite_score: number | null;
}

export interface IngestionLogFilters {
  platform?: string;
  max_score?: number;
  limit?: number;
}

export async function fetchIngestionLogs(
  projectId: string,
  filters: IngestionLogFilters = {},
): Promise<IngestionLogPost[]> {
  const params = new URLSearchParams();
  params.set("project_id", projectId);
  if (filters.platform) params.set("platform", filters.platform);
  if (filters.max_score !== undefined) params.set("max_score", String(filters.max_score));
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  const qs = params.toString();
  const res = await fetch(`${API_BASE}/api/posts/log?${qs}`);
  if (!res.ok) throw new Error("Failed to fetch ingestion logs");
  return res.json();
}

export interface BaselineSettings {
  heuristic_threshold: number;
  copypasta_threshold: number;
  temporal_cluster_min: number;
  new_account_days: number;
}

export interface BaselineSettingsUpdate {
  heuristic_threshold?: number;
  copypasta_threshold?: number;
  temporal_cluster_min?: number;
  new_account_days?: number;
}

export async function fetchBaselineSettings(): Promise<BaselineSettings> {
  const res = await fetch(`${API_BASE}/api/settings/baseline`);
  if (!res.ok) throw new Error("Failed to fetch baseline settings");
  return res.json();
}

export async function updateBaselineSettings(
  settings: BaselineSettingsUpdate,
): Promise<BaselineSettings> {
  const res = await fetch(`${API_BASE}/api/settings/baseline`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!res.ok) throw new Error("Failed to update baseline settings");
  return res.json();
}

export interface ProjectTarget {
  id: string;
  platform: string;
  target_type: string;
  value: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  targets: ProjectTarget[];
}

export interface ProjectCreate {
  name: string;
  description?: string;
  targets: Array<{
    platform: string;
    target_type: string;
    value: string;
  }>;
}

export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/api/projects`);
  if (!res.ok) throw new Error("Failed to fetch projects");
  return res.json();
}

export async function createProject(data: ProjectCreate): Promise<Project> {
  const res = await fetch(`${API_BASE}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create project");
  return res.json();
}

export async function deleteProject(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete project");
}

export interface EvalQueueItem {
  post_id: string;
  source: string;
  author_handle: string | null;
  author_created: string | null;
  published_at: string;
  content: string;
  copypasta_score: number;
  temporal_anomaly: number;
  account_age_flag: number;
  composite_score: number;
  account_age_days: number | null;
}

export interface EvalQueueResponse {
  posts: EvalQueueItem[];
  remaining_unlabeled: number;
}

export async function fetchEvalQueue(
  projectId: string,
  limit: number = 25,
  highFrac: number = 0.75,
): Promise<EvalQueueResponse> {
  const params = new URLSearchParams();
  params.set("project_id", projectId);
  params.set("limit", String(limit));
  params.set("high_frac", String(highFrac));
  const res = await fetch(`${API_BASE}/api/eval/queue?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to fetch eval queue");
  return res.json();
}

export interface EvalLabelResponse {
  post_id: string;
  label: string;
  status: string;
}

export async function submitEvalLabel(
  postId: string,
  label: "organic" | "coordinated" | "uncertain",
): Promise<EvalLabelResponse> {
  const res = await fetch(`${API_BASE}/api/eval/label`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ post_id: postId, label }),
  });
  if (!res.ok) throw new Error("Failed to submit label");
  return res.json();
}

export interface SimilarPost {
  post_id: string;
  author_handle: string | null;
  source: string;
  published_at: string;
  content: string;
  similarity: number;
}

export interface AuthorRecentPost {
  post_id: string;
  source: string;
  published_at: string;
  content: string;
  composite_score: number | null;
}

export interface AuthorStats {
  author_handle: string | null;
  author_created: string | null;
  account_age_days: number | null;
  total_posts_in_project: number;
  first_seen: string | null;
  last_seen: string | null;
  distinct_sources: string[];
}

export interface EvalEvidenceResponse {
  post_id: string;
  project_id: string;
  similar_posts: SimilarPost[];
  author_recent_posts: AuthorRecentPost[];
  author_stats: AuthorStats;
}

export async function fetchEvalEvidence(postId: string): Promise<EvalEvidenceResponse> {
  const res = await fetch(`${API_BASE}/api/eval/evidence/${postId}`);
  if (!res.ok) throw new Error("Failed to fetch eval evidence");
  return res.json();
}
