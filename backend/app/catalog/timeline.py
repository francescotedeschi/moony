"""Build timeline payloads for track UI (now-playing, analyze overlay)."""

from __future__ import annotations

from app.catalog.motion import motion_preview_curve, motion_summary
from app.matching.motion_match import effective_segment_label
from app.models.catalog import Track, TrackMotion


def _motion_series_arrays(
    motion: TrackMotion | None,
    values: list[float],
    duration_ms: int,
) -> tuple[list[float], list[int]]:
    if motion is None or not values:
        return [], []
    timestamps_ms = [
        int(round(i * motion.hop_sec * 1000)) for i in range(len(values))
    ]
    if duration_ms > 0:
        trimmed: list[float] = []
        trimmed_ts: list[int] = []
        for val, t_ms in zip(values, timestamps_ms):
            if t_ms > duration_ms:
                break
            trimmed.append(float(val))
            trimmed_ts.append(t_ms)
        if trimmed:
            return trimmed, trimmed_ts
    return [float(v) for v in values], timestamps_ms


def track_timeline_payload(track: Track) -> dict:
    segments = sorted(track.segments, key=lambda s: s.t_start)
    duration_ms = max((s.t_end for s in segments), default=0)
    duration_sec = (
        track.duration_sec if track.duration_sec and track.duration_sec > 0 else duration_ms / 1000.0
    )
    vocal_curve, vocal_curve_timestamps_ms = _motion_series_arrays(
        track.motion,
        list(track.motion.vocal) if track.motion else [],
        duration_ms,
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
        "energy_curve": track.energy_curve,
        "energy_curve_timestamps_ms": track.energy_curve_timestamps_ms,
        "vocal_curve": vocal_curve,
        "vocal_curve_timestamps_ms": vocal_curve_timestamps_ms,
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
                "cyanite_mood_tag": s.cyanite_mood_tag or "",
                "cyanite_v": s.cyanite_v,
                "cyanite_ar": s.cyanite_ar,
            }
            for idx, s in enumerate(segments)
        ],
    }
