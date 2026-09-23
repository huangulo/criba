"""Redis-backed persistence for stateful heuristic filters, scoped per project.

Stateful filters (deduplication, copypasta, temporal, hashtag, network) keep
72-hour corpora in memory. Celery runs in separate processes with round-robin
task routing, so that state must survive across polling runs and stay
isolated per project. Snapshots are pickled, compressed, and stored in Redis
under one key per project and filter, with a TTL that only reaps state for
deleted or long-idle projects.
"""

import logging
import os
import pickle
import uuid
import zlib

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

STATE_TTL_SECONDS = 7 * 24 * 3600


def _state_key(project_id: uuid.UUID, filter_name: str) -> str:
    return f"criba:filter_state:{project_id}:{filter_name}"


def _redis() -> aioredis.Redis:
    return aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def load_filter_state(project_id: uuid.UUID, filter_names: list[str]) -> dict:
    """Load the persisted state for the given filters; missing or corrupt entries are skipped."""
    client = _redis()
    try:
        values = await client.mget([_state_key(project_id, name) for name in filter_names])
    finally:
        await client.aclose()

    state: dict = {}
    for name, raw in zip(filter_names, values):
        if not raw:
            continue
        try:
            state[name] = pickle.loads(zlib.decompress(raw))
        except Exception:
            logger.warning("Discarding corrupt filter state for %s", name, exc_info=True)
    return state


async def save_filter_state(project_id: uuid.UUID, state: dict) -> None:
    """Persist per-filter state snapshots. An unpicklable filter only loses its own state."""
    client = _redis()
    try:
        for name, data in state.items():
            try:
                payload = zlib.compress(pickle.dumps(data))
            except Exception:
                logger.exception("Failed to serialize state for filter %s; skipping", name)
                continue
            await client.set(_state_key(project_id, name), payload, ex=STATE_TTL_SECONDS)
    finally:
        await client.aclose()


async def clear_filter_state(project_id: uuid.UUID) -> None:
    """Drop persisted state for a project, e.g. when the project is deleted."""
    client = _redis()
    try:
        keys = [key async for key in client.scan_iter(match=_state_key(project_id, "*"))]
        if keys:
            await client.delete(*keys)
    finally:
        await client.aclose()
