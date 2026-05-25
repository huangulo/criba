import logging
import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from criba.api.schemas import (
    CampaignInspectResponse,
    CampaignResponse,
    CopypastaPhrase,
    FlaggedPostResponse,
    InspectPost,
    NarrativeResponse,
    NetworkGraphResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    PlatformBleedStep,
    StatsSummary,
    TestAlertResponse,
)
from criba.db.connection import get_async_session
from criba.db.models import (
    AuthorGraph,
    Campaign,
    HeuristicScore,
    LlmAnalysis,
    Narrative,
    NarrativePost,
    Post,
    PostEmbedding,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/narratives", response_model=list[NarrativeResponse])
async def list_narratives(
    status: str = Query(default="active"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    stmt = (
        select(Narrative)
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
    status: str = Query(default="active"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    stmt = (
        select(Campaign)
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


@router.get("/stats/summary", response_model=StatsSummary)
async def stats_summary(session: AsyncSession = Depends(get_async_session)):
    total_posts = (await session.execute(select(func.count(Post.id)))).scalar_one()
    flagged_posts = (
        await session.execute(
            select(func.count(HeuristicScore.post_id)).where(HeuristicScore.sent_to_llm == True)
        )
    ).scalar_one()
    analyzed_posts = (await session.execute(select(func.count(LlmAnalysis.post_id)))).scalar_one()
    active_narratives = (
        await session.execute(select(func.count(Narrative.id)).where(Narrative.status == "active"))
    ).scalar_one()
    active_campaigns = (
        await session.execute(select(func.count(Campaign.id)).where(Campaign.status == "active"))
    ).scalar_one()
    clustered_posts = (await session.execute(select(func.count(NarrativePost.post_id)))).scalar_one()

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
    session: AsyncSession = Depends(get_async_session),
):
    narrative = await session.get(Narrative, narrative_id)
    if narrative is None:
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
    session: AsyncSession = Depends(get_async_session),
):
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    narrative_stmt = select(Narrative).where(Narrative.label == campaign.label).where(Narrative.status == "active").limit(1)
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
async def get_notification_settings():
    from criba.config import load_config
    config = load_config()
    n = config.notifications
    return NotificationSettingsResponse(
        slack_webhook_url=n.slack_webhook_url,
        discord_webhook_url=n.discord_webhook_url,
        telegram_bot_token=n.telegram_bot_token,
        telegram_chat_id=n.telegram_chat_id,
        confidence_threshold=n.confidence_threshold,
    )


@router.put("/settings/notifications", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    update: NotificationSettingsUpdate,
):
    from criba.config import load_config, save_config
    config = load_config()
    n = config.notifications
    if update.slack_webhook_url is not None:
        n.slack_webhook_url = update.slack_webhook_url
    if update.discord_webhook_url is not None:
        n.discord_webhook_url = update.discord_webhook_url
    if update.telegram_bot_token is not None:
        n.telegram_bot_token = update.telegram_bot_token
    if update.telegram_chat_id is not None:
        n.telegram_chat_id = update.telegram_chat_id
    if update.confidence_threshold is not None:
        n.confidence_threshold = update.confidence_threshold
    save_config(config)
    return NotificationSettingsResponse(
        slack_webhook_url=n.slack_webhook_url,
        discord_webhook_url=n.discord_webhook_url,
        telegram_bot_token=n.telegram_bot_token,
        telegram_chat_id=n.telegram_chat_id,
        confidence_threshold=n.confidence_threshold,
    )


@router.post("/alerts/test/{channel}", response_model=TestAlertResponse)
async def test_alert(channel: str):
    if channel not in ("slack", "discord", "telegram"):
        raise HTTPException(status_code=400, detail="Invalid channel. Use: slack, discord, telegram")
    from criba.worker.alerts import send_test_alert
    result = await send_test_alert(channel)
    return TestAlertResponse(**result)
