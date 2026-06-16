from fastapi import APIRouter, HTTPException

from app.catalog.loader import catalog_store
from app.config import get_settings
from app.matching.lyrics_sync import align_crossfade_to_line, pick_entry_anchor, pick_exit_anchor
from app.models.api import LyricsResponse, PrefetchLyricsRequest
from app.musixmatch.client import musixmatch_client

router = APIRouter(tags=["lyrics"])


def _lyrics_disabled() -> None:
    if not get_settings().musixmatch_api_key:
        raise HTTPException(
            status_code=503,
            detail="Musixmatch API key not configured — lyrics disabled",
        )


@router.get("/tracks/{track_id}/lyrics", response_model=LyricsResponse)
async def get_track_lyrics(track_id: str) -> LyricsResponse:
    _lyrics_disabled()
    track = catalog_store.catalog.get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    mm = track.musixmatch
    if not mm or not (mm.commontrack_id or mm.track_id):
        raise HTTPException(status_code=404, detail="No Musixmatch reference for track")

    result = await musixmatch_client.get_subtitle_lines(
        commontrack_id=mm.commontrack_id,
        track_id=mm.track_id,
    )
    source = "subtitle"
    if not result:
        result = await musixmatch_client.get_snippet(
            commontrack_id=mm.commontrack_id,
            track_id=mm.track_id,
        )
        source = "snippet"
    if not result:
        raise HTTPException(status_code=404, detail="Lyrics unavailable (restricted or missing)")

    lines, copyright_text, pixel, script = result
    return LyricsResponse(
        track_id=track_id,
        lines=lines,
        lyrics_copyright=copyright_text,
        pixel_tracking_url=pixel,
        script_tracking_url=script,
        source=source,
    )


@router.get("/tracks/{track_id}/analysis")
async def get_track_analysis(track_id: str) -> dict:
    _lyrics_disabled()
    track = catalog_store.catalog.get_track(track_id)
    if not track or not track.musixmatch or not track.musixmatch.track_id:
        raise HTTPException(status_code=404, detail="Track or Musixmatch ID not found")

    analysis = await musixmatch_client.get_analysis(track.musixmatch.track_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis unavailable")
    return {"track_id": track_id, "analysis": analysis}


@router.post("/prefetch/lyrics")
async def prefetch_lyrics(body: PrefetchLyricsRequest) -> dict:
    """L2 prefetch: lyric anchors per intent (Musixmatch live, session-only)."""
    _lyrics_disabled()
    current_id = body.current.get("track_id")
    current_t_ms = int(body.current.get("t_ms", 0))
    bar_ms = 2000

    current_track = catalog_store.catalog.get_track(current_id) if current_id else None
    current_lines: list = []
    if current_track and current_track.musixmatch:
        sub = await musixmatch_client.get_subtitle_lines(
            commontrack_id=current_track.musixmatch.commontrack_id,
            track_id=current_track.musixmatch.track_id,
        )
        if sub:
            current_lines = sub[0]

    exit_anchor = pick_exit_anchor(current_lines, current_t_ms) if current_lines else None

    enriched: dict[str, dict] = {}
    for intent_key, candidates in body.candidates_l1.items():
        if not candidates:
            continue
        top = candidates[0]
        target = catalog_store.catalog.get_track(top["track_id"])
        if not target or not target.musixmatch:
            continue

        if target.beat_grid:
            bar_ms = target.beat_grid.bar_ms

        sub = await musixmatch_client.get_subtitle_lines(
            commontrack_id=target.musixmatch.commontrack_id,
            track_id=target.musixmatch.track_id,
        )
        entry_anchor = None
        copyright_text = ""
        pixel = None
        if sub:
            lines, copyright_text, pixel, _ = sub
            entry_anchor = pick_entry_anchor(
                lines,
                top.get("audio_start_ms", 0),
                top.get("audio_start_ms", 0) + 60_000,
            )

        crossfade = None
        if exit_anchor and entry_anchor:
            crossfade = align_crossfade_to_line(
                exit_anchor["t_ms"],
                entry_anchor["t_ms"],
                top.get("audio_start_ms", 0),
                bar_ms=bar_ms,
            )

        analysis = None
        if target.musixmatch.track_id:
            analysis = await musixmatch_client.get_analysis(target.musixmatch.track_id)

        enriched[intent_key] = {
            "track_id": target.id,
            "title": target.title,
            "artist": target.artist,
            "score_l1": top.get("score"),
            "exit_anchor": exit_anchor,
            "entry_anchor": entry_anchor,
            "crossfade": crossfade,
            "lyrics_copyright": copyright_text,
            "pixel_tracking_url": pixel,
            "analysis": analysis,
        }

    return {"intents": enriched}
