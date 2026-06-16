from fastapi import APIRouter

from app.catalog.loader import catalog_store
from app.play_stats import play_stats_store

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    stats = catalog_store.stats()
    return {
        "status": "ok",
        "service": "moony-api",
        "catalog": stats,
        "play_stats": play_stats_store.stats_summary(),
    }


@router.get("/catalog/stats")
async def catalog_stats() -> dict:
    return catalog_store.stats()
