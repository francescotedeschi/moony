"""Beat-grid alignment for entry points and crossfade timing."""

from __future__ import annotations

import math

from app.models.catalog import BeatGrid, Track

ENTRY_SNAP_MAX_MS = 400


def bar_ms_for_track(track: Track) -> int:
    if track.beat_grid is not None and track.beat_grid.bar_ms > 0:
        return track.beat_grid.bar_ms
    return int(round((60_000.0 / max(40, track.bpm)) * 4))


def grid_offset_ms(track: Track) -> int:
    if track.beat_grid is not None:
        return max(0, track.beat_grid.offset_ms)
    return 0


def _bar_index(ms: int, offset: int, bar_ms: int) -> float:
    return (ms - offset) / bar_ms


def snap_ms_to_downbeat(
    ms: int,
    track: Track,
    *,
    prefer: str = "nearest",
) -> int:
    """Snap timestamp to a bar boundary on the track beat grid."""
    bar_ms = bar_ms_for_track(track)
    if bar_ms <= 0:
        return max(0, ms)
    offset = grid_offset_ms(track)
    rel = _bar_index(ms, offset, bar_ms)
    if prefer == "forward":
        idx = math.ceil(rel - 1e-9)
    elif prefer == "backward":
        idx = math.floor(rel + 1e-9)
    else:
        idx = round(rel)
    return max(0, offset + int(idx * bar_ms))


def snap_entry_ms(entry_ms: int, track: Track) -> int:
    """
    Snap mix entry to a downbeat. Prefer the next bar if within ENTRY_SNAP_MAX_MS.
    """
    bar_ms = bar_ms_for_track(track)
    forward = snap_ms_to_downbeat(entry_ms, track, prefer="forward")
    if 0 <= forward - entry_ms <= min(ENTRY_SNAP_MAX_MS, bar_ms // 2):
        return forward
    return snap_ms_to_downbeat(entry_ms, track, prefer="nearest")


def bar_align_duration_ms(fade_ms: int, bar_ms: int, *, min_ms: int, max_ms: int) -> int:
    """Round fade length to whole bars, clamped to min/max bar counts."""
    if bar_ms <= 0:
        return max(min_ms, min(max_ms, fade_ms))
    min_bars = max(1, (min_ms + bar_ms - 1) // bar_ms)
    max_bars = max(min_bars, max_ms // bar_ms)
    bars = max(min_bars, min(max_bars, round(fade_ms / bar_ms)))
    return bars * bar_ms


def compute_crossfade_start_ms(
    from_t_ms: int,
    fade_ms: int,
    from_track: Track,
) -> int:
    """
    When to start the outgoing fade on the current track (ms from track start).

    Ends the fade on the next downbeat after a short runway from the current position.
    """
    bar_ms = bar_ms_for_track(from_track)
    runway = max(bar_ms // 2, 300)
    fade_end = snap_ms_to_downbeat(from_t_ms + runway, from_track, prefer="forward")
    if fade_end <= from_t_ms:
        fade_end = from_t_ms + bar_ms
    start = max(from_t_ms, fade_end - fade_ms)
    snapped = snap_ms_to_downbeat(start, from_track, prefer="backward")
    if snapped < from_t_ms:
        snapped = snap_ms_to_downbeat(from_t_ms, from_track, prefer="forward")
    # Never schedule a fade start behind the playhead (client would spin until timeout).
    return max(from_t_ms, snapped)


def beat_grid_for_bpm(bpm: int, beat_grid: BeatGrid | None = None) -> int:
    if beat_grid is not None and beat_grid.bar_ms > 0:
        return beat_grid.bar_ms
    return int(round((60_000.0 / max(40, bpm)) * 4))
