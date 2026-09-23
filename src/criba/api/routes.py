import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from criba.api.schemas import (
    BaselineSettings,
    BaselineSettingsUpdate,
    CampaignInspectResponse,
    CampaignResponse,
    CopypastaPhrase,
    AuthorRecentPost,
    AuthorStats,
    EvalEvidenceResponse,
    EvalLabelInput,
    EvalLabelResponse,
    EvalQueueItem,
    EvalQueueResponse,
    FlaggedPostResponse,
    InspectPost,
    NarrativeResponse,
    NetworkGraphResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    PlatformBleedStep,
    ProjectCreate,
    ProjectResponse,
    ProjectTargetInput,
    ProjectTargetResponse,
    RawPostLog,
    SimilarPost,
    StatsSummary,
    TestAlertResponse,
)
from criba.db.connection import get_async_session
from criba.db.models import (
    AuthorGraph,
    Campaign,
    GroundTruth,
    HeuristicScore,
    LlmAnalysis,
    Narrative,
    NarrativePost,
    Post,
    PostEmbedding,
    Project,
    ProjectTarget,
    SystemSetting,
)

logger = logging.getLogger(__name__)

async def _get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    )
    row = result.scalar_one_or_none()
    return row.value if row else default


async def _set_setting(session: AsyncSession, key: str, value: str) -> None:
    result = await session.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    )
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(SystemSetting(key=key, value=value))

router = APIRouter(prefix="/api")


@router.get("/narratives", response_model=list[NarrativeResponse])
async def list_narratives(
    project_id: uuid.UUID = Query(..., description="Project to scope results to"),
    status: str = Query(default="active"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    stmt = (
        select(Narrative)
        .where(Narrative.project_id == project_id)
        .where(Narrative.status == status)
        .order_by(Narrative.post_count.desc(), Narrative.last_seen.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    narratives = result.scalars().all()
    return narratives


@router.get("/campaigns", response_model=list[CampaignResponse])
async def list_campaigns(
    project_id: uuid.UUID = Query(..., description="Project to scope results to"),
    status: str = Query(default="active"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    stmt = (
        select(Campaign)
        .where(Campaign.project_id == project_id)
        .where(Campaign.status == status)
        .order_by(Campaign.confidence.desc(), Campaign.detected_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    campaigns = result.scalars().all()
    return campaigns


@router.get("/posts/flagged", response_model=list[FlaggedPostResponse])
async def list_flagged_posts(
    project_id: uuid.UUID = Query(..., description="Project to scope results to"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    min_score: float = Query(default=0.6, ge=0.0, le=1.0),
    session: AsyncSession = Depends(get_async_session),
):
    stmt = (
        select(Post, HeuristicScore, LlmAnalysis)
        .join(HeuristicScore, Post.id == HeuristicScore.post_id)
        .outerjoin(LlmAnalysis, Post.id == LlmAnalysis.post_id)
        .where(HeuristicScore.composite_score >= min_score)
        .where(Post.project_id == project_id)
        .order_by(HeuristicScore.composite_score.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.all()

    return [
        FlaggedPostResponse(
            id=post.id,
            content=post.content,
            source=post.source,
            author_handle=post.author_handle,
            published_at=post.published_at,
            anomaly_score=score.composite_score,
            narrative_category=analysis.narrative_category if analysis else None,
            coordination_probability=analysis.coordination_probability if analysis else None,
            recommended_action=analysis.recommended_action if analysis else None,
        )
        for post, score, analysis in rows
    ]


@router.get("/posts/log", response_model=list[RawPostLog])
async def ingestion_log(
    project_id: uuid.UUID = Query(..., description="Project to scope results to"),
    platform: str | None = Query(default=None),
    max_score: float = Query(default=0.6, ge=0.0, le=1.0),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_async_session),
):
    stmt = (
        select(Post, HeuristicScore)
        .join(HeuristicScore, Post.id == HeuristicScore.post_id)
        .where(HeuristicScore.composite_score <= max_score)
        .where(Post.project_id == project_id)
    )
    if platform is not None:
        stmt = stmt.where(Post.source == platform)
    stmt = stmt.order_by(Post.published_at.desc()).limit(limit)
    result = await session.execute(stmt)
    rows = result.all()

    return [
        RawPostLog(
            id=post.id,
            content=post.content,
            platform=post.source,
            author_handle=post.author_handle,
            published_at=post.published_at,
            composite_score=score.composite_score,
        )
        for post, score in rows
    ]


@router.get("/stats/summary", response_model=StatsSummary)
async def stats_summary(
    project_id: uuid.UUID = Query(..., description="Project to scope results to"),
    session: AsyncSession = Depends(get_async_session),
):
    total_posts = (
        await session.execute(
            select(func.count(Post.id)).where(Post.project_id == project_id)
        )
    ).scalar_one()
    flagged_posts = (
        await session.execute(
            select(func.count(HeuristicScore.post_id))
            .join(Post, HeuristicScore.post_id == Post.id)
            .where(Post.project_id == project_id)
            .where(HeuristicScore.sent_to_llm == True)
        )
    ).scalar_one()
    analyzed_posts = (
        await session.execute(
            select(func.count(LlmAnalysis.post_id))
            .join(Post, LlmAnalysis.post_id == Post.id)
            .where(Post.project_id == project_id)
        )
    ).scalar_one()
    active_narratives = (
        await session.execute(
            select(func.count(Narrative.id))
            .where(Narrative.status == "active")
            .where(Narrative.project_id == project_id)
        )
    ).scalar_one()
    active_campaigns = (
        await session.execute(
            select(func.count(Campaign.id))
            .where(Campaign.status == "active")
            .where(Campaign.project_id == project_id)
        )
    ).scalar_one()
    clustered_posts = (
        await session.execute(
            select(func.count(NarrativePost.post_id))
            .join(Post, NarrativePost.post_id == Post.id)
            .where(Post.project_id == project_id)
        )
    ).scalar_one()

    return StatsSummary(
        total_posts=total_posts,
        flagged_posts=flagged_posts,
        analyzed_posts=analyzed_posts,
        active_narratives=active_narratives,
        active_campaigns=active_campaigns,
        clustered_posts=clustered_posts,
    )


@router.get("/network/{narrative_id}", response_model=NetworkGraphResponse)
async def get_network(
    narrative_id: uuid.UUID,
    project_id: uuid.UUID = Query(..., description="Project to scope results to"),
    session: AsyncSession = Depends(get_async_session),
):
    narrative = await session.get(Narrative, narrative_id)
    if narrative is None or narrative.project_id != project_id:
        raise HTTPException(status_code=404, detail="Narrative not found")

    stmt = (
        select(Post.author_id, Post.author_handle, Post.source)
        .join(NarrativePost, Post.id == NarrativePost.post_id)
        .where(NarrativePost.narrative_id == narrative_id)
    )
    result = await session.execute(stmt)
    author_rows = result.all()

    source_counts: dict[str, dict[str, int]] = {}
    author_info: dict[str, dict[str, str | None]] = {}
    for author_id, author_handle, source in author_rows:
        if author_id not in author_info:
            author_info[author_id] = {"handle": author_handle, "platform": None}
            source_counts[author_id] = {}
        if source:
            source_counts[author_id][source] = source_counts[author_id].get(source, 0) + 1

    for author_id in author_info:
        if source_counts[author_id]:
            author_info[author_id]["platform"] = max(
                source_counts[author_id], key=source_counts[author_id].get
            )

    author_ids = set(author_info.keys())

    stmt = select(AuthorGraph).where(
        and_(AuthorGraph.source_author.in_(author_ids), AuthorGraph.target_author.in_(author_ids))
    )
    result = await session.execute(stmt)
    edges = result.scalars().all()

    degree: dict[str, int] = {}
    for edge in edges:
        degree[edge.source_author] = degree.get(edge.source_author, 0) + 1
        degree[edge.target_author] = degree.get(edge.target_author, 0) + 1

    adjacency: dict[str, set[str]] = {}
    for author_id in author_ids:
        adjacency[author_id] = set()
    for edge in edges:
        adjacency[edge.source_author].add(edge.target_author)
        adjacency[edge.target_author].add(edge.source_author)

    cluster_members: set[str] = set()
    for node in author_ids:
        neighbors = list(adjacency[node])
        mutual_count = 0
        for i, neighbor_a in enumerate(neighbors):
            for neighbor_b in neighbors[i + 1:]:
                if neighbor_b in adjacency[neighbor_a]:
                    mutual_count += 1
        if mutual_count >= 3:
            cluster_members.add(node)

    clusters: list[list[str]] = []
    visited: set[str] = set()

    def bfs(start: str) -> list[str]:
        cluster = []
        queue = [start]
        visited.add(start)
        while queue:
            current = queue.pop(0)
            cluster.append(current)
            for neighbor in adjacency[current]:
                if neighbor in cluster_members and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return cluster

    for node in cluster_members:
        if node not in visited:
            clusters.append(bfs(node))

    node_cluster_map: dict[str, tuple[int, int]] = {}
    for cluster_idx, cluster in enumerate(clusters):
        for node in cluster:
            node_cluster_map[node] = (cluster_idx, len(cluster))

    nodes = [
        {
            "id": author_id,
            "handle": author_info[author_id]["handle"],
            "platform": author_info[author_id]["platform"],
            "degree": degree.get(author_id, 0),
            "is_cluster": author_id in node_cluster_map,
            "cluster_id": node_cluster_map[author_id][0] if author_id in node_cluster_map else None,
        }
        for author_id in author_ids
    ]

    links = [
        {"source": edge.source_author, "target": edge.target_author, "interaction": edge.interaction, "weight": edge.weight}
        for edge in edges
    ]

    return NetworkGraphResponse(
        narrative_id=narrative_id,
        narrative_label=narrative.label,
        nodes=nodes,
        links=links,
        clusters=clusters,
        total_authors=len(author_ids),
        total_interactions=len(edges),
    )


@router.get("/campaigns/{campaign_id}/inspect", response_model=CampaignInspectResponse)
async def inspect_campaign(
    campaign_id: uuid.UUID,
    project_id: uuid.UUID = Query(..., description="Project to scope results to"),
    session: AsyncSession = Depends(get_async_session),
):
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.project_id != project_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    narrative_stmt = (
        select(Narrative)
        .where(Narrative.label == campaign.label)
        .where(Narrative.status == "active")
        .where(Narrative.project_id == project_id)
        .limit(1)
    )
    narrative_result = await session.execute(narrative_stmt)
    narrative = narrative_result.scalar_one_or_none()

    if narrative is None:
        return CampaignInspectResponse(
            campaign_id=campaign_id,
            campaign_label=campaign.label,
            confidence=campaign.confidence,
            posts=[],
            total_posts=0,
            unique_authors=0,
            unique_platforms=0,
            identity_ratio=0.0,
            copypasta_phrases=[],
            platform_bleed=[],
            time_span_minutes=None,
            evidence_summary=f"{round((campaign.confidence or 0) * 100)}% Confidence: No matching narrative found",
        )

    posts_stmt = (
        select(Post, HeuristicScore, LlmAnalysis)
        .join(NarrativePost, Post.id == NarrativePost.post_id)
        .outerjoin(HeuristicScore, Post.id == HeuristicScore.post_id)
        .outerjoin(LlmAnalysis, Post.id == LlmAnalysis.post_id)
        .where(NarrativePost.narrative_id == narrative.id)
        .order_by(Post.published_at.asc())
    )
    result = await session.execute(posts_stmt)
    rows = result.all()

    posts = [
        InspectPost(
            id=post.id,
            source=post.source,
            author_id=post.author_id,
            author_handle=post.author_handle,
            content=post.content,
            published_at=post.published_at,
            composite_score=score.composite_score if score else None,
            coordination_probability=analysis.coordination_probability if analysis else None,
            narrative_category=analysis.narrative_category if analysis else None,
        )
        for post, score, analysis in rows
    ]

    normalized_contents = [p.content.lower().strip() for p in posts]
    content_counts = Counter(normalized_contents)
    total = len(posts)
    duplicate_posts = sum(count for content, count in content_counts.items() if count > 1)
    identity_ratio = duplicate_posts / total if total > 0 else 0.0

    def _extract_shingles(text: str, k: int = 5) -> list[str]:
        words = text.lower().split()
        if len(words) < k:
            return [text.lower()]
        return [" ".join(words[i:i+k]) for i in range(len(words) - k + 1)]

    shingle_counter: Counter = Counter()
    shingle_authors: dict[str, set[str]] = {}

    for post in posts:
        shingles = _extract_shingles(post.content)
        for sh in shingles:
            shingle_counter[sh] += 1
            if sh not in shingle_authors:
                shingle_authors[sh] = set()
            shingle_authors[sh].add(post.author_id)

    copypasta_phrases = []
    for phrase, count in shingle_counter.most_common():
        if count < 2:
            continue
        unique_auths = len(shingle_authors.get(phrase, set()))
        if unique_auths < 2:
            continue
        copypasta_phrases.append(CopypastaPhrase(
            phrase=phrase,
            count=count,
            unique_authors=unique_auths,
            percentage=round(count / total * 100, 1) if total > 0 else 0.0,
        ))
        if len(copypasta_phrases) >= 10:
            break

    platform_first_seen: dict[str, datetime] = {}
    platform_posts: dict[str, int] = {}
    platform_authors: dict[str, set[str]] = {}

    for post in posts:
        src = post.source
        if src not in platform_first_seen or post.published_at < platform_first_seen[src]:
            platform_first_seen[src] = post.published_at
        platform_posts[src] = platform_posts.get(src, 0) + 1
        if src not in platform_authors:
            platform_authors[src] = set()
        platform_authors[src].add(post.author_id)

    bleed_steps = sorted(platform_first_seen.items(), key=lambda x: x[1])
    first_time = bleed_steps[0][1] if bleed_steps else None

    platform_bleed = []
    for platform, first_seen in bleed_steps:
        delay = (first_seen - first_time).total_seconds() / 60.0 if first_time else None
        platform_bleed.append(PlatformBleedStep(
            platform=platform,
            first_seen=first_seen,
            post_count=platform_posts.get(platform, 0),
            unique_authors=len(platform_authors.get(platform, set())),
            delay_minutes=round(delay, 1) if delay is not None else None,
        ))

    if posts:
        time_span = (posts[-1].published_at - posts[0].published_at).total_seconds() / 60.0
    else:
        time_span = None

    unique_author_ids = set(p.author_id for p in posts)
    unique_platform_set = set(p.source for p in posts)
    plural_posts = "post" if total == 1 else "posts"
    identity_pct = round(identity_ratio * 100)

    if identity_ratio >= 0.8:
        dup_word = "identical"
    elif identity_ratio >= 0.5:
        dup_word = "near-identical"
    else:
        dup_word = "similar"

    if time_span is not None:
        time_str = f"in {round(time_span)} minutes"
    else:
        time_str = ""

    evidence_summary = (
        f"{round((campaign.confidence or 0) * 100)}% Confidence: "
        f"{total} {dup_word} {plural_posts} from {len(unique_author_ids)} authors "
        f"across {len(unique_platform_set)} platforms"
        f"{(' ' + time_str) if time_str else ''}"
    )

    return CampaignInspectResponse(
        campaign_id=campaign_id,
        campaign_label=campaign.label,
        confidence=campaign.confidence,
        posts=posts,
        total_posts=len(posts),
        unique_authors=len(unique_author_ids),
        unique_platforms=len(unique_platform_set),
        identity_ratio=round(identity_ratio, 3),
        copypasta_phrases=copypasta_phrases,
        platform_bleed=platform_bleed,
        time_span_minutes=round(time_span, 1) if time_span is not None else None,
        evidence_summary=evidence_summary,
    )


@router.get("/settings/notifications", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    session: AsyncSession = Depends(get_async_session),
):
    keys = [
        "slack_webhook_url", "discord_webhook_url",
        "telegram_bot_token", "telegram_chat_id", "confidence_threshold",
    ]
    values = {}
    for key in keys:
        values[key] = await _get_setting(session, key, "")
    values["confidence_threshold"] = float(values.get("confidence_threshold", "0.85") or "0.85")
    return NotificationSettingsResponse(**values)


@router.put("/settings/notifications", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    update: NotificationSettingsUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    mapping = {
        "slack_webhook_url": update.slack_webhook_url,
        "discord_webhook_url": update.discord_webhook_url,
        "telegram_bot_token": update.telegram_bot_token,
        "telegram_chat_id": update.telegram_chat_id,
        "confidence_threshold": (
            str(update.confidence_threshold) if update.confidence_threshold is not None else None
        ),
    }
    for key, value in mapping.items():
        if value is not None:
            await _set_setting(session, key, value)
    await session.commit()

    keys = [
        "slack_webhook_url", "discord_webhook_url",
        "telegram_bot_token", "telegram_chat_id", "confidence_threshold",
    ]
    values = {}
    for key in keys:
        values[key] = await _get_setting(session, key, "")
    values["confidence_threshold"] = float(values.get("confidence_threshold", "0.85") or "0.85")
    return NotificationSettingsResponse(**values)


@router.get("/settings/baseline", response_model=BaselineSettings)
async def get_baseline_settings(
    session: AsyncSession = Depends(get_async_session),
):
    return BaselineSettings(
        heuristic_threshold=float(await _get_setting(session, "heuristic_threshold", "0.6")),
        copypasta_threshold=int(await _get_setting(session, "copypasta_threshold", "10")),
        temporal_cluster_min=int(await _get_setting(session, "temporal_cluster_min", "5")),
        new_account_days=int(await _get_setting(session, "new_account_days", "7")),
    )


@router.put("/settings/baseline", response_model=BaselineSettings)
async def update_baseline_settings(
    update: BaselineSettingsUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    if update.heuristic_threshold is not None:
        await _set_setting(session, "heuristic_threshold", str(update.heuristic_threshold))
    if update.copypasta_threshold is not None:
        await _set_setting(session, "copypasta_threshold", str(update.copypasta_threshold))
    if update.temporal_cluster_min is not None:
        await _set_setting(session, "temporal_cluster_min", str(update.temporal_cluster_min))
    if update.new_account_days is not None:
        await _set_setting(session, "new_account_days", str(update.new_account_days))
    await session.commit()

    return BaselineSettings(
        heuristic_threshold=float(await _get_setting(session, "heuristic_threshold", "0.6")),
        copypasta_threshold=int(await _get_setting(session, "copypasta_threshold", "10")),
        temporal_cluster_min=int(await _get_setting(session, "temporal_cluster_min", "5")),
        new_account_days=int(await _get_setting(session, "new_account_days", "7")),
    )


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    session: AsyncSession = Depends(get_async_session),
):
    stmt = select(Project).order_by(Project.created_at.desc())
    result = await session.execute(stmt)
    projects = result.scalars().all()

    response = []
    for project in projects:
        targets_stmt = select(ProjectTarget).where(ProjectTarget.project_id == project.id)
        targets_result = await session.execute(targets_stmt)
        targets = targets_result.scalars().all()
        response.append(ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
            targets=[
                ProjectTargetResponse(
                    id=t.id,
                    platform=t.platform,
                    target_type=t.target_type,
                    value=t.value,
                )
                for t in targets
            ],
        ))
    return response


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    session: AsyncSession = Depends(get_async_session),
):
    project = Project(
        name=data.name,
        description=data.description,
    )
    session.add(project)
    await session.flush()

    targets = []
    for target_input in data.targets:
        target = ProjectTarget(
            project_id=project.id,
            platform=target_input.platform,
            target_type=target_input.target_type,
            value=target_input.value,
        )
        session.add(target)
        targets.append(target)
    await session.commit()

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        targets=[
            ProjectTargetResponse(
                id=t.id,
                platform=t.platform,
                target_type=t.target_type,
                value=t.value,
            )
            for t in targets
        ],
    )


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    await session.execute(delete(ProjectTarget).where(ProjectTarget.project_id == project_id))
    await session.delete(project)
    await session.commit()


@router.post("/alerts/test/{channel}", response_model=TestAlertResponse)
async def test_alert(channel: str):
    if channel not in ("slack", "discord", "telegram"):
        raise HTTPException(status_code=400, detail="Invalid channel. Use: slack, discord, telegram")
    from criba.worker.alerts import send_test_alert
    result = await send_test_alert(channel)
    return TestAlertResponse(**result)


_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)
_URL_RE = re.compile(r"https?://\S+")
_MENTION_RE = re.compile(r"@\w+")


def is_junk(content: str, min_words: int = 2) -> bool:
    if not content or not content.strip():
        return True
    stripped = _EMOJI_RE.sub("", content)
    stripped = _URL_RE.sub("", stripped)
    stripped = _MENTION_RE.sub("", stripped)
    stripped = re.sub(r"[^\w\s]", "", stripped).strip()
    if not stripped:
        return True
    words = [w for w in stripped.split() if len(w) >= 2 and any(c.isalnum() for c in w)]
    return len(words) < min_words


@router.get("/eval/queue", response_model=EvalQueueResponse)
async def get_eval_queue(
    project_id: uuid.UUID = Query(..., description="Project to scope results to"),
    limit: int = Query(default=25, le=200),
    high_frac: float = Query(default=0.5, ge=0.0, le=1.0),
    min_words: int = Query(default=2, ge=1, le=10, description="Minimum meaningful words to avoid junk"),
    session: AsyncSession = Depends(get_async_session),
):
    n_high = round(limit * high_frac)
    n_low = limit - n_high
    fetch_multiplier = 4

    base = (
        select(
            Post.id,
            Post.source,
            Post.author_handle,
            Post.author_created,
            Post.published_at,
            Post.content,
            HeuristicScore.copypasta_score,
            HeuristicScore.temporal_anomaly,
            HeuristicScore.account_age_flag,
            HeuristicScore.composite_score,
        )
        .join(HeuristicScore, HeuristicScore.post_id == Post.id)
        .outerjoin(GroundTruth, GroundTruth.post_id == Post.id)
        .where(Post.project_id == project_id)
        .where(GroundTruth.post_id.is_(None))
    )

    high_q = base.order_by(HeuristicScore.composite_score.desc()).limit(n_high * fetch_multiplier)
    low_q = base.order_by(HeuristicScore.composite_score.asc()).limit(n_low * fetch_multiplier)

    # Query the strata separately: SQL UNION does not preserve the ORDER BY
    # of its inputs, so a single unordered union cannot be split back into
    # high- and low-score samples by row position.
    high_rows = (await session.execute(high_q)).fetchall()
    low_rows = (await session.execute(low_q)).fetchall()

    seen: set[uuid.UUID] = set()
    high_survivors = []
    for row in high_rows:
        if row[0] in seen:
            continue
        seen.add(row[0])
        if is_junk(row[5], min_words):
            continue
        if len(high_survivors) < n_high:
            high_survivors.append(row)
        else:
            break

    low_survivors = []
    for row in low_rows:
        if row[0] in seen:
            continue
        seen.add(row[0])
        if is_junk(row[5], min_words):
            continue
        if len(low_survivors) < n_low:
            low_survivors.append(row)
        else:
            break

    remaining = (
        await session.execute(
            select(func.count(Post.id))
            .join(HeuristicScore, HeuristicScore.post_id == Post.id)
            .outerjoin(GroundTruth, GroundTruth.post_id == Post.id)
            .where(Post.project_id == project_id)
            .where(GroundTruth.post_id.is_(None))
        )
    ).scalar_one()

    items = []
    for row in high_survivors + low_survivors:
        post_id, source, author_handle, author_created, published_at, content, cp, ta, aa, composite = row
        age_days = None
        if author_created and published_at:
            age_days = (published_at - author_created).total_seconds() / 86400.0
        items.append(EvalQueueItem(
            post_id=post_id,
            source=source,
            author_handle=author_handle,
            author_created=author_created,
            published_at=published_at,
            content=content,
            copypasta_score=cp,
            temporal_anomaly=ta,
            account_age_flag=aa,
            composite_score=composite,
            account_age_days=age_days,
        ))

    return EvalQueueResponse(posts=items, remaining_unlabeled=remaining)


@router.post("/eval/label", response_model=EvalLabelResponse)
async def label_eval_post(
    data: EvalLabelInput,
    session: AsyncSession = Depends(get_async_session),
):
    if data.label not in ("organic", "coordinated", "uncertain"):
        raise HTTPException(status_code=422, detail=f"Invalid label: {data.label}. Must be organic, coordinated, or uncertain.")

    post = await session.get(Post, data.post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    stmt = pg_insert(GroundTruth).values(
        post_id=data.post_id,
        label=data.label,
        labeled_by="dashboard",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["post_id"],
        set_={"label": stmt.excluded.label, "labeled_at": func.now()},
    )
    await session.execute(stmt)
    await session.commit()

    return EvalLabelResponse(post_id=data.post_id, label=data.label, status="labeled")


def _extract_shingles(text: str, k: int = 5) -> set[str]:
    words = text.lower().split()
    if len(words) < k:
        return {"".join(words)} if words else set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@router.get("/eval/evidence/{post_id}", response_model=EvalEvidenceResponse)
async def get_eval_evidence(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    project_id = post.project_id

    target_shingles = _extract_shingles(post.content)
    window_start = post.published_at - timedelta(hours=72)
    window_end = post.published_at + timedelta(hours=72)

    candidates = (
        await session.execute(
            select(Post.id, Post.author_handle, Post.source, Post.published_at, Post.content)
            .where(Post.project_id == project_id)
            .where(Post.id != post_id)
            .where(Post.published_at.between(window_start, window_end))
            .order_by(Post.published_at.desc())
            .limit(2000)
        )
    ).fetchall()

    scored = []
    for cid, chandle, csrc, cpub, ccontent in candidates:
        if is_junk(ccontent, 2):
            continue
        sim = _jaccard(target_shingles, _extract_shingles(ccontent))
        if sim >= 0.5:
            scored.append((sim, cid, chandle, csrc, cpub, ccontent))

    scored.sort(key=lambda x: x[0], reverse=True)
    similar_posts = [
        SimilarPost(post_id=sid, author_handle=sh, source=ss, published_at=sp, content=sc, similarity=round(sv, 3))
        for sv, sid, sh, ss, sp, sc in scored[:10]
    ]

    author_recent = (
        await session.execute(
            select(Post.id, Post.source, Post.published_at, Post.content, HeuristicScore.composite_score)
            .outerjoin(HeuristicScore, HeuristicScore.post_id == Post.id)
            .where(Post.project_id == project_id)
            .where(Post.author_id == post.author_id)
            .order_by(Post.published_at.desc())
            .limit(15)
        )
    ).fetchall()

    author_recent_posts = [
        AuthorRecentPost(
            post_id=aid, source=asrc, published_at=apub, content=acontent, composite_score=ascore,
        )
        for aid, asrc, apub, acontent, ascore in author_recent
    ]

    agg = (
        await session.execute(
            select(
                func.count(Post.id),
                func.min(Post.published_at),
                func.max(Post.published_at),
                func.array_agg(func.distinct(Post.source)),
            )
            .where(Post.project_id == project_id)
            .where(Post.author_id == post.author_id)
        )
    ).fetchone()

    total_author_posts, first_seen, last_seen, sources = agg
    account_age_days = None
    if post.author_created:
        account_age_days = (datetime.now(timezone.utc) - post.author_created).total_seconds() / 86400.0

    author_stats = AuthorStats(
        author_handle=post.author_handle,
        author_created=post.author_created,
        account_age_days=account_age_days,
        total_posts_in_project=total_author_posts or 0,
        first_seen=first_seen,
        last_seen=last_seen,
        distinct_sources=list(sources) if sources else [],
    )

    return EvalEvidenceResponse(
        post_id=post_id,
        project_id=project_id,
        similar_posts=similar_posts,
        author_recent_posts=author_recent_posts,
        author_stats=author_stats,
    )
