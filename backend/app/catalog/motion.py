"""
Runtime motion lookup — precomputed catalog timelines only.

segments[] = macro waypoints (overview, chapters, matching).
motion.*   = smooth playback trajectory (UI, animations).

Do not recompute motion server-side; use catalog builder (moodpad-catalog).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.catalog import TrackMotion

if TYPE_CHECKING:
    from app.models.catalog import Segment

MOOD_TOLERANCE = 0.01
DEFAULT_VALENCE = 0.0
DEFAULT_AROUSAL = 0.3
DEFAULT_MOOD = 50.0
DEFAULT_ENERGY = 0.5
DEFAULT_VOCAL = 0.5


@dataclass(frozen=True)
class MotionSample:
    t_sec: float
    energy: float
    vocal: float
    valence: float
    arousal: float
    mood: float


def expected_motion_length(duration_sec: float, hop_sec: float) -> int:
    """Sample count from moodpad-catalog timeline (arange + optional endpoint)."""
    if duration_sec <= 0 or hop_sec <= 0:
        return 1
    n = int(math.floor(duration_sec / hop_sec)) + 1
    last_t = (n - 1) * hop_sec
    if last_t < duration_sec - 1e-6:
        n += 1
    return max(1, n)


def motion_index_at_sec(motion: TrackMotion, t_sec: float) -> int:
    idx = int(math.floor(t_sec / motion.hop_sec))
    return max(0, min(idx, len(motion.energy) - 1))


def motion_at_sec(motion: TrackMotion, t_sec: float) -> MotionSample:
    i = motion_index_at_sec(motion, t_sec)
    return MotionSample(
        t_sec=i * motion.hop_sec,
        energy=motion.energy[i],
        vocal=motion.vocal[i],
        valence=motion.valence_smooth[i],
        arousal=motion.arousal_smooth[i],
        mood=motion.mood[i],
    )


def motion_at_sec_interpolated(motion: TrackMotion, t_sec: float) -> MotionSample:
    n = len(motion.energy)
    if n == 0:
        return motion_fallback_at_sec([], 0.0, t_sec)
    if n == 1:
        return motion_at_sec(motion, t_sec)

    pos = max(0.0, t_sec / motion.hop_sec)
    i0 = max(0, min(int(math.floor(pos)), n - 1))
    i1 = min(i0 + 1, n - 1)
    f = max(0.0, min(1.0, pos - i0)) if i1 > i0 else 0.0

    def lerp(a: float, b: float) -> float:
        return a + (b - a) * f

    return MotionSample(
        t_sec=t_sec,
        energy=lerp(motion.energy[i0], motion.energy[i1]),
        vocal=lerp(motion.vocal[i0], motion.vocal[i1]),
        valence=lerp(motion.valence_smooth[i0], motion.valence_smooth[i1]),
        arousal=lerp(motion.arousal_smooth[i0], motion.arousal_smooth[i1]),
        mood=lerp(motion.mood[i0], motion.mood[i1]),
    )


def _va_from_segments(segments: list[Segment], t_sec: float) -> tuple[float, float]:
    ms = int(max(0.0, t_sec) * 1000)
    if not segments:
        return DEFAULT_VALENCE, DEFAULT_AROUSAL
    ordered = sorted(segments, key=lambda s: s.t_start)
    for seg in ordered:
        if seg.t_start <= ms < seg.t_end:
            return seg.v, seg.ar
    last = ordered[-1]
    return last.v, last.ar


def motion_fallback_at_sec(
    segments: list[Segment],
    duration_sec: float,
    t_sec: float,
) -> MotionSample:
    """Degrade: linear V/A from segments, else flat defaults."""
    t = max(0.0, min(t_sec, duration_sec) if duration_sec > 0 else t_sec)
    if segments:
        v, ar = _va_from_segments(segments, t)
    else:
        v, ar = DEFAULT_VALENCE, DEFAULT_AROUSAL
    mood = 50.0 + 25.0 * v + 25.0 * ar
    return MotionSample(
        t_sec=t,
        energy=DEFAULT_ENERGY,
        vocal=DEFAULT_VOCAL,
        valence=v,
        arousal=ar,
        mood=mood,
    )


def motion_for_track(
    *,
    motion: TrackMotion | None,
    segments: list[Segment],
    duration_sec: float,
    t_sec: float,
    interpolated: bool = True,
) -> MotionSample:
    if motion is not None and len(motion.energy) > 0:
        if interpolated:
            return motion_at_sec_interpolated(motion, t_sec)
        return motion_at_sec(motion, t_sec)
    return motion_fallback_at_sec(segments, duration_sec, t_sec)


def motion_summary(motion: TrackMotion | None) -> dict:
    if motion is None or not motion.energy:
        return {"has_motion": False, "motion_hop_sec": None, "motion_samples": 0}
    return {
        "has_motion": True,
        "motion_hop_sec": motion.hop_sec,
        "motion_samples": len(motion.energy),
    }


def motion_preview_curve(
    motion: TrackMotion | None,
    *,
    duration_ms: int,
    max_points: int = 96,
) -> list[dict[str, float | int]]:
    """
    Downsampled valence timeline for UI overlay (y in 0..1, t_ms along track).
    """
    if motion is None or not motion.valence_smooth or duration_ms <= 0:
        return []

    vals = motion.valence_smooth
    n = len(vals)
    step = max(1, n // max(1, max_points))
    out: list[dict[str, float | int]] = []
    ars = motion.arousal_smooth
    for i in range(0, n, step):
        t_ms = int(round(i * motion.hop_sec * 1000))
        if t_ms > duration_ms:
            break
        v = float(vals[i])
        ar = float(ars[i]) if i < len(ars) else 0.0
        # Blend V/A so the overlay line moves visibly (not flat valence-only).
        y = 0.45 * ((v + 1.0) / 2.0) + 0.55 * ((ar + 1.0) / 2.0)
        out.append({"t_ms": t_ms, "y": round(y, 4)})
    if out and out[-1]["t_ms"] != duration_ms:
        last_v = float(vals[-1])
        last_ar = float(ars[-1]) if ars else 0.0
        y_end = 0.45 * ((last_v + 1.0) / 2.0) + 0.55 * ((last_ar + 1.0) / 2.0)
        out.append({"t_ms": duration_ms, "y": round(y_end, 4)})
    return out
