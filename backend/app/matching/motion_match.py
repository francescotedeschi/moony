"""Motion-aware V/A lookup and DJ transition helpers for matching."""

from __future__ import annotations

import math

from app.catalog.motion import motion_at_sec_interpolated, motion_for_track, motion_index_at_sec
from app.matching.beat_align import snap_entry_ms
from app.matching.emotions import emotion_label_for_va, normalize_emotion_label

from app.models.catalog import Segment, Track, Transition, VA

ENTRY_WINDOW_SEC = 45.0
BPM_RATE_MIN = 0.85
BPM_RATE_MAX = 1.15
# Cross-track / new-track entry: not first section; section start within first 40% of song
MAX_ENTRY_POSITION_FRACTION = 0.4


def track_duration_sec(track: Track) -> float:
    if track.duration_sec and track.duration_sec > 0:
        return float(track.duration_sec)
    if track.segments:
        return max(s.t_end for s in track.segments) / 1000.0
    return 0.0


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def va_at_track_time(track: Track, t_sec: float) -> VA:
    sample = motion_for_track(
        motion=track.motion,
        segments=track.segments,
        duration_sec=track_duration_sec(track),
        t_sec=max(0.0, t_sec),
        interpolated=True,
    )
    return VA(v=sample.valence, ar=sample.arousal)


def effective_match_position(
    pad_position: VA,
    current_track: Track | None,
    current_t_ms: int | None,
) -> VA:
    """User emotion target from the pad (filled pointer). Live song mood is scored via current_va elsewhere."""
    _ = current_track, current_t_ms
    return VA(v=_clamp(pad_position.v), ar=_clamp(pad_position.ar))


def seek_direction(
    target: VA,
    current_va: VA | None,
    drag_direction: VA,
    *,
    min_drag: float = 0.06,
) -> VA:
    """Vector from current song mood toward user target (not last pointer delta)."""
    if current_va is not None:
        return VA(v=_clamp(target.v - current_va.v), ar=_clamp(target.ar - current_va.ar))
    drag_mag = math.hypot(drag_direction.v, drag_direction.ar)
    if drag_mag >= min_drag:
        return VA(v=_clamp(drag_direction.v), ar=_clamp(drag_direction.ar))
    target_mag = math.hypot(target.v, target.ar)
    if target_mag < 1e-4:
        return VA(v=0.0, ar=0.0)
    scale = min(1.0, target_mag)
    return VA(v=_clamp(target.v / target_mag * scale), ar=_clamp(target.ar / target_mag * scale))


def va_at_segment_entry(track: Track, seg: Segment) -> VA:
    return va_at_track_time(track, seg.t_start / 1000.0)


def motion_transition_vector(from_va: VA, to_va: VA) -> VA:
    return VA(v=_clamp(to_va.v - from_va.v), ar=_clamp(to_va.ar - from_va.ar))


def segment_index_at_ms(track: Track, ms: int) -> int:
    for idx, seg in enumerate(track.segments):
        if seg.t_start <= ms < seg.t_end:
            return idx
    return max(0, len(track.segments) - 1)


def segment_is_outro(seg: Segment) -> bool:
    """Label-only check (prefer segment_is_outro_at when track context is available)."""
    return (seg.label or "").strip().lower() == "outro"


def segment_is_outro_at(track: Track, idx: int) -> bool:
    """Tagged outro, or the last segment when the track has more than one section."""
    segs = track.segments
    if idx < 0 or idx >= len(segs):
        return False
    if segment_is_outro(segs[idx]):
        return True
    return len(segs) > 1 and idx == len(segs) - 1


def effective_segment_label(track: Track, idx: int) -> str:
    seg = track.segments[idx]
    if segment_is_outro_at(track, idx):
        return "outro"
    return seg.label or ""


def without_outro_indices(track: Track, indices: list[int]) -> list[int]:
    return [i for i in indices if i < len(track.segments) and not segment_is_outro_at(track, i)]


def session_opener_entry(
    track: Track,
    emotion_label: str,
) -> tuple[Segment, int, int, VA] | None:
    """
    Session start: enter at the first catalog segment (index 0) when it matches mood.
    """
    if not track.segments or segment_is_outro_at(track, 0):
        return None
    want = emotion_label.strip().lower()
    seg = track.segments[0]
    if effective_segment_emotion_label(seg) != want:
        return None
    start_ms = snap_entry_ms(int(seg.t_start), track)
    entry_va = va_at_track_time(track, start_ms / 1000.0)
    return seg, 0, start_ms, entry_va


def segment_entry_eligible(track: Track, seg_idx: int) -> bool:
    """Entry segment must not be the first; its start must be within the first 40% of the track."""
    if seg_idx <= 0 or seg_idx >= len(track.segments):
        return False
    dur = track_duration_sec(track)
    if dur <= 0:
        return False
    start_sec = track.segments[seg_idx].t_start / 1000.0
    return start_sec <= dur * MAX_ENTRY_POSITION_FRACTION


def eligible_entry_indices(track: Track, indices: list[int]) -> list[int]:
    return [i for i in indices if segment_entry_eligible(track, i)]


_LEGACY_LABEL_REMAP: dict[str, str] = {
    "calm":    "chilled",
    "joy":     "happy",
    "energy":  "energetic",
    "tension": "tense",
    # "sad" is unchanged
}


def effective_segment_emotion_label(seg: Segment) -> str:
    for field in (seg.emotion_label, seg.moss_emotion_label):
        lab = (field or "").strip().lower()
        if lab:
            return _LEGACY_LABEL_REMAP.get(lab, lab)
    return emotion_label_for_va(VA(v=seg.v, ar=seg.ar))


def _matching_segment_indices(track: Track, emotion_label: str) -> list[int]:
    want = normalize_emotion_label(emotion_label)
    if not want:
        return list(range(len(track.segments)))
    out: list[int] = []
    for idx, seg in enumerate(track.segments):
        if effective_segment_emotion_label(seg) == want:
            out.append(idx)
    return without_outro_indices(track, out)


def _ms_in_matching_segment(track: Track, t_ms: int, match_indices: list[int]) -> bool:
    return any(
        track.segments[i].t_start <= t_ms < track.segments[i].t_end for i in match_indices
    )


def motion_va_at_segment_start(track: Track, seg_idx: int) -> VA:
    """V/A from the motion timeline at the start of a catalog segment."""
    if seg_idx < 0 or seg_idx >= len(track.segments):
        seg = track.segments[max(0, len(track.segments) - 1)]
        return VA(v=seg.v, ar=seg.ar)
    seg = track.segments[seg_idx]
    return va_at_track_time(track, seg.t_start / 1000.0)


def upcoming_segment_indices(track: Track, t_ms: int) -> list[int]:
    """Segment indices after playhead, never including outro."""
    if not track.segments:
        return []
    idx = segment_index_at_ms(track, t_ms)
    return without_outro_indices(track, list(range(idx + 1, len(track.segments))))


def clamp_start_ms_before_outro(track: Track, start_ms: int) -> int:
    """Ensure playback never begins inside an outro segment."""
    if not track.segments:
        return start_ms
    idx = segment_index_at_ms(track, start_ms)
    if not segment_is_outro_at(track, idx):
        return start_ms
    for j in range(idx - 1, -1, -1):
        if not segment_is_outro_at(track, j):
            return track.segments[j].t_start
    return 0


def _best_motion_entry_in_segments(
    track: Track,
    target: VA,
    segment_indices: list[int],
    *,
    after_t_sec: float | None = None,
) -> tuple[int, VA, int] | None:
    """Closest motion frame inside ``segment_indices`` (no emotion_label filter)."""
    segment_indices = eligible_entry_indices(track, without_outro_indices(track, segment_indices))
    if not segment_indices:
        return None

    if not track.has_motion or not track.motion:
        best_i = segment_indices[0]
        best_d = 1e9
        for i in segment_indices:
            seg = track.segments[i]
            d = math.hypot(target.v - seg.v, target.ar - seg.ar)
            if d < best_d:
                best_d, best_i = d, i
        seg = track.segments[best_i]
        return seg.t_start, VA(v=seg.v, ar=seg.ar), best_i

    motion = track.motion
    duration = track_duration_sec(track)
    i_lo = 0
    if after_t_sec is not None:
        i_lo = motion_index_at_sec(motion, min(max(0.0, after_t_sec), duration))
    i_hi = motion_index_at_sec(motion, duration)

    best_i: int | None = None
    best_dist = 1e9
    for i in range(i_lo, i_hi + 1):
        t_ms = int(round(i * motion.hop_sec * 1000))
        if not _ms_in_matching_segment(track, t_ms, segment_indices):
            continue
        v = motion.valence_smooth[i]
        ar = motion.arousal_smooth[i]
        dist = math.hypot(target.v - v, target.ar - ar)
        if dist < best_dist:
            best_dist = dist
            best_i = i

    if best_i is None:
        best_i = segment_indices[0]
        seg = track.segments[best_i]
        return seg.t_start, va_at_track_time(track, seg.t_start / 1000.0), best_i

    t_sec = best_i * motion.hop_sec
    sample = motion_at_sec_interpolated(motion, t_sec)
    start_ms = clamp_start_ms_before_outro(track, int(round(t_sec * 1000)))
    entry_va = VA(v=sample.valence, ar=sample.arousal)
    return start_ms, entry_va, segment_index_at_ms(track, start_ms)


def best_target_entry_for_emotion(
    track: Track,
    target: VA,
    emotion_label: str,
    *,
    after_t_sec: float | None = None,
    only_segment_indices: list[int] | None = None,
) -> tuple[int, VA, int] | None:
    """
    Closest motion frame to target inside segments with ``emotion_label``.
    When ``only_segment_indices`` is set, search is limited to those sections
    (e.g. upcoming segments on the current track).
    """
    match_idx = _matching_segment_indices(track, emotion_label)
    if only_segment_indices is not None:
        allowed = set(without_outro_indices(track, only_segment_indices))
        match_idx = [i for i in match_idx if i in allowed]
    else:
        match_idx = eligible_entry_indices(track, match_idx)
    if not match_idx:
        # Never fall back to a different mood (e.g. joy after calm on same track).
        return None

    if not track.has_motion or not track.motion:
        best_i = match_idx[0]
        best_d = 1e9
        for i in match_idx:
            seg = track.segments[i]
            d = math.hypot(target.v - seg.v, target.ar - seg.ar)
            if d < best_d:
                best_d, best_i = d, i
        seg = track.segments[best_i]
        return seg.t_start, VA(v=seg.v, ar=seg.ar), best_i

    motion = track.motion
    duration = track_duration_sec(track)
    i_lo = 0
    if after_t_sec is not None:
        i_lo = motion_index_at_sec(motion, min(max(0.0, after_t_sec), duration))
    i_hi = motion_index_at_sec(motion, duration)

    best_i: int | None = None
    best_dist = 1e9
    for i in range(i_lo, i_hi + 1):
        t_ms = int(round(i * motion.hop_sec * 1000))
        if not _ms_in_matching_segment(track, t_ms, match_idx):
            continue
        v = motion.valence_smooth[i]
        ar = motion.arousal_smooth[i]
        dist = math.hypot(target.v - v, target.ar - ar)
        if dist < best_dist:
            best_dist = dist
            best_i = i

    if best_i is None:
        best_i = match_idx[0]
        seg = track.segments[best_i]
        return seg.t_start, va_at_track_time(track, seg.t_start / 1000.0), best_i

    t_sec = best_i * motion.hop_sec
    sample = motion_at_sec_interpolated(motion, t_sec)
    start_ms = clamp_start_ms_before_outro(track, int(round(t_sec * 1000)))
    entry_va = VA(v=sample.valence, ar=sample.arousal)
    return start_ms, entry_va, segment_index_at_ms(track, start_ms)


def best_target_entry_on_track(
    track: Track,
    target: VA,
    *,
    after_t_sec: float | None = None,
) -> tuple[int, VA, int]:
    """
    Closest motion frame to user target on the full track timeline.
    Returns (start_ms, entry_va, segment_idx).
    """
    if not track.segments:
        raise ValueError("track has no segments")

    eligible = eligible_entry_indices(
        track, without_outro_indices(track, list(range(len(track.segments))))
    )
    if not eligible:
        raise ValueError("track has no eligible entry segments")

    if not track.has_motion or not track.motion:
        best_i = eligible[0]
        best_dist = 1e9
        for idx in eligible:
            seg = track.segments[idx]
            dist = math.hypot(target.v - seg.v, target.ar - seg.ar)
            if dist < best_dist:
                best_dist = dist
                best_i = idx
        seg = track.segments[best_i]
        return seg.t_start, VA(v=seg.v, ar=seg.ar), best_i

    motion = track.motion
    duration = track_duration_sec(track)
    i_lo = 0
    if after_t_sec is not None:
        i_lo = motion_index_at_sec(motion, min(max(0.0, after_t_sec), duration))
    i_hi = motion_index_at_sec(motion, duration)

    best_i: int | None = None
    best_dist = 1e9
    for i in range(i_lo, i_hi + 1):
        t_ms = int(round(i * motion.hop_sec * 1000))
        if not _ms_in_matching_segment(track, t_ms, eligible):
            continue
        v = motion.valence_smooth[i]
        ar = motion.arousal_smooth[i]
        dist = math.hypot(target.v - v, target.ar - ar)
        if dist < best_dist:
            best_dist = dist
            best_i = i

    if best_i is None:
        best_i = eligible[0]
        seg = track.segments[best_i]
        return seg.t_start, VA(v=seg.v, ar=seg.ar), best_i

    t_sec = best_i * motion.hop_sec
    sample = motion_at_sec_interpolated(motion, t_sec)
    start_ms = clamp_start_ms_before_outro(track, int(round(t_sec * 1000)))
    entry_va = VA(v=sample.valence, ar=sample.arousal)
    return start_ms, entry_va, segment_index_at_ms(track, start_ms)


def refine_entry_ms(
    track: Track,
    seg: Segment,
    target: VA,
    *,
    window_sec: float = ENTRY_WINDOW_SEC,
) -> tuple[int, VA]:
    """Pick closest target mood frame on the full track motion timeline."""
    _ = seg, window_sec
    start_ms, entry_va, _ = best_target_entry_on_track(track, target)
    return start_ms, entry_va


def dj_playback_rates(bpm_from: int, bpm_to: int) -> tuple[float, float]:
    """
    Incoming track starts synced to outgoing tempo, eases to native BPM.
    Returns (playback_rate_start, playback_rate_end) for the entering deck.
    """
    if bpm_to <= 0:
        return 1.0, 1.0
    start = bpm_from / bpm_to
    start = max(BPM_RATE_MIN, min(BPM_RATE_MAX, start))
    return round(start, 4), 1.0


def transition_from_stored_or_motion(
    track: Track,
    seg_idx: int,
    entry_va: VA,
    current_va: VA | None,
) -> Transition | None:
    if current_va is not None:
        delta = motion_transition_vector(current_va, entry_va)
        return Transition(from_seg=max(0, seg_idx - 1), to_seg=seg_idx, dv=delta.v, dar=delta.ar)
    if seg_idx < len(track.transitions):
        t = track.transitions[seg_idx]
        if t.to_seg == seg_idx or t.from_seg == seg_idx - 1:
            return t
    if track.transitions and seg_idx > 0:
        for t in track.transitions:
            if t.to_seg == seg_idx:
                return t
    return None
