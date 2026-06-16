import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.catalog.loader import catalog_store

router = APIRouter(tags=["audio"])

ALLOWED_AUDIO_HOSTS = (
    "storage.jamendo.com",
    "prod-1.storage.jamendo.com",
    "mp3l.jamendo.com",
)

_UPSTREAM_TIMEOUT = httpx.Timeout(60.0, connect=15.0)
_CHUNK_SIZE = 65_536


@router.get("/tracks/{track_id}/audio")
async def stream_track_audio(track_id: str, request: Request) -> StreamingResponse:
    """Proxy Jamendo audio to avoid browser CORS blocks (forwards Range for seeking)."""
    track = catalog_store.catalog.get_track(track_id)
    if not track or not track.audio_url:
        raise HTTPException(status_code=404, detail="Track or audio URL not found")

    if not any(host in track.audio_url for host in ALLOWED_AUDIO_HOSTS):
        raise HTTPException(status_code=400, detail="Audio host not allowed")

    headers: dict[str, str] = {}
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    client = httpx.AsyncClient(timeout=_UPSTREAM_TIMEOUT, follow_redirects=True)
    try:
        upstream_req = client.build_request("GET", track.audio_url, headers=headers)
        upstream = await client.send(upstream_req, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Upstream audio failed: {exc}") from exc

    if upstream.status_code not in (200, 206):
        await upstream.aclose()
        await client.aclose()
        upstream.raise_for_status()

    out_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=300",
        "Content-Type": upstream.headers.get("content-type", "audio/mpeg"),
    }
    for key in ("Content-Length", "Content-Range"):
        if key in upstream.headers:
            out_headers[key] = upstream.headers[key]

    async def body():
        try:
            async for chunk in upstream.aiter_bytes(chunk_size=_CHUNK_SIZE):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        headers=out_headers,
    )
