import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from criba.api.auth import require_api_key, require_api_key_ws
from criba.api.routes import router
from criba.api.ws import alerts_subscriber
from criba.api.ws import router as ws_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    subscriber = asyncio.create_task(alerts_subscriber(), name="alerts-subscriber")
    yield
    subscriber.cancel()
    with suppress(asyncio.CancelledError):
        await subscriber


def create_app() -> FastAPI:
    app = FastAPI(
        title="Criba",
        description="Narrative Intelligence & Astroturfing Detection Engine",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3030"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # When CRIBA_API_KEY is set, every route requires the key: REST via the
    # X-API-Key header, the WebSocket via ?api_key=. Unset, the API runs open.
    app.include_router(router, dependencies=[Depends(require_api_key)])
    app.include_router(ws_router, dependencies=[Depends(require_api_key_ws)])

    return app


app = create_app()
