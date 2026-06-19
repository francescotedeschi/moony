"""Build timeline payloads for track UI (now-playing, analyze overlay)."""

from __future__ import annotations

from app.matching.motion_match import effective_segment_label
from app.models.catalog import Track


def track_timeline_payload(track: Track) -> dict:
    segments = sorted(track.segments, key=lambda s: s.t_start)
    duration_ms = max((s.t_end for s in segments), default=0)
    duration_sec = (
        track.duration_sec if track.duration_sec and track.duration_sec > 0 else duration_ms / 1000.0
    )
    return {
        "track_id": track.id,
        "title": track.title,
        "artist": track.artist,
        "bpm": track.bpm,
        "duration_ms": duration_ms,
        "duration_sec": duration_sec,
        "musixmatch": track.musixmatch.model_dump() if track.musixmatch else None,
        "energy_curve": track.energy_curve,
        "energy_curve_timestamps_ms": track.energy_curve_timestamps_ms,
        "segments": [
            {
                "t_start": s.t_start,
                "t_end": s.t_end,
                "v": s.v,
                "ar": s.ar,
                "label": effective_segment_label(track, idx),
                "emotion_label": s.emotion_label or "",
                "description": s.description or "",
                "cyanite_mood_tag": s.cyanite_mood_tag or "",
                "cyanite_v": s.cyanite_v,
                "cyanite_ar": s.cyanite_ar,
            }
            for idx, s in enumerate(segments)
        ],
    }
