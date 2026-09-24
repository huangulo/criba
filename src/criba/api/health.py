"""Unauthenticated infrastructure health probe.

Mounted without the API-key dependency on purpose: docker healthchecks
and load balancers must be able to probe without carrying credentials.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 5.0


async def _check_postgres() -> str:
    from sqlalchemy import text

    from criba.db.connection import get_async_session_factory

    try:
        async def _probe() -> None:
            async with get_async_session_factory()() as session:
                await session.execute(text("SELECT 1"))

        # A down database can hang a connect for a long time; a health
        # probe must answer fast, so bound the wait explicitly.
        await asyncio.wait_for(_probe(), timeout=CHECK_TIMEOUT_SECONDS)
        return "ok"
    except Exception:  # any failure means the dependency is down
        logger.exception("Health check: postgres unreachable")
        return "down"


async def _check_redis() -> str:
    from redis import asyncio as aioredis

    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = aioredis.from_url(url, socket_timeout=CHECK_TIMEOUT_SECONDS)
        try:
            await client.ping()
        finally:
            await client.aclose()
        return "ok"
    except Exception:  # any failure means the dependency is down
        logger.exception("Health check: redis unreachable at %s", url)
        return "down"


async def _check_ollama() -> str:
    from criba.llm.client import OllamaClient

    # is_available() already bounds itself with a 5s httpx timeout and
    # swallows its own errors; an unavailable Ollama is a degradation,
    # not an outage, since the API serves fine without it.
    try:
        return "ok" if await OllamaClient().is_available() else "down"
    except Exception:  # any failure means the dependency is down
        logger.exception("Health check: ollama probe failed")
        return "down"


@router.get("/health")
async def health() -> JSONResponse:
    """Report dependency status.

    200 when core dependencies (postgres, redis) are up — including a
    degraded state where only Ollama is offline — and 503 when a core
    dependency is down.
    """
    postgres, redis, ollama = await asyncio.gather(
        _check_postgres(),
        _check_redis(),
        _check_ollama(),
    )
    dependencies = {"postgres": postgres, "redis": redis, "ollama": ollama}

    core_up = postgres == "ok" and redis == "ok"
    if not core_up:
        status = "down"
    elif ollama == "ok":
        status = "ok"
    else:
        status = "degraded"

    body = {
        "status": status,
        "dependencies": dependencies,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    return JSONResponse(body, status_code=200 if core_up else 503)
