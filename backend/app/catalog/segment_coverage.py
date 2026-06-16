"""MOSS timeline quality checks for playback / matching."""

from __future__ import annotations

from app.matching.motion_match import track_duration_sec
from app.models.catalog import Track

MIN_NAVIGABLE_SEGMENTS = 2
MIN_MOSS_SPAN_MS = 30_000
MIN_MOSS_DURATION_FRACTION = 0.35


def track_moss_span_ms(track: Track) -> int:
    if not track.segments:
        return 0
    return max(s.t_end for s in track.segments)


def track_has_navigable_timeline(track: Track) -> bool:
    """
    True when the track has enough MOSS sections for section-aware playback.

    Filters incomplete MOSS runs (e.g. a single intro label on a 2+ minute preview).
    """
    if len(track.segments) < MIN_NAVIGABLE_SEGMENTS:
        return False
    moss_end_ms = track_moss_span_ms(track)
    if moss_end_ms < MIN_MOSS_SPAN_MS:
        return False
    duration_ms = int(track_duration_sec(track) * 1000)
    if duration_ms > 0 and moss_end_ms < duration_ms * MIN_MOSS_DURATION_FRACTION:
        return False
    return True
