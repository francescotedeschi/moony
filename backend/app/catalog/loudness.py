"""YouTube-style playback gain from precomputed catalog loudness (EBU R128)."""

from __future__ import annotations

import math

from app.models.catalog import Track

YOUTUBE_TARGET_LUFS = -14.0
YOUTUBE_TRUE_PEAK_DBTP = -1.0
MAX_ANALYZE_SEC = 90


def compute_youtube_playback_gain(integrated_lufs: float, true_peak_dbfs: float) -> float:
    """Attenuate if louder than -14 LUFS; never boost; cap true peak at -1 dBTP."""
    gain_db = 0.0
    if integrated_lufs > YOUTUBE_TARGET_LUFS:
        gain_db = YOUTUBE_TARGET_LUFS - integrated_lufs
    linear = 10 ** (gain_db / 20)
    peak_after_dbfs = true_peak_dbfs + 20 * math.log10(linear) if linear > 0 else true_peak_dbfs
    if peak_after_dbfs > YOUTUBE_TRUE_PEAK_DBTP:
        linear = 10 ** ((YOUTUBE_TRUE_PEAK_DBTP - true_peak_dbfs) / 20)
    return max(0.0, min(1.0, linear))


def is_plausible_lufs(lufs: float) -> bool:
    return math.isfinite(lufs) and -45 <= lufs <= -5


def youtube_gain_for_track(track: Track) -> float | None:
    """Precomputed gain for the whole track, or None if not in catalog."""
    if track.loudness is None:
        return None
    return track.loudness.youtube_gain


def youtube_gain_for_start(track: Track, _start_ms: int = 0) -> float | None:
    """Same as track-level gain (start_ms ignored)."""
    return youtube_gain_for_track(track)
