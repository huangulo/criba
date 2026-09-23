"""Redis pub/sub bus for live alert events (worker -> API -> dashboard)."""

import json
import logging
import os

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

ALERTS_CHANNEL = "criba:alerts"


async def publish_alert(event_type: str, message: str, data: dict) -> None:
    """Publish an alert event so connected dashboards receive it live.

    Best effort: a Redis outage must never fail campaign detection, so
    publish errors are logged and swallowed by the caller's guard.
    """
    payload = json.dumps({"event_type": event_type, "message": message, "data": data})
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    client = aioredis.from_url(url)
    try:
        await client.publish(ALERTS_CHANNEL, payload)
    finally:
        await client.aclose()
