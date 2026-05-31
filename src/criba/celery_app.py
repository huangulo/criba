import os

from celery import Celery

app = Celery("criba")

app.conf.update(
    broker_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    result_backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Bogota",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "ingest-telegram": {
            "task": "criba.worker.tasks.ingest_source",
            "schedule": 60.0,
            "kwargs": {"source_name": "telegram"},
        },
        "ingest-rss": {
            "task": "criba.worker.tasks.ingest_source",
            "schedule": 300.0,
            "kwargs": {"source_name": "rss"},
        },
        "ingest-reddit": {
            "task": "criba.worker.tasks.ingest_source",
            "schedule": 120.0,
            "kwargs": {"source_name": "reddit"},
        },
        "ingest-bluesky": {
            "task": "criba.worker.tasks.ingest_source",
            "schedule": 120.0,
            "kwargs": {"source_name": "bluesky"},
        },
        "ingest-youtube": {
            "task": "criba.worker.tasks.ingest_source",
            "schedule": 900.0,
            "kwargs": {"source_name": "youtube"},
        },
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
    },
)

app.autodiscover_tasks(["criba.plugins"])
app.autodiscover_tasks(["criba.worker"])
app.autodiscover_tasks(["criba.llm"])
app.autodiscover_tasks(["criba.engine"])
