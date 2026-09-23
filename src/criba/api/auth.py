"""API key authentication for the Criba API.

Set CRIBA_API_KEY to require callers to authenticate. REST routes require
the key in the X-API-Key header; the WebSocket requires it as the api_key
query parameter (browsers cannot set custom WebSocket headers). When
CRIBA_API_KEY is unset the API runs without authentication, e.g. for
local development.
"""

import hmac
import os

from fastapi import HTTPException, Request, WebSocket, WebSocketException


def _configured_api_key() -> str | None:
    return os.getenv("CRIBA_API_KEY") or None


async def require_api_key(request: Request) -> None:
    """FastAPI dependency: enforce the X-API-Key header when configured."""
    configured = _configured_api_key()
    if not configured:
        return
    provided = request.headers.get("X-API-Key")
    if not provided or not hmac.compare_digest(provided, configured):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def require_api_key_ws(websocket: WebSocket) -> None:
    """FastAPI dependency: enforce ?api_key= on the WebSocket when configured."""
    configured = _configured_api_key()
    if not configured:
        return
    provided = websocket.query_params.get("api_key")
    if not provided or not hmac.compare_digest(provided, configured):
        raise WebSocketException(code=4401, reason="Invalid or missing API key")
