import os

from celery import Celery

from criba.config import CribaConfig, load_infra_config

app = Celery("criba")


def _build_beat_schedule(config: CribaConfig) -> dict:
    """Build the beat schedule from the infra-only settings in criba.yml."""
    default_intervals = {
        "telegram": 60.0,
        "rss": 300.0,
        "reddit": 120.0,
        "bluesky": 120.0,
        "youtube": 900.0,
    }

    schedule: dict = {}
    for name, default_interval in default_intervals.items():
        source = getattr(config.sources, name, None)
        if source is None or not source.enabled:
            continue
        interval = float(source.poll_interval or default_interval)
        schedule[f"ingest-{name}"] = {
            "task": "criba.worker.tasks.ingest_source",
            "schedule": interval,
            "kwargs": {"source_name": name},
        }

    schedule.update(
        {
            "analyze-flagged": {
                "task": "criba.llm.tasks.analyze_flagged_posts",
                "schedule": 120.0,
            },
            "generate-embeddings": {
                "task": "criba.engine.tasks.generate_post_embeddings",
                "schedule": 180.0,
            },
            "cluster-narratives": {
                "task": "criba.engine.tasks.cluster_narratives",
                "schedule": 300.0,
            },
            "detect-campaigns": {
                "task": "criba.engine.tasks.detect_campaigns",
                "schedule": 600.0,
            },
        }
    )
    return schedule


_infra_config = load_infra_config()

app.conf.update(
    broker_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    result_backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=_infra_config.general.timezone,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule=_build_beat_schedule(_infra_config),
)

app.autodiscover_tasks(["criba.plugins"])
app.autodiscover_tasks(["criba.worker"])
app.autodiscover_tasks(["criba.llm"])
app.autodiscover_tasks(["criba.engine"])
