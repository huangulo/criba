import asyncio
import logging

from criba.celery_app import app

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3, default_retry_delay=120)
def analyze_flagged_posts(self) -> dict:
    try:
        return asyncio.run(_analyze_flagged_posts_async())
    except Exception as exc:
        logger.exception("LLM analysis task failed")
        raise self.retry(exc=exc)


async def _author_network_evidence(session, post) -> dict:
    """Summarize the author's persisted interaction edges.

    The author_graph primary key leads with (project_id, source,
    source_author), so this lookup is index-backed.
    """
    from sqlalchemy import func, select

    from criba.db.models import AuthorGraph

    stmt = select(
        func.count(func.distinct(AuthorGraph.target_author)),
        func.coalesce(func.sum(AuthorGraph.weight), 0),
    ).where(
        AuthorGraph.project_id == post.project_id,
        AuthorGraph.source == post.source,
        AuthorGraph.source_author == post.author_id,
    )
    targets, weight = (await session.execute(stmt)).one()
    return {"targets": int(targets), "weight": int(weight)}


async def _analyze_flagged_posts_async() -> dict:
    from datetime import datetime, timezone

    from sqlalchemy import select
    from criba.db.connection import get_async_session_factory
    from criba.db.models import HeuristicScore, LlmAnalysis, Post
    from criba.llm.client import OllamaClient
    from criba.llm.prompt import build_analysis_prompt

    client = OllamaClient()

    available = await client.is_available()
    if not available:
        logger.warning("Ollama not available at %s, skipping analysis", client._host)
        return {"error": "ollama unavailable"}

    analyzed = 0
    failed = 0

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        analyzed_post_ids = select(LlmAnalysis.post_id).where(LlmAnalysis.post_id.isnot(None))
        stmt = (
            select(Post, HeuristicScore)
            .join(HeuristicScore, Post.id == HeuristicScore.post_id)
            .where(HeuristicScore.sent_to_llm == True)
            .where(Post.id.notin_(analyzed_post_ids))
            .limit(50)
        )

        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            logger.info("No flagged posts pending LLM analysis")
            return {"analyzed": 0, "failed": 0}

        logger.info("Found %d posts pending LLM analysis", len(rows))

        for post, score in rows:
            account_age_days = (
                (datetime.now(timezone.utc) - post.author_created).days
                if post.author_created
                else None
            )
            network = await _author_network_evidence(session, post)

            prompt = build_analysis_prompt(
                source=post.source,
                content=post.content,
                evidence={
                    "author_handle": post.author_handle,
                    "account_age_days": account_age_days,
                    "language": post.language,
                    "copypasta_similarity": score.copypasta_score,
                    "temporal_anomaly": score.temporal_anomaly,
                    "account_age_flag": score.account_age_flag,
                    "composite_score": score.composite_score,
                    "interaction_targets": network["targets"],
                    "interaction_weight": network["weight"],
                    "hashtags": (post.hashtags or [])[:15],
                    "mentions": (post.mentions or [])[:15],
                    "engagement": {
                        key: value
                        for key, value in (post.engagement or {}).items()
                        if isinstance(value, (int, float)) and not isinstance(value, bool)
                    },
                    "media_count": len(post.media_urls or []),
                    "is_reply": bool(post.reply_to),
                    "published_at": post.published_at.isoformat(),
                },
            )

            llm_response = await client.analyze(prompt)

            if llm_response is None:
                failed += 1
                logger.warning("LLM returned no response for post %s", post.source_id)
                continue

            coordination_prob = llm_response.get("coordination_probability", 0.0)
            if isinstance(coordination_prob, str):
                try:
                    coordination_prob = float(coordination_prob)
                except (ValueError, TypeError):
                    coordination_prob = 0.0
            elif not isinstance(coordination_prob, (int, float)):
                coordination_prob = 0.0

            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(LlmAnalysis).values(
                post_id=post.id,
                coordination_probability=min(1.0, max(0.0, coordination_prob)),
                reasoning=str(llm_response.get("reasoning", ""))[:2000],
                narrative_category=llm_response.get("narrative_category"),
                talking_points=llm_response.get("talking_points_extracted", []),
                recommended_action=llm_response.get("recommended_action"),
                model_used=client.model,
            ).on_conflict_do_nothing(index_elements=["post_id"])

            await session.execute(stmt)
            await session.commit()
            analyzed += 1

            logger.info(
                "Post %s analyzed: coordination=%.2f category=%s action=%s",
                post.source_id,
                coordination_prob,
                llm_response.get("narrative_category"),
                llm_response.get("recommended_action"),
            )

    logger.info("LLM analysis complete: analyzed=%d failed=%d", analyzed, failed)
    return {"analyzed": analyzed, "failed": failed}
