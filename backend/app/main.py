from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.db import initialize_database
from app.search.bm25 import BM25IndexCache


@asynccontextmanager
async def lifespan(application: FastAPI):
    initialize_database(application.state.settings.database_path)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(
        title="MemoryScope API",
        description="Local API for MemoryScope.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = settings or get_settings()
    application.state.bm25_cache = BM25IndexCache()

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(application.state.settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
