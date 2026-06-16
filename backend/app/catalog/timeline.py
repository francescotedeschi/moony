"""Build timeline payloads for track UI (now-playing, analyze overlay)."""

from __future__ import annotations

from app.catalog.motion import motion_preview_curve, motion_summary
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
        "has_motion": track.has_motion,
        "musixmatch": track.musixmatch.model_dump() if track.musixmatch else None,
        **motion_summary(track.motion),
        "motion_preview": motion_preview_curve(track.motion, duration_ms=duration_ms),
        "segments": [
            {
                "t_start": s.t_start,
                "t_end": s.t_end,
                "v": s.v,
                "ar": s.ar,
                "label": effective_segment_label(track, idx),
                "emotion_label": s.emotion_label or "",
                "description": s.description or "",
                "moss_emotion_label": s.moss_emotion_label or "",
                "essentia_emotion_label": s.essentia_emotion_label or "",
            }
            for idx, s in enumerate(segments)
        ],
    }
