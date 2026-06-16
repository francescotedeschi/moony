from fastapi import APIRouter, HTTPException

from app.catalog.loader import catalog_store
from app.play_stats import play_stats_store

router = APIRouter(tags=["plays"])


@router.get("/tracks/{track_id}/play-count")
async def get_track_play_count(track_id: str) -> dict:
    if not catalog_store.catalog.get_track(track_id):
        raise HTTPException(status_code=404, detail="Track not found")
    return {
        "track_id": track_id,
        "play_count": play_stats_store.get_play_count(track_id),
        "stats_enabled": play_stats_store.enabled,
    }


@router.post("/tracks/{track_id}/played")
async def record_track_played(track_id: str) -> dict:
    """Increment global play count when the client actually starts playback."""
    if not catalog_store.catalog.get_track(track_id):
        raise HTTPException(status_code=404, detail="Track not found")
    count = play_stats_store.record_play(track_id)
    return {
        "track_id": track_id,
        "play_count": count,
        "stats_enabled": play_stats_store.enabled,
    }
