import httpx
from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings

router = APIRouter(prefix="/jamendo", tags=["jamendo"])

JAMENDO_BASE = "https://api.jamendo.com/v3.0"


@router.get("/tracks")
async def search_tracks(
    tags: str = Query(default="calm"),
    limit: int = Query(default=20, le=50),
) -> dict:
    """Proxy Jamendo API (CORS bypass for frontend / pipeline tooling)."""
    client_id = get_settings().jamendo_client_id
    if not client_id:
        raise HTTPException(status_code=503, detail="JAMENDO_CLIENT_ID not configured")

    params = {
        "client_id": client_id,
        "format": "json",
        "limit": limit,
        "tags": tags,
        "include": "musicinfo",
        "audioformat": "mp32",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(f"{JAMENDO_BASE}/tracks/", params=params)
        resp.raise_for_status()
        return resp.json()
