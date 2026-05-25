import asyncio
import json
import logging

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
