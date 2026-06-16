from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.catalog.loader import catalog_store
from app.config import get_settings
from app.play_stats import play_stats_store
from app.routers import audio, jamendo, lyrics, match, plays, system, tracks


@asynccontextmanager
async def lifespan(_app: FastAPI):
    catalog_store.load()
    play_stats_store.init()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Moony API",
        description="Emotion-driven music navigation — Musicathon edition",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router)
    app.include_router(plays.router)
    app.include_router(match.router)
    app.include_router(tracks.router)
    app.include_router(audio.router)
    app.include_router(lyrics.router)
    app.include_router(jamendo.router)

    return app


app = create_app()
