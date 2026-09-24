import uuid
from datetime import datetime

from pydantic import BaseModel


class NarrativeResponse(BaseModel):
    id: uuid.UUID
    label: str | None
    post_count: int
    platform_spread: int
    status: str
    first_seen: datetime | None
    last_seen: datetime | None


class CampaignResponse(BaseModel):
    id: uuid.UUID
    label: str | None
    confidence: float | None
    account_count: int | None
    post_count: int | None
    platforms: list[str] | None
    status: str
    detected_at: datetime


class FlaggedPostResponse(BaseModel):
    id: uuid.UUID
    content: str
    source: str
    author_handle: str | None
    published_at: datetime
    anomaly_score: float
    narrative_category: str | None
    coordination_probability: float | None
    recommended_action: str | None
    media_urls: list[str] = []


class StatsSummary(BaseModel):
    total_posts: int
    flagged_posts: int
    analyzed_posts: int
    active_narratives: int
    active_campaigns: int
    clustered_posts: int


class AlertMessage(BaseModel):
    event_type: str
    message: str
    data: dict


class NetworkNode(BaseModel):
    id: str
    handle: str | None
    platform: str | None
    degree: int
    is_cluster: bool = False
    cluster_id: int | None = None


class NetworkLink(BaseModel):
    source: str
    target: str
    interaction: str
    weight: int


class NetworkGraphResponse(BaseModel):
    narrative_id: uuid.UUID
    narrative_label: str | None
    nodes: list[NetworkNode]
    links: list[NetworkLink]
    clusters: list[list[str]]
    total_authors: int
    total_interactions: int


class InspectPost(BaseModel):
    id: uuid.UUID
    source: str
    author_id: str
    author_handle: str | None
    content: str
    published_at: datetime
    composite_score: float | None = None
    coordination_probability: float | None = None
    narrative_category: str | None = None
    media_urls: list[str] = []


class CopypastaPhrase(BaseModel):
    phrase: str
    count: int
    unique_authors: int
    percentage: float


class PlatformBleedStep(BaseModel):
    platform: str
    first_seen: datetime
    post_count: int
    unique_authors: int
    delay_minutes: float | None = None


class CampaignInspectResponse(BaseModel):
    campaign_id: uuid.UUID
    campaign_label: str | None
    confidence: float | None
    posts: list[InspectPost]
    total_posts: int
    unique_authors: int
    unique_platforms: int

    identity_ratio: float
    copypasta_phrases: list[CopypastaPhrase]

    platform_bleed: list[PlatformBleedStep]
    time_span_minutes: float | None = None

    evidence_summary: str


class NotificationSettingsResponse(BaseModel):
    slack_webhook_url: str = ""
    discord_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    confidence_threshold: float = 0.85


class NotificationSettingsUpdate(BaseModel):
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    confidence_threshold: float | None = None


class TestAlertResponse(BaseModel):
    channel: str
    success: bool
    error: str | None = None


class RawPostLog(BaseModel):
    id: uuid.UUID
    content: str
    platform: str
    author_handle: str | None
    published_at: datetime
    composite_score: float | None


class BaselineSettings(BaseModel):
    heuristic_threshold: float
    copypasta_threshold: int
    temporal_cluster_min: int
    new_account_days: int


class BaselineSettingsUpdate(BaseModel):
    heuristic_threshold: float | None = None
    copypasta_threshold: int | None = None
    temporal_cluster_min: int | None = None
    new_account_days: int | None = None


class ProjectTargetInput(BaseModel):
    platform: str
    target_type: str  # 'keyword' or 'handle'
    value: str


class ProjectTargetResponse(BaseModel):
    id: uuid.UUID
    platform: str
    target_type: str
    value: str


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    targets: list[ProjectTargetInput] = []


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    created_at: datetime
    targets: list[ProjectTargetResponse]


class EvalQueueItem(BaseModel):
    post_id: uuid.UUID
    source: str
    author_handle: str | None
    author_created: datetime | None
    published_at: datetime
    content: str
    copypasta_score: float
    temporal_anomaly: float
    account_age_flag: float
    composite_score: float
    account_age_days: float | None


class EvalQueueResponse(BaseModel):
    posts: list[EvalQueueItem]
    remaining_unlabeled: int


class EvalLabelInput(BaseModel):
    post_id: uuid.UUID
    label: str


class EvalLabelResponse(BaseModel):
    post_id: uuid.UUID
    label: str
    status: str


class SimilarPost(BaseModel):
    post_id: uuid.UUID
    author_handle: str | None
    source: str
    published_at: datetime
    content: str
    similarity: float
    media_urls: list[str] = []


class AuthorRecentPost(BaseModel):
    post_id: uuid.UUID
    source: str
    published_at: datetime
    content: str
    composite_score: float | None
    media_urls: list[str] = []


class AuthorStats(BaseModel):
    author_handle: str | None
    author_created: datetime | None
    account_age_days: float | None
    total_posts_in_project: int
    first_seen: datetime | None
    last_seen: datetime | None
    distinct_sources: list[str]


class EvalEvidenceResponse(BaseModel):
    post_id: uuid.UUID
    project_id: uuid.UUID
    similar_posts: list[SimilarPost]
    author_recent_posts: list[AuthorRecentPost]
    author_stats: AuthorStats
