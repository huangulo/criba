import asyncio
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone

from criba.celery_app import app

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
    from criba.db.models import AuthorGraph, HeuristicScore, Post, ProjectTarget
    from criba.filters.scoring import create_pipeline, get_scoring_settings
    from criba.plugins.registry import get_plugin
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    plugin = get_plugin(source_name)

    if plugin is None:
        logger.error("No plugin found for source: %s", source_name)
        return {"error": f"no plugin for {source_name}"}

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        targets_stmt = select(ProjectTarget).where(ProjectTarget.platform == source_name)
        targets_result = await session.execute(targets_stmt)
        targets = targets_result.scalars().all()

    if not targets:
        logger.info("No active targets for source %s, skipping", source_name)
        return {"error": f"no targets for {source_name}"}

    targets_by_project: dict = defaultdict(list)
    for t in targets:
        targets_by_project[t.project_id].append(t)

    settings = await get_scoring_settings()
    pipeline = create_pipeline(**settings)

    total = 0
    inserted = 0
    duplicates = 0
    flagged_for_llm = 0

    for project_id, project_targets in targets_by_project.items():
        channels = [t.value for t in project_targets if t.target_type == "handle"]
        keywords = [t.value for t in project_targets if t.target_type == "keyword"]

        if source_name == "rss":
            source_config = {
                "feeds": [
                    {
                        "name": url.split("//")[1].split("/")[0] if "//" in url else url,
                        "url": url,
                    }
                    for url in keywords
                ],
                "poll_interval": 60,
            }
        elif source_name == "reddit":
            source_config = {
                "subreddits": channels + keywords,
                "poll_interval": 60,
            }
        elif source_name == "bluesky":
            source_config = {
                "keywords": keywords,
                "handles": channels,
                "poll_interval": 60,
            }
        elif source_name in ("telegram", "youtube"):
            source_config = {
                "channels": channels,
                "poll_interval": 60,
            }
        else:
            source_config = {
                "channels": channels,
                "keywords": keywords,
                "poll_interval": 60,
            }

        logger.info("Ingesting %s for project %s", source_name, project_id)
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            async for raw_post in plugin.stream(source_config):
                total += 1

                insert_stmt = pg_insert(Post).values(
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
                    project_id=project_id,
                )
                insert_stmt = insert_stmt.on_conflict_do_nothing(
                    index_elements=["source", "source_id", "project_id"]
                ).returning(Post.id)
                post_id = (await session.execute(insert_stmt)).scalar_one_or_none()

                if post_id is None:
                    duplicates += 1
                    continue

                inserted += 1

                pipeline_result = await pipeline.run(raw_post)

                copypasta_score = pipeline_result.filter_results.get("copypasta")
                temporal = pipeline_result.filter_results.get("temporal_anomaly")
                account_age = pipeline_result.filter_results.get("account_age")

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

                # The post, its heuristic score, and its graph edges commit as
                # one transaction: a failure rolls the insert back too, so a
                # retry re-ingests and re-scores the post instead of skipping
                # it as a duplicate forever.
                await session.commit()

                if pipeline_result.should_send_to_llm:
                    flagged_for_llm += 1
                    logger.info(
                        "Post %s flagged for LLM in project %s (score=%.3f)",
                        raw_post.source_id, project_id, pipeline_result.composite_score,
                    )

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
