import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from criba.api.routes import router
from criba.api.ws import router as ws_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Criba",
        description="Narrative Intelligence & Astroturfing Detection Engine",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3030"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(ws_router)

    return app


app = create_app()
