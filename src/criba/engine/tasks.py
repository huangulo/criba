import asyncio
import logging

from criba.celery_app import app

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3, default_retry_delay=120)
def generate_post_embeddings(self) -> dict:
    try:
        return asyncio.run(_generate_embeddings_async())
    except Exception as exc:
        logger.exception("Embedding generation task failed")
        raise self.retry(exc=exc)


async def _generate_embeddings_async() -> dict:
    from sqlalchemy import select
    from criba.db.connection import get_async_session_factory
    from criba.db.models import LlmAnalysis, PostEmbedding, Post
    from criba.llm.embedding import OllamaEmbeddingClient

    client = OllamaEmbeddingClient()

    available = await client.is_available()
    if not available:
        logger.warning("Ollama not available at %s, skipping embedding generation", client._host)
        return {"error": "ollama unavailable"}

    embedded = 0
    failed = 0

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        existing_embeddings = select(PostEmbedding.post_id)
        stmt = (
            select(Post, LlmAnalysis)
            .join(LlmAnalysis, Post.id == LlmAnalysis.post_id)
            .where(Post.id.notin_(existing_embeddings))
            .limit(50)
        )

        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            logger.info("No posts pending embedding generation")
            return {"embedded": 0, "failed": 0}

        logger.info("Found %d posts pending embedding generation", len(rows))

        for post, analysis in rows:
            embed_text = post.content
            if analysis.talking_points:
                embed_text += " " + " ".join(analysis.talking_points)

            vector = await client.embed(embed_text[:2000])

            if vector is None:
                failed += 1
                logger.warning("Embedding failed for post %s", post.source_id)
                continue

            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(PostEmbedding).values(
                post_id=post.id,
                embedding=vector,
                model_used=client.model,
            ).on_conflict_do_nothing(index_elements=["post_id"])

            await session.execute(stmt)
            await session.commit()
            embedded += 1

    logger.info("Embedding generation complete: embedded=%d failed=%d", embedded, failed)
    return {"embedded": embedded, "failed": failed}


@app.task(bind=True, max_retries=3, default_retry_delay=120)
def cluster_narratives(self) -> dict:
    try:
        return asyncio.run(_cluster_narratives_async())
    except Exception as exc:
        logger.exception("Narrative clustering task failed")
        raise self.retry(exc=exc)


async def _cluster_narratives_async() -> dict:
    from sqlalchemy import select
    from criba.db.connection import get_async_session_factory
    from criba.db.models import Post
    from criba.engine.narrative import NarrativeEngine

    session_factory = get_async_session_factory()

    async with session_factory() as session:
        project_ids = [
            row[0] for row in
            (await session.execute(select(Post.project_id).distinct())).all()
        ]

    total_result = {"clustered": 0, "new_narratives": 0, "updated_narratives": 0}

    for project_id in project_ids:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            engine = NarrativeEngine(session=session)
            result = await engine.cluster_posts(project_id=project_id)
            for key in total_result:
                total_result[key] += result.get(key, 0)

    logger.info("Narrative clustering result: %s", total_result)
    return total_result


@app.task(bind=True, max_retries=3, default_retry_delay=120)
def detect_campaigns(self) -> dict:
    try:
        return asyncio.run(_detect_campaigns_async())
    except Exception as exc:
        logger.exception("Campaign detection task failed")
        raise self.retry(exc=exc)


async def _detect_campaigns_async() -> dict:
    from sqlalchemy import select
    from criba.db.connection import get_async_session_factory
    from criba.engine.narrative import NarrativeEngine
    from criba.db.models import Campaign, Post, SystemSetting

    session_factory = get_async_session_factory()

    async with session_factory() as session:
        existing_ids = set(
            row[0] for row in (await session.execute(select(Campaign.id))).all()
        )

    async with session_factory() as session:
        project_ids = [
            row[0] for row in
            (await session.execute(select(Post.project_id).distinct())).all()
        ]

    total_result = {"detected": 0, "skipped": 0}

    for project_id in project_ids:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            engine = NarrativeEngine(session=session)
            result = await engine.detect_campaigns(project_id=project_id)
            for key in total_result:
                total_result[key] += result.get(key, 0)

    if total_result.get("detected", 0) > 0:
        async with session_factory() as session:
            all_ids = set(
                row[0] for row in (await session.execute(select(Campaign.id))).all()
            )
            new_ids = all_ids - existing_ids

            if new_ids:
                _sess_factory = get_async_session_factory()
                async with _sess_factory() as _session:
                    _result = await _session.execute(
                        select(SystemSetting.value).where(SystemSetting.key == "confidence_threshold")
                    )
                    threshold = float(_result.scalar_one_or_none() or "0.85")

                for campaign_id in new_ids:
                    campaign = await session.get(Campaign, campaign_id)
                    if campaign and (campaign.confidence or 0) >= threshold:
                        from criba.worker.alerts import send_campaign_alert
                        alert_payload = {
                            "id": str(campaign.id),
                            "label": campaign.label,
                            "confidence": campaign.confidence,
                            "platforms": campaign.platforms,
                            "account_count": campaign.account_count,
                            "post_count": campaign.post_count,
                            "detected_at": campaign.detected_at.isoformat() if campaign.detected_at else "",
                        }
                        send_campaign_alert.delay(alert_payload)
                        try:
                            from criba.utils.alerts_bus import publish_alert
                            await publish_alert(
                                "campaign_detected",
                                f"Campaign detected: {campaign.label or 'unnamed campaign'}",
                                alert_payload,
                            )
                        except Exception:
                            logger.exception("Failed to publish campaign alert to the live bus")
                        logger.info("Triggered alert for campaign %s (confidence=%.2f)", campaign.id, campaign.confidence)

    logger.info("Campaign detection result: %s", total_result)
    return total_result
