import asyncio
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone

from criba.celery_app import app
from criba.config import load_config

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_source(self, source_name: str) -> dict:
    try:
        return asyncio.run(_ingest_source_async(source_name))
    except Exception as exc:
        logger.exception("Ingestion failed for %s", source_name)
        raise self.retry(exc=exc)


async def _ingest_source_async(source_name: str) -> dict:
    from criba.db.connection import get_async_session_factory
    from criba.db.models import AuthorGraph, HeuristicScore, Post
    from criba.filters.scoring import create_pipeline
    from criba.plugins.registry import get_plugin
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    config = load_config()
    plugin = get_plugin(source_name)

    if plugin is None:
        logger.error("No plugin found for source: %s", source_name)
        return {"error": f"no plugin for {source_name}"}

    source_dataclass = getattr(config.sources, source_name, None)

    if source_dataclass is None or not getattr(source_dataclass, "enabled", False):
        logger.info("Source %s is not enabled, skipping", source_name)
        return {"error": f"source {source_name} not enabled"}

    source_config = asdict(source_dataclass)
    pipeline = create_pipeline()

    total = 0
    inserted = 0
    duplicates = 0
    flagged_for_llm = 0

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        async for raw_post in plugin.stream(source_config):
            total += 1

            stmt = pg_insert(Post).values(
                source=raw_post.source,
                source_id=raw_post.source_id,
                author_id=raw_post.author_id,
                author_handle=raw_post.author_handle,
                author_created=raw_post.author_created_at,
                content=raw_post.content,
                language=raw_post.language,
                published_at=raw_post.published_at,
                url=raw_post.url,
                engagement=raw_post.engagement,
                hashtags=raw_post.hashtags,
                mentions=raw_post.mentions,
                reply_to=raw_post.reply_to,
                raw_metadata=raw_post.raw_metadata,
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=["source", "source_id"])
            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount > 0:
                inserted += 1

                pipeline_result = await pipeline.run(raw_post)

                copypasta_score = pipeline_result.filter_results.get("copypasta")
                temporal = pipeline_result.filter_results.get("temporal_anomaly")
                account_age = pipeline_result.filter_results.get("account_age")

                from sqlalchemy import select
                post_row = await session.execute(
                    select(Post.id).where(
                        Post.source == raw_post.source,
                        Post.source_id == raw_post.source_id,
                    )
                )
                post_id = post_row.scalar_one_or_none()

                if post_id:
                    score_stmt = pg_insert(HeuristicScore).values(
                        post_id=post_id,
                        copypasta_score=copypasta_score.score if copypasta_score else 0.0,
                        temporal_anomaly=temporal.score if temporal else 0.0,
                        account_age_flag=account_age.score if account_age else 0.0,
                        composite_score=pipeline_result.composite_score,
                        sent_to_llm=pipeline_result.should_send_to_llm,
                    )
                    score_stmt = score_stmt.on_conflict_do_nothing()
                    await session.execute(score_stmt)
                    await session.commit()

                    network_result = pipeline_result.filter_results.get("network_graph")
                    if network_result and network_result.metadata.get("network_edges_to_persist"):
                        for edge_data in network_result.metadata["network_edges_to_persist"]:
                            edge_stmt = pg_insert(AuthorGraph).values(
                                source_author=edge_data["source"],
                                target_author=edge_data["target"],
                                interaction=edge_data["interaction"],
                                weight=1,
                            )
                            edge_stmt = edge_stmt.on_conflict_do_update(
                                index_elements=["source_author", "target_author", "interaction"],
                                set_={"weight": AuthorGraph.weight + 1, "last_seen": datetime.now(timezone.utc)}
                            )
                            await session.execute(edge_stmt)
                        await session.commit()

                    if pipeline_result.should_send_to_llm:
                        flagged_for_llm += 1
                        logger.info(
                            "Post %s flagged for LLM (score=%.3f)",
                            raw_post.source_id, pipeline_result.composite_score,
                        )
            else:
                duplicates += 1

    logger.info(
        "Ingestion %s complete: total=%d, inserted=%d, duplicates=%d, flagged_for_llm=%d",
        source_name, total, inserted, duplicates, flagged_for_llm,
    )
    return {
        "total": total,
        "inserted": inserted,
        "duplicates": duplicates,
        "flagged_for_llm": flagged_for_llm,
    }


def main():
    app.start(sys.argv[1:] if len(sys.argv) > 1 else ["worker", "-l", "info"])
