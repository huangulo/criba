import asyncio
import contextlib
import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info("WebSocket client connected. Total: %d", len(self._connections))

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
        logger.info("WebSocket client disconnected. Total: %d", len(self._connections))

    async def broadcast(self, event_type: str, message: str, data: dict):
        payload = json.dumps({"event_type": event_type, "message": message, "data": data})
        disconnected = []
        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(payload)
                except Exception:
                    disconnected.append(ws)
        for ws in disconnected:
            await self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws/alerts")
async def alerts_ws(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)


async def broadcast_alert(event_type: str, message: str, data: dict):
    await manager.broadcast(event_type, message, data)


async def alerts_subscriber() -> None:
    """Relay alert events from the Redis pub/sub channel to connected dashboards.

    The worker publishes campaign alerts to Redis; this loop bridges them to
    every open WebSocket. It reconnects after failures so a Redis restart
    never takes the live-alert fan-out down with it.
    """
    from redis import asyncio as aioredis

    from criba.utils.alerts_bus import ALERTS_CHANNEL

    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    while True:
        client = None
        pubsub = None
        try:
            client = aioredis.from_url(url)
            pubsub = client.pubsub()
            await pubsub.subscribe(ALERTS_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    event = json.loads(message["data"])
                except (TypeError, ValueError):
                    logger.warning("Ignoring malformed alert event: %r", message.get("data"))
                    continue
                await manager.broadcast(
                    event.get("event_type", "alert"),
                    event.get("message", ""),
                    event.get("data") or {},
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Alerts Redis subscriber failed; retrying in 5s")
            await asyncio.sleep(5)
        finally:
            if pubsub is not None:
                with contextlib.suppress(Exception):
                    await pubsub.aclose()
            if client is not None:
                with contextlib.suppress(Exception):
                    await client.aclose()
