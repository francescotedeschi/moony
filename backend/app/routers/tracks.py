from fastapi import APIRouter, HTTPException

from app.catalog.loader import catalog_store
from app.catalog.motion import motion_for_track, motion_preview_curve, motion_summary
from app.matching.motion_match import best_target_entry_on_track, effective_segment_label
from app.models.api import TargetEntryRequest, TargetEntryResponse

router = APIRouter(tags=["tracks"])


def _get_track_or_404(track_id: str):
    track = catalog_store.catalog.get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return track


def _duration_sec(track) -> float:
    if track.duration_sec and track.duration_sec > 0:
        return track.duration_sec
    if track.segments:
        return max(s.t_end for s in track.segments) / 1000.0
    return 0.0


def _track_detail_payload(track) -> dict:
    segments = sorted(track.segments, key=lambda s: s.t_start)
    duration_ms = int(_duration_sec(track) * 1000) or max((s.t_end for s in segments), default=0)
    payload = {
        "id": track.id,
        "title": track.title,
        "artist": track.artist,
        "bpm": track.bpm,
        "duration_sec": _duration_sec(track),
        "duration_ms": duration_ms,
        "audio_url": track.audio_url,
        "has_motion": track.has_motion,
        **motion_summary(track.motion),
        "segments": [
            {
                "t_start": s.t_start,
                "t_end": s.t_end,
                "v": s.v,
                "ar": s.ar,
                "label": effective_segment_label(track, idx),
            }
            for idx, s in enumerate(segments)
        ],
    }
    if track.has_motion and track.motion:
        payload["motion"] = track.motion.model_dump()
    return payload


@router.get("/tracks/{track_id}")
async def get_track(track_id: str) -> dict:
    """Track detail: macro segments + optional precomputed motion timeline."""
    return _track_detail_payload(_get_track_or_404(track_id))


@router.get("/tracks/{track_id}/motion/preview")
async def get_track_motion_preview(track_id: str) -> list[dict]:
    """Downsampled motion curve for timeline UI overlay."""
    track = _get_track_or_404(track_id)
    duration_ms = int(_duration_sec(track) * 1000) or max(
        (s.t_end for s in track.segments), default=0
    )
    return motion_preview_curve(track.motion, duration_ms=duration_ms)


@router.get("/tracks/{track_id}/motion")
async def get_track_motion(track_id: str) -> dict:
    """Motion timeline only (large payload)."""
    track = _get_track_or_404(track_id)
    if not track.has_motion or not track.motion:
        raise HTTPException(status_code=404, detail="Track has no precomputed motion")
    return track.motion.model_dump()


@router.post("/tracks/{track_id}/target-entry", response_model=TargetEntryResponse)
async def resolve_target_entry(track_id: str, body: TargetEntryRequest) -> TargetEntryResponse:
    """Closest motion frame to the user pad target (optionally only after playhead)."""
    track = _get_track_or_404(track_id)
    after_t_sec = body.after_t_ms / 1000.0 if body.after_t_ms is not None else None
    start_ms, entry_va, idx = best_target_entry_on_track(
        track,
        body.target,
        after_t_sec=after_t_sec,
    )
    seg = track.segments[idx]
    return TargetEntryResponse(
        track_id=track.id,
        start_ms=start_ms,
        segment={
            "v": entry_va.v,
            "ar": entry_va.ar,
            "label": seg.label,
            "t_start": start_ms,
            "t_end": seg.t_end,
        },
    )


@router.get("/tracks/{track_id}/motion/at")
async def get_motion_at(track_id: str, t_sec: float = 0.0, interpolated: bool = True) -> dict:
    """Lookup motion state at playback time (uses fallback when motion absent)."""
    track = _get_track_or_404(track_id)
    sample = motion_for_track(
        motion=track.motion,
        segments=track.segments,
        duration_sec=_duration_sec(track),
        t_sec=t_sec,
        interpolated=interpolated,
    )
    return {
        "track_id": track.id,
        "has_motion": track.has_motion,
        "interpolated": interpolated,
        **sample.__dict__,
    }
