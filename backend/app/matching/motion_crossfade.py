"""Crossfade timing and tempo ramps from segment V/A and Cyanite energy."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.catalog.energy import energy_sample_at_sec
from app.matching.beat_align import (
    bar_align_duration_ms,
    bar_ms_for_track,
    beat_grid_for_bpm,
    compute_crossfade_start_ms,
    snap_entry_ms,
)
from app.matching.motion_match import BPM_RATE_MAX, BPM_RATE_MIN, dj_playback_rates, va_at_track_time
from app.models.catalog import BeatGrid, Track, VA

CROSSFADE_MS_MIN = 900
CROSSFADE_MS_MAX = 5500
CROSSFADE_BARS_MIN = 1.0
CROSSFADE_BARS_MAX = 4.5
MOOD_JUMP_EQUAL_POWER = 0.28
ENERGY_JUMP_EQUAL_POWER = 0.22


@dataclass(frozen=True)
class MotionCrossfadePlan:
    crossfade_ms: int
    curve: str
    playback_rate_start: float
    playback_rate_end: float
    playback_rate_out_end: float
    mood_jump: float
    energy_delta: float
    crossfade_start_ms: int | None = None
    entry_ms_aligned: int | None = None


@dataclass(frozen=True)
class BeatAlignedTransition:
    plan: MotionCrossfadePlan
    entry_ms: int


def bar_ms(bpm: int, beat_grid: BeatGrid | None = None) -> int:
    return beat_grid_for_bpm(bpm, beat_grid)


def _energy_at_track_time(track: Track, t_sec: float) -> float | None:
    if not track.has_energy_curve:
        return None
    return float(energy_sample_at_sec(track, t_sec).energy)


def motion_crossfade_plan(
    *,
    bpm_from: int,
    bpm_to: int,
    exit_va: VA | None,
    entry_va: VA,
    exit_energy: float | None = None,
    entry_energy: float | None = None,
    bar_ms_dest: int | None = None,
) -> MotionCrossfadePlan:
    """
    Derive crossfade length and volume curve from mood/energy delta at the transition.
    Tempo ramps stay BPM-synced; small arousal nudges on rate_start.
    """
    rate_start, rate_end = dj_playback_rates(bpm_from, bpm_to)
    out_end = 1.0
    if bpm_from > 0 and bpm_to > 0:
        out_end = max(BPM_RATE_MIN, min(BPM_RATE_MAX, bpm_to / bpm_from))
        out_end = round(out_end, 4)

    mood_jump = 0.4
    if exit_va is not None:
        mood_jump = math.hypot(entry_va.v - exit_va.v, entry_va.ar - exit_va.ar)

    energy_delta = 0.0
    if exit_energy is not None and entry_energy is not None:
        energy_delta = entry_energy - exit_energy

    bars = CROSSFADE_BARS_MIN + mood_jump * 2.4 + abs(energy_delta) * 1.6
    if energy_delta < -0.18:
        bars += 0.35
    bars = max(CROSSFADE_BARS_MIN, min(CROSSFADE_BARS_MAX, bars))

    dest_bar = bar_ms_dest if bar_ms_dest and bar_ms_dest > 0 else bar_ms(bpm_to)
    fade_ms = int(dest_bar * bars)
    fade_ms = bar_align_duration_ms(
        fade_ms, dest_bar, min_ms=CROSSFADE_MS_MIN, max_ms=CROSSFADE_MS_MAX
    )

    curve = "linear"
    if mood_jump >= MOOD_JUMP_EQUAL_POWER or abs(energy_delta) >= ENERGY_JUMP_EQUAL_POWER:
        curve = "equal_power"

    if exit_va is not None:
        ar_delta = entry_va.ar - exit_va.ar
        if ar_delta > 0.12:
            rate_start = round(min(BPM_RATE_MAX, rate_start * 1.025), 4)
        elif ar_delta < -0.12:
            rate_start = round(max(BPM_RATE_MIN, rate_start * 0.975), 4)

    return MotionCrossfadePlan(
        crossfade_ms=fade_ms,
        curve=curve,
        playback_rate_start=rate_start,
        playback_rate_end=rate_end,
        playback_rate_out_end=out_end,
        mood_jump=round(mood_jump, 4),
        energy_delta=round(energy_delta, 4),
    )


def crossfade_plan_between_tracks(
    *,
    from_track: Track | None,
    from_t_ms: int | None,
    to_track: Track,
    entry_ms: int,
    entry_va: VA,
    bpm_from: int,
    bpm_to: int,
) -> BeatAlignedTransition:
    exit_va: VA | None = None
    exit_energy: float | None = None
    if from_track is not None and from_t_ms is not None:
        t_sec = from_t_ms / 1000.0
        exit_va = va_at_track_time(from_track, t_sec)
        exit_energy = _energy_at_track_time(from_track, t_sec)

    aligned_entry = snap_entry_ms(entry_ms, to_track)
    entry_energy = _energy_at_track_time(to_track, aligned_entry / 1000.0)

    plan = motion_crossfade_plan(
        bpm_from=bpm_from,
        bpm_to=bpm_to,
        exit_va=exit_va,
        entry_va=entry_va,
        exit_energy=exit_energy,
        entry_energy=entry_energy,
        bar_ms_dest=bar_ms_for_track(to_track),
    )

    crossfade_start: int | None = None
    if from_track is not None and from_t_ms is not None:
        crossfade_start = compute_crossfade_start_ms(
            from_t_ms, plan.crossfade_ms, from_track
        )

    plan = MotionCrossfadePlan(
        crossfade_ms=plan.crossfade_ms,
        curve=plan.curve,
        playback_rate_start=plan.playback_rate_start,
        playback_rate_end=plan.playback_rate_end,
        playback_rate_out_end=plan.playback_rate_out_end,
        mood_jump=plan.mood_jump,
        energy_delta=plan.energy_delta,
        crossfade_start_ms=crossfade_start,
        entry_ms_aligned=aligned_entry,
    )
    return BeatAlignedTransition(plan=plan, entry_ms=aligned_entry)
