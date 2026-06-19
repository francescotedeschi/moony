"""Cyanite energy_curve lookup for playback API."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.catalog import Segment, Track


@dataclass(frozen=True)
class EnergySample:
    t_sec: float
    energy: float
    valence: float
    arousal: float


def track_has_energy_curve(track: Track) -> bool:
    return (
        len(track.energy_curve) >= 2
        and len(track.energy_curve_timestamps_ms) >= 2
        and len(track.energy_curve) == len(track.energy_curve_timestamps_ms)
    )


def energy_at_time_ms(
    values: list[float],
    timestamps_ms: list[int],
    t_ms: float,
) -> float | None:
    if len(values) < 2 or len(values) != len(timestamps_ms):
        return None

    if t_ms <= timestamps_ms[0]:
        return float(values[0])
    last = len(values) - 1
    if t_ms >= timestamps_ms[last]:
        return float(values[last])

    for i in range(last):
        t0 = timestamps_ms[i]
        t1 = timestamps_ms[i + 1]
        if t_ms < t0 or t_ms > t1:
            continue
        span = t1 - t0
        if span <= 0:
            return float(values[i])
        u = (t_ms - t0) / span
        return float(values[i] + (values[i + 1] - values[i]) * u)

    return float(values[last])


def _va_from_segments(segments: list[Segment], t_sec: float) -> tuple[float, float]:
    ms = int(max(0.0, t_sec) * 1000)
    if not segments:
        return 0.0, 0.0
    ordered = sorted(segments, key=lambda s: s.t_start)
    for seg in ordered:
        if seg.t_start <= ms < seg.t_end:
            return float(seg.v), float(seg.ar)
    last = ordered[-1]
    return float(last.v), float(last.ar)


def energy_sample_at_sec(track: Track, t_sec: float) -> EnergySample:
    """Interpolate Cyanite energy and section V/A at playback time."""
    t = max(0.0, t_sec)
    t_ms = t * 1000.0
    energy_val = energy_at_time_ms(
        list(track.energy_curve),
        list(track.energy_curve_timestamps_ms),
        t_ms,
    )
    v, ar = _va_from_segments(track.segments, t)
    return EnergySample(
        t_sec=t,
        energy=float(energy_val if energy_val is not None else 0.5),
        valence=v,
        arousal=ar,
    )


def energy_summary(track: Track) -> dict:
    if not track_has_energy_curve(track):
        return {"has_energy_curve": False, "energy_samples": 0}
    return {
        "has_energy_curve": True,
        "energy_samples": len(track.energy_curve),
    }


def energy_preview_curve(
    track: Track,
    *,
    duration_ms: int,
    max_points: int = 96,
) -> list[dict[str, float | int]]:
    """Downsampled Cyanite energy for optional API consumers."""
    if not track_has_energy_curve(track) or duration_ms <= 0:
        return []

    values = track.energy_curve
    timestamps = track.energy_curve_timestamps_ms
    n = len(values)
    step = max(1, n // max(1, max_points))
    out: list[dict[str, float | int]] = []
    for i in range(0, n, step):
        t_ms = int(timestamps[i])
        if t_ms > duration_ms:
            break
        out.append({"t_ms": t_ms, "energy": round(float(values[i]), 4)})
    if out and out[-1]["t_ms"] != duration_ms:
        out.append(
            {
                "t_ms": duration_ms,
                "energy": round(float(values[-1]), 4),
            }
        )
    return out
