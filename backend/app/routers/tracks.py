from fastapi import APIRouter, HTTPException

from app.catalog.energy import (
    energy_preview_curve,
    energy_sample_at_sec,
    energy_summary,
    track_has_energy_curve,
)
from app.catalog.loader import catalog_store
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
        **energy_summary(track),
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
    if track_has_energy_curve(track):
        payload["energy_curve"] = list(track.energy_curve)
        payload["energy_curve_timestamps_ms"] = list(track.energy_curve_timestamps_ms)
    return payload


@router.get("/tracks/{track_id}")
async def get_track(track_id: str) -> dict:
    """Track detail: macro segments + optional Cyanite energy curve."""
    return _track_detail_payload(_get_track_or_404(track_id))


@router.get("/tracks/{track_id}/energy/preview")
async def get_track_energy_preview(track_id: str) -> list[dict]:
    """Downsampled Cyanite energy curve for timeline UI."""
    track = _get_track_or_404(track_id)
    duration_ms = int(_duration_sec(track) * 1000) or max(
        (s.t_end for s in track.segments), default=0
    )
    return energy_preview_curve(track, duration_ms=duration_ms)


@router.get("/tracks/{track_id}/energy")
async def get_track_energy(track_id: str) -> dict:
    """Full Cyanite energy curve (values + millisecond timestamps)."""
    track = _get_track_or_404(track_id)
    if not track_has_energy_curve(track):
        raise HTTPException(status_code=404, detail="Track has no Cyanite energy curve")
    return {
        "track_id": track.id,
        "energy_curve": list(track.energy_curve),
        "energy_curve_timestamps_ms": list(track.energy_curve_timestamps_ms),
    }


@router.post("/tracks/{track_id}/target-entry", response_model=TargetEntryResponse)
async def resolve_target_entry(track_id: str, body: TargetEntryRequest) -> TargetEntryResponse:
    """Closest segment entry to the user pad target (optionally only after playhead)."""
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


@router.get("/tracks/{track_id}/energy/at")
async def get_energy_at(track_id: str, t_sec: float = 0.0) -> dict:
    """Cyanite energy + section V/A at playback time."""
    track = _get_track_or_404(track_id)
    sample = energy_sample_at_sec(track, t_sec)
    return {
        "track_id": track.id,
        "has_energy_curve": track_has_energy_curve(track),
        "t_sec": sample.t_sec,
        "energy": sample.energy,
        "valence": sample.valence,
        "arousal": sample.arousal,
    }
