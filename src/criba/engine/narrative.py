import logging
import uuid

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from criba.db.models import Post, LlmAnalysis, PostEmbedding, Narrative, NarrativePost, Campaign

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.85


class NarrativeEngine:

    def __init__(self, session: AsyncSession, similarity_threshold: float = SIMILARITY_THRESHOLD):
        self._session = session
        self._threshold = similarity_threshold

    async def cluster_posts(self, project_id: uuid.UUID, limit: int = 200) -> dict:
        clustered_post_ids = select(NarrativePost.post_id)
        stmt = (
            select(Post, LlmAnalysis, PostEmbedding)
            .join(LlmAnalysis, Post.id == LlmAnalysis.post_id)
            .join(PostEmbedding, Post.id == PostEmbedding.post_id)
            .where(Post.id.notin_(clustered_post_ids))
            .where(Post.project_id == project_id)
            .order_by(Post.published_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.all()

        if not rows:
            logger.info("No unclustered posts to process")
            return {"clustered": 0, "new_narratives": 0, "updated_narratives": 0}

        clustered = 0
        new_narratives = 0
        updated_narratives = 0

        for post, analysis, embedding in rows:
            best_narrative = await self._find_matching_narrative(embedding.embedding, project_id)

            if best_narrative is None:
                best_narrative = await self._create_narrative(post, analysis, embedding, project_id)
                new_narratives += 1
            else:
                await self._update_narrative(best_narrative, post, analysis, embedding)
                updated_narratives += 1

            link_stmt = pg_insert(NarrativePost).values(
                narrative_id=best_narrative.id,
                post_id=post.id,
            ).on_conflict_do_nothing()
            await self._session.execute(link_stmt)
            await self._session.commit()
            clustered += 1

        logger.info(
            "Clustering complete: clustered=%d new_narratives=%d updated_narratives=%d",
            clustered, new_narratives, updated_narratives,
        )
        return {"clustered": clustered, "new_narratives": new_narratives, "updated_narratives": updated_narratives}

    async def _find_matching_narrative(self, embedding: list[float], project_id: uuid.UUID) -> Narrative | None:
        from pgvector.sqlalchemy import Vector

        max_distance = 1.0 - self._threshold

        stmt = (
            select(Narrative)
            .where(Narrative.embedding.isnot(None))
            .where(Narrative.status == "active")
            .where(Narrative.project_id == project_id)
            .order_by(Narrative.embedding.cosine_distance(embedding))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        candidate = result.scalar_one_or_none()

        if candidate is None or candidate.embedding is None:
            return None

        distance_stmt = select(Narrative.embedding.cosine_distance(embedding)).where(Narrative.id == candidate.id)
        dist_result = await self._session.execute(distance_stmt)
        distance = dist_result.scalar_one()

        if distance <= max_distance:
            return candidate
        return None

    async def _create_narrative(self, post: Post, analysis: LlmAnalysis, embedding: PostEmbedding, project_id: uuid.UUID) -> Narrative:
        label = self._derive_label(analysis)
        narrative = Narrative(
            id=uuid.uuid4(),
            label=label,
            first_seen=post.published_at,
            last_seen=post.published_at,
            post_count=1,
            platform_spread=1,
            status="active",
            embedding=embedding.embedding,
            project_id=project_id,
        )
        self._session.add(narrative)
        await self._session.commit()
        return narrative

    async def _update_narrative(self, narrative: Narrative, post: Post, analysis: LlmAnalysis, embedding: PostEmbedding) -> None:
        if narrative.first_seen is None or post.published_at < narrative.first_seen:
            narrative.first_seen = post.published_at
        if narrative.last_seen is None or post.published_at > narrative.last_seen:
            narrative.last_seen = post.published_at

        narrative.post_count = (narrative.post_count or 0) + 1

        new_label = self._derive_label(analysis)
        if new_label and (not narrative.label or narrative.label.startswith("Narrative ")):
            narrative.label = new_label

        await self._session.commit()

        recount_stmt = (
            select(func.count(func.distinct(Post.source)))
            .join(NarrativePost, Post.id == NarrativePost.post_id)
            .where(NarrativePost.narrative_id == narrative.id)
        )
        result = await self._session.execute(recount_stmt)
        narrative.platform_spread = result.scalar_one()
        await self._session.commit()

    def _derive_label(self, analysis: LlmAnalysis) -> str:
        if analysis.talking_points and len(analysis.talking_points) > 0:
            points = analysis.talking_points[:3]
            return " | ".join(points)
        if analysis.narrative_category:
            return f"{analysis.narrative_category.replace('_', ' ').title()} narrative"
        return "Unnamed narrative"

    async def detect_campaigns(self, project_id: uuid.UUID) -> dict:
        stmt = (
            select(Narrative)
            .where(Narrative.status == "active")
            .where(Narrative.post_count > 20)
            .where(Narrative.platform_spread >= 2)
            .where(Narrative.project_id == project_id)
        )
        result = await self._session.execute(stmt)
        candidates = result.scalars().all()

        detected = 0
        skipped = 0

        for narrative in candidates:
            author_stmt = (
                select(func.count(func.distinct(Post.author_id)))
                .join(NarrativePost, Post.id == NarrativePost.post_id)
                .where(NarrativePost.narrative_id == narrative.id)
            )
            author_result = await self._session.execute(author_stmt)
            unique_authors = author_result.scalar_one()

            if unique_authors <= 10:
                skipped += 1
                continue

            existing = await self._session.execute(
                select(Campaign).where(Campaign.label == narrative.label).where(Campaign.status == "active").where(Campaign.project_id == project_id)
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

            platforms_stmt = (
                select(func.distinct(Post.source))
                .join(NarrativePost, Post.id == NarrativePost.post_id)
                .where(NarrativePost.narrative_id == narrative.id)
            )
            platforms_result = await self._session.execute(platforms_stmt)
            platforms = [row[0] for row in platforms_result.all()]

            avg_coord_stmt = (
                select(func.avg(LlmAnalysis.coordination_probability))
                .join(Post, LlmAnalysis.post_id == Post.id)
                .join(NarrativePost, Post.id == NarrativePost.post_id)
                .where(NarrativePost.narrative_id == narrative.id)
            )
            avg_result = await self._session.execute(avg_coord_stmt)
            avg_coordination = avg_result.scalar_one() or 0.0

            post_count_stmt = (
                select(func.count(NarrativePost.post_id))
                .where(NarrativePost.narrative_id == narrative.id)
            )
            post_count_result = await self._session.execute(post_count_stmt)
            total_posts = post_count_result.scalar_one()

            confidence = self._calculate_confidence(avg_coordination, unique_authors, total_posts, len(platforms))

            campaign = Campaign(
                id=uuid.uuid4(),
                label=narrative.label,
                description=f"Auto-detected campaign from narrative cluster. "
                           f"Avg coordination: {avg_coordination:.2f}, "
                           f"{unique_authors} unique authors across {len(platforms)} platforms.",
                confidence=confidence,
                account_count=unique_authors,
                post_count=total_posts,
                platforms=platforms,
                status="active",
                project_id=project_id,
            )
            self._session.add(campaign)
            await self._session.commit()
            detected += 1

            logger.info(
                "Campaign detected: %s (confidence=%.2f, authors=%d, posts=%d, platforms=%s)",
                narrative.label, confidence, unique_authors, total_posts, platforms,
            )

        logger.info("Campaign detection complete: detected=%d skipped=%d", detected, skipped)
        return {"detected": detected, "skipped": skipped}

    @staticmethod
    def _calculate_confidence(avg_coordination: float, unique_authors: int, post_count: int, platform_count: int) -> float:
        confidence = avg_coordination * 0.5

        if unique_authors > 20:
            confidence += 0.15
        elif unique_authors > 10:
            confidence += 0.1

        if post_count > 50:
            confidence += 0.15
        elif post_count > 20:
            confidence += 0.1

        if platform_count >= 3:
            confidence += 0.1
        elif platform_count >= 2:
            confidence += 0.05

        return min(1.0, max(0.0, confidence))
