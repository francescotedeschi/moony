"""
Emotion matching v3 — segment label + motion entry + embedding tie-break.

1. Map pad target → emotion_label (5 zones) + catalog search V/A
2. Blend search target toward motion at upcoming section boundaries on current track
3. Only tracks/entries inside segments with that emotion_label (upcoming-only on same track)
4. Entry time = closest motion frame to search target within those segments
5. Lookahead skip uses motion V/A at next two section starts vs pad target
6. Never enter or play outro — skip track if in/near outro; entry points exclude outro segments
7. Embedding: continuity vs current segment + alignment to target-mood profile on candidate track
8. Bonus score when ≥50% of track segments share the target emotion_label
9. Entry segment: not the first section; section start ≤ 40% of track duration
10. Client passes session ``exclude_ids`` — each track at most once per session
11. Global play counts (DB): never-played tracks win pool tier; sqrt penalty + tie-break on score
12. Segment-mood slot (intent 0): live playhead mood — not pad target; ≥0.5 mood_distribution when used
13. Session embedding penalties: early skip / same-mood handoff (≤15s) soft-push away similar embeddings;
    10-minute half-life decay on penalty strength
"""

from __future__ import annotations

import math
from typing import Iterable

from app.catalog.mood_distribution import mood_share_for_label, track_has_dominant_mood_share
from app.catalog.segment_coverage import track_has_navigable_timeline
from app.matching.emotions import (
    EMOTION_BRANCHES,
    SAME_MOOD_INTENT,
    branch_target_va,
    emotion_label_for_branch,
    emotion_label_for_va,
    resolve_search_target,
)
from app.matching.motion_crossfade import MotionCrossfadePlan, crossfade_plan_between_tracks
from app.play_stats.fairness import (
    play_fairness_pool_bonus,
    play_fairness_score_penalty,
    play_fairness_tier,
)
from app.matching.motion_match import (
    best_target_entry_for_emotion,
    effective_segment_emotion_label,
    motion_va_at_segment_start,
    segment_index_at_ms,
    segment_is_outro_at,
    session_opener_entry,
    upcoming_segment_indices,
    va_at_track_time,
)
from app.matching.embedding_penalties import WeightedEmbedding, embedding_penalty_adjustment
from app.models.catalog import Segment, Track, VA

MATCHER_VERSION = "v3"

SAME_TRACK_AHEAD_SEC = 0.5
PREFETCH_POOL = 120
TOP_K = 3
EMBEDDING_CONTINUITY_WEIGHT = 1.25
EMBEDDING_PROFILE_WEIGHT = 1.0
EMBEDDING_POOL_WEIGHT = 0.08
SECTION_BLEND_MAX = 0.45
SECTION_BLEND_WINDOW = 0.5
SECTION_TARGET_VA_DIST = 0.38

WEAK_MOOD_DISTANCE = 0.42
POOR_MOOD_DISTANCE = 0.58
TARGET_EMOTION_FRACTION = 0.5
TARGET_EMOTION_DEPTH_BONUS = 3.0


def euclidean(a: VA, b: VA) -> float:
    return math.hypot(a.v - b.v, a.ar - b.ar)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-9 or nb <= 1e-9:
        return 0.0
    return dot / (na * nb)


def bpm_compat(bpm_a: int, bpm_b: int) -> float:
    diff = abs(bpm_a - bpm_b)
    if diff <= 30:
        return 1.0 - diff / 30.0
    half = abs(bpm_a - bpm_b * 2)
    double = abs(bpm_a * 2 - bpm_b)
    best = min(diff, half, double)
    return max(0.0, 1.0 - best / 30.0)


def mood_quality(distance: float) -> str:
    if distance <= 0.22:
        return "excellent"
    if distance <= WEAK_MOOD_DISTANCE:
        return "good"
    if distance <= POOR_MOOD_DISTANCE:
        return "weak"
    return "poor"


def _current_segment(track: Track | None, t_ms: int | None) -> Segment | None:
    if track is None or t_ms is None or not track.segments:
        return None
    idx = segment_index_at_ms(track, t_ms)
    return track.segments[idx]


def _resolve_forward_search_target(
    user_target: VA,
    *,
    current_track: Track | None,
    current_t_ms: int | None,
) -> tuple[VA, str]:
    """
    Pad search target, blended toward motion at the next section boundary
    as the playhead nears the end of the current segment.
    """
    search_target, branch = resolve_search_target(user_target)
    target_label = emotion_label_for_branch(branch)
    if current_track is None or current_t_ms is None or not current_track.segments:
        return search_target, target_label

    idx = segment_index_at_ms(current_track, current_t_ms)
    if idx + 1 >= len(current_track.segments):
        return search_target, target_label

    cur = current_track.segments[idx]
    remaining = max(0, cur.t_end - current_t_ms)
    seg_len = max(1, cur.t_end - cur.t_start)
    progress = 1.0 - min(1.0, remaining / (SECTION_BLEND_WINDOW * seg_len))
    if progress <= 0:
        return search_target, target_label

    next_va = motion_va_at_segment_start(current_track, idx + 1)
    w = SECTION_BLEND_MAX * progress
    blended = VA(
        v=search_target.v * (1.0 - w) + next_va.v * w,
        ar=search_target.ar * (1.0 - w) + next_va.ar * w,
    )
    return blended, target_label


def _upcoming_section_matches_target(
    track: Track,
    seg_idx: int,
    target_label: str,
    target_va: VA,
) -> bool:
    """True when motion at section start aligns with pad target mood."""
    want = target_label.strip().lower()
    if not want:
        return False
    mva = motion_va_at_segment_start(track, seg_idx)
    if emotion_label_for_va(mva) == want:
        return True
    return euclidean(mva, target_va) <= SECTION_TARGET_VA_DIST


def _next_segment_is_outro(track: Track, t_ms: int) -> bool:
    """True when the segment immediately after the playhead is tagged outro."""
    if not track.segments:
        return False
    idx = segment_index_at_ms(track, t_ms)
    if idx + 1 >= len(track.segments):
        return False
    return segment_is_outro_at(track, idx + 1)


def _should_skip_current_track(
    track: Track,
    t_ms: int,
    target_label: str,
    target_va: VA,
) -> bool:
    """Exclude current song — outro must not play; pick another track, same target mood."""
    if not track.segments:
        return False
    idx = segment_index_at_ms(track, t_ms)
    if segment_is_outro_at(track, idx):
        return True
    if _next_segment_is_outro(track, t_ms):
        return True
    return _next_two_sections_leave_target(track, t_ms, target_label, target_va)


def _next_two_sections_leave_target(
    track: Track,
    t_ms: int,
    target_label: str,
    target_va: VA,
) -> bool:
    """
    True when the next two sections' motion at their starts both diverge
    from the pad target (timeline won't reach target mood soon).
    """
    if not track.segments:
        return False

    idx = segment_index_at_ms(track, t_ms)
    if idx + 2 >= len(track.segments):
        return False

    return all(
        not _upcoming_section_matches_target(track, j, target_label, target_va)
        for j in (idx + 1, idx + 2)
    )


def _effective_excludes_for_match(
    exclude_ids: set[str],
    *,
    current_track: Track | None,
    current_t_ms: int | None,
    target_emotion_label: str,
    target_va: VA,
) -> set[str]:
    """
    Skip the current track when the next segment is outro, or when the next two
    sections' motion both diverge from the pad target — then match another song
    with the same target mood.
    """
    out = set(exclude_ids)
    if current_track is None or current_t_ms is None:
        return out
    if _should_skip_current_track(
        current_track,
        current_t_ms,
        target_emotion_label,
        target_va,
    ):
        out.add(current_track.id)
    return out


def _min_motion_dist_for_emotion(
    track: Track,
    search_target: VA,
    emotion_label: str,
) -> float:
    label = emotion_label.strip().lower()
    match_indices = [
        i
        for i, s in enumerate(track.segments)
        if effective_segment_emotion_label(s) == label
    ]
    if not match_indices:
        return 1e9

    if track.has_motion and track.motion:
        motion = track.motion
        hop = motion.hop_sec
        best = 1e9
        for i in range(len(motion.valence_smooth)):
            t_ms = int(round(i * hop * 1000))
            if not any(
                track.segments[idx].t_start <= t_ms < track.segments[idx].t_end
                for idx in match_indices
            ):
                continue
            v = motion.valence_smooth[i]
            ar = motion.arousal_smooth[i]
            best = min(best, euclidean(search_target, VA(v=v, ar=ar)))
        return best

    best = 1e9
    for idx in match_indices:
        seg = track.segments[idx]
        best = min(best, euclidean(search_target, VA(v=seg.v, ar=seg.ar)))
    return best


def _same_mood_search_context(
    current_track: Track | None,
    current_t_ms: int | None,
) -> tuple[VA, VA, str] | None:
    """Segment mood at playhead (intent 0) — not pad target mood."""
    if current_track is None or current_t_ms is None:
        return None
    current_va = va_at_track_time(current_track, current_t_ms / 1000.0)
    cur_seg = _current_segment(current_track, current_t_ms)
    target_label = (
        (cur_seg.emotion_label or "").strip().lower()
        if cur_seg and cur_seg.emotion_label
        else emotion_label_for_va(current_va)
    )
    branch_target = current_va
    search_target = branch_target
    idx = segment_index_at_ms(current_track, current_t_ms)
    if idx + 1 < len(current_track.segments):
        next_va = motion_va_at_segment_start(current_track, idx + 1)
        search_target = VA(
            v=0.6 * branch_target.v + 0.4 * next_va.v,
            ar=0.6 * branch_target.ar + 0.4 * next_va.ar,
        )
    return branch_target, search_target, target_label


def _play_count_for(counts: dict[str, int], track_id: str) -> int:
    return int(counts.get(track_id, 0))


def _restrict_ranked_by_play_fairness(
    ranked: list[tuple[float, Track]],
    counts: dict[str, int],
) -> list[tuple[float, Track]]:
    """Keep never-played tracks when any exist; else the lowest play-count tier."""
    if not ranked or not counts:
        return ranked
    unplayed = [(dist, track) for dist, track in ranked if _play_count_for(counts, track.id) == 0]
    if unplayed:
        return unplayed
    min_plays = min(_play_count_for(counts, track.id) for _, track in ranked)
    return [
        (dist, track)
        for dist, track in ranked
        if play_fairness_tier(_play_count_for(counts, track.id), min_plays)
    ]


def _track_pool(
    tracks: list[Track],
    exclude_ids: set[str],
    search_target: VA,
    emotion_label: str,
    *,
    limit: int = PREFETCH_POOL,
    play_counts: dict[str, int] | None = None,
    restrict_mood_share: bool = False,
) -> list[Track]:
    counts = play_counts or {}
    ranked: list[tuple[float, Track]] = []
    for track in tracks:
        if track.id in exclude_ids or not track.segments:
            continue
        if not track_has_navigable_timeline(track):
            continue
        dist = _min_motion_dist_for_emotion(track, search_target, emotion_label)
        if dist >= 1e8:
            continue
        rank_adj = target_emotion_depth_bonus(track, emotion_label) * 0.04
        rank_adj += embedding_pool_bonus(track, emotion_label)
        if restrict_mood_share:
            rank_adj += mood_share_for_label(track, emotion_label) * 0.08
        rank_adj -= play_fairness_pool_bonus(counts.get(track.id, 0))
        ranked.append((dist - rank_adj, track))
    ranked.sort(key=lambda item: item[0])
    if restrict_mood_share:
        strong = [
            (dist, track)
            for dist, track in ranked
            if track_has_dominant_mood_share(track, emotion_label)
        ]
        if strong:
            ranked = strong
    ranked = _restrict_ranked_by_play_fairness(ranked, counts)
    return [track for _, track in ranked[:limit]]


def _entry_for_track(
    track: Track,
    search_target: VA,
    emotion_label: str,
    *,
    current_track_id: str | None,
    current_t_ms: int | None,
) -> tuple[int, VA, int] | None:
    after_t_sec: float | None = None
    only_segment_indices: list[int] | None = None
    if current_track_id and current_t_ms is not None and track.id == current_track_id:
        after_t_sec = current_t_ms / 1000.0 + SAME_TRACK_AHEAD_SEC
        upcoming = upcoming_segment_indices(track, current_t_ms)
        if upcoming:
            only_segment_indices = upcoming
    return best_target_entry_for_emotion(
        track,
        search_target,
        emotion_label,
        after_t_sec=after_t_sec,
        only_segment_indices=only_segment_indices,
    )


def count_segments_for_emotion(track: Track, emotion_label: str) -> int:
    want = emotion_label.strip().lower()
    return sum(
        1 for seg in track.segments if effective_segment_emotion_label(seg) == want
    )


def target_emotion_fraction(track: Track, emotion_label: str) -> float:
    if not track.segments:
        return 0.0
    return count_segments_for_emotion(track, emotion_label) / len(track.segments)


def target_emotion_depth_bonus(track: Track, emotion_label: str) -> float:
    """Prefer tracks where at least half of sections match the pad target mood."""
    if target_emotion_fraction(track, emotion_label) >= TARGET_EMOTION_FRACTION:
        return TARGET_EMOTION_DEPTH_BONUS
    return 0.0


def mean_embedding_for_emotion(track: Track, emotion_label: str) -> list[float] | None:
    """Average MOSS segment embedding for all sections with ``emotion_label``."""
    want = emotion_label.strip().lower()
    vectors = [
        list(seg.embedding)
        for seg in track.segments
        if effective_segment_emotion_label(seg) == want and seg.embedding
    ]
    if not vectors:
        return None
    dim = len(vectors[0])
    if any(len(v) != dim for v in vectors):
        return None
    acc = [0.0] * dim
    for vec in vectors:
        for i, x in enumerate(vec):
            acc[i] += x
    n = float(len(vectors))
    return [x / n for x in acc]


def embedding_pool_bonus(track: Track, emotion_label: str) -> float:
    """Boost prefetch pool rank when target-mood segments share a coherent embedding profile."""
    profile = mean_embedding_for_emotion(track, emotion_label)
    if not profile:
        return 0.0
    want = emotion_label.strip().lower()
    best = 0.0
    for seg in track.segments:
        if effective_segment_emotion_label(seg) != want or not seg.embedding:
            continue
        best = max(best, cosine_similarity(profile, list(seg.embedding)))
    return best * EMBEDDING_POOL_WEIGHT


def _score_candidate(
    user_target: VA,
    entry_va: VA,
    bpm_current: int,
    track_bpm: int,
    *,
    track: Track | None = None,
    target_emotion_label: str | None = None,
    current_embedding: list[float] | None,
    candidate_embedding: list[float] | None,
    play_count: int = 0,
    embedding_penalties: list[WeightedEmbedding] | None = None,
) -> tuple[float, float]:
    mood_dist = euclidean(user_target, entry_va)
    score = -mood_dist * 10.0 + bpm_compat(bpm_current, track_bpm) * 1.5
    score -= play_fairness_score_penalty(play_count)
    if current_embedding and candidate_embedding:
        score += EMBEDDING_CONTINUITY_WEIGHT * cosine_similarity(
            current_embedding, candidate_embedding
        )
    if embedding_penalties and candidate_embedding:
        score += embedding_penalty_adjustment(candidate_embedding, embedding_penalties)
    if track is not None and target_emotion_label and candidate_embedding:
        profile = mean_embedding_for_emotion(track, target_emotion_label)
        if profile:
            score += EMBEDDING_PROFILE_WEIGHT * cosine_similarity(
                candidate_embedding, profile
            )
    if track is not None and target_emotion_label:
        score += target_emotion_depth_bonus(track, target_emotion_label)
    return score, mood_dist


def _youtube_gain_field(track: Track, start_ms: int) -> dict[str, float]:
    from app.catalog.loudness import youtube_gain_for_track

    gain = youtube_gain_for_track(track)
    if gain is None:
        return {}
    return {"youtube_playback_gain": gain}


def _candidate_dict(
    track: Track,
    seg: Segment,
    idx: int,
    start_ms: int,
    entry_va: VA,
    score: float,
    mood_dist: float,
    *,
    target_emotion_label: str,
    crossfade: MotionCrossfadePlan | None = None,
) -> dict:
    out: dict = {
        "track_id": track.id,
        "title": track.title,
        "artist": track.artist,
        "bpm": track.bpm,
        "audio_url": track.audio_url,
        "segment_idx": idx,
        "audio_start_ms": start_ms,
        "score": round(score, 4),
        "mood_distance": round(mood_dist, 4),
        "mood_quality": mood_quality(mood_dist),
        "emotion_label": target_emotion_label,
        "matcher": MATCHER_VERSION,
        "segment": {
            "v": entry_va.v,
            "ar": entry_va.ar,
            "label": seg.label,
            "emotion_label": seg.emotion_label,
            "t_start": start_ms,
            "t_end": seg.t_end,
        },
        "musixmatch": track.musixmatch.model_dump() if track.musixmatch else None,
        **_youtube_gain_field(track, start_ms),
    }
    if crossfade is not None:
        out.update(
            {
                "crossfade_ms": crossfade.crossfade_ms,
                "crossfade_curve": crossfade.curve,
                "crossfade_mood_jump": crossfade.mood_jump,
                "crossfade_start_ms": crossfade.crossfade_start_ms,
                "playback_rate_start": crossfade.playback_rate_start,
                "playback_rate_end": crossfade.playback_rate_end,
                "playback_rate_out_end": crossfade.playback_rate_out_end,
            }
        )
    return out


def _match_exclude_attempts(
    effective_excludes: set[str],
    restrict_mood_share: bool,
    *,
    same_mood_handoff: bool,
    pad_only: bool,
    current_id: str | None,
) -> list[tuple[set[str], bool]]:
    """Progressive relax when the session pool is empty (allow replay, soften mood filter)."""
    attempts: list[tuple[set[str], bool]] = [(set(effective_excludes), restrict_mood_share)]
    if restrict_mood_share:
        attempts.append((set(effective_excludes), False))
    allow_replay = (
        same_mood_handoff
        or (current_id is not None and not pad_only)
        or (pad_only and len(effective_excludes) > 0)
    )
    if allow_replay:
        minimal: set[str] = set()
        if current_id:
            minimal.add(current_id)
        if minimal != effective_excludes:
            attempts.append((minimal, restrict_mood_share))
            if restrict_mood_share:
                attempts.append((minimal, False))
    seen: set[tuple[frozenset[str], bool]] = set()
    ordered: list[tuple[set[str], bool]] = []
    for ex, restrict in attempts:
        key = (frozenset(ex), restrict)
        if key in seen:
            continue
        seen.add(key)
        ordered.append((ex, restrict))
    return ordered


def _pick_best_from_pool(
    pool: list[Track],
    *,
    search_target: VA,
    target_label: str,
    user_target: VA,
    bpm_current: int,
    pad_only: bool,
    current_id: str | None,
    current_t_ms: int | None,
    effective_excludes: set[str],
    cur_emb: list[float] | None,
    counts: dict[str, int],
    embedding_penalties: list[WeightedEmbedding] | None = None,
) -> tuple[Track, Segment, int, float, int, VA, float, str, str] | None:
    best: tuple[Track, Segment, int, float, int, VA, float, str, str] | None = None
    want = target_label.strip().lower()

    for track in pool:
        use_same_track_ctx = (
            not pad_only
            and current_id is not None
            and track.id == current_id
            and track.id not in effective_excludes
        )
        entry = _entry_for_track(
            track,
            search_target,
            target_label,
            current_track_id=current_id if use_same_track_ctx else None,
            current_t_ms=current_t_ms if use_same_track_ctx else None,
        )
        if entry is None:
            continue
        start_ms, entry_va, idx = entry
        seg = track.segments[idx]
        if effective_segment_emotion_label(seg) != want:
            continue
        score, mood_dist = _score_candidate(
            user_target,
            entry_va,
            bpm_current,
            track.bpm,
            track=track,
            target_emotion_label=target_label,
            current_embedding=cur_emb,
            candidate_embedding=list(seg.embedding) if seg.embedding else None,
            play_count=counts.get(track.id, 0),
            embedding_penalties=embedding_penalties,
        )
        quality = mood_quality(mood_dist)

        if best is None:
            best = (track, seg, idx, score, start_ms, entry_va, mood_dist, quality, target_label)
        elif score > best[3]:
            best = (track, seg, idx, score, start_ms, entry_va, mood_dist, quality, target_label)
        elif score == best[3] and counts.get(track.id, 0) < counts.get(best[0].id, 0):
            best = (track, seg, idx, score, start_ms, entry_va, mood_dist, quality, target_label)

    return best


def find_best_match(
    tracks: Iterable[Track],
    user_target: VA,
    _direction: VA,
    bpm_current: int,
    exclude_ids: set[str],
    current_t_ms: int | None = None,
    *,
    current_track: Track | None = None,
    pad_only: bool = False,
    same_mood_handoff: bool = False,
    play_counts: dict[str, int] | None = None,
    embedding_penalties: list[WeightedEmbedding] | None = None,
) -> tuple[Track, Segment, int, float, int, VA, float, str, str] | None:
    """
    Returns (track, segment, seg_idx, score, start_ms, entry_va, mood_distance,
    mood_quality, target_emotion_label).
    """
    restrict_mood_share = False
    if same_mood_handoff:
        ctx = _same_mood_search_context(current_track, current_t_ms)
        if ctx is None:
            return None
        branch_target, search_target, target_label = ctx
        user_target = branch_target
        restrict_mood_share = True
    elif pad_only or current_track is None or current_t_ms is None:
        search_target, branch = resolve_search_target(user_target)
        target_label = emotion_label_for_branch(branch)
    else:
        search_target, target_label = _resolve_forward_search_target(
            user_target,
            current_track=current_track,
            current_t_ms=current_t_ms,
        )
    current_id = current_track.id if current_track else None
    cur_seg = _current_segment(current_track, current_t_ms)
    cur_emb = list(cur_seg.embedding) if cur_seg and cur_seg.embedding else None
    effective_excludes = _effective_excludes_for_match(
        exclude_ids,
        current_track=current_track,
        current_t_ms=current_t_ms,
        target_emotion_label=target_label,
        target_va=search_target,
    )
    if same_mood_handoff and current_track is not None:
        effective_excludes.add(current_track.id)
    counts = play_counts or {}
    track_list = list(tracks)

    for ex, restrict in _match_exclude_attempts(
        effective_excludes,
        restrict_mood_share,
        same_mood_handoff=same_mood_handoff,
        pad_only=pad_only,
        current_id=current_id,
    ):
        pool = _track_pool(
            track_list,
            ex,
            search_target,
            target_label,
            play_counts=counts,
            restrict_mood_share=restrict,
        )
        best = _pick_best_from_pool(
            pool,
            search_target=search_target,
            target_label=target_label,
            user_target=user_target,
            bpm_current=bpm_current,
            pad_only=pad_only,
            current_id=current_id,
            current_t_ms=current_t_ms,
            effective_excludes=ex,
            cur_emb=cur_emb,
            counts=counts,
            embedding_penalties=embedding_penalties,
        )
        if best is not None:
            return best

    return None


def _pick_joy_session_opener(
    candidates: list[Track],
    pad_target: VA,
    *,
    bpm_current: int,
    counts: dict[str, int],
    target_label: str = "joy",
) -> tuple[Track, Segment, int, float, int, VA, float, str, str] | None:
    """Score joy openers at segment 0 — entry rules skip index 0 elsewhere."""
    want = target_label.strip().lower()
    best: tuple[Track, Segment, int, float, int, VA, float, str, str] | None = None

    for track in candidates:
        opener = session_opener_entry(track, want)
        if opener is None:
            continue
        seg, idx, start_ms, entry_va = opener
        score, mood_dist = _score_candidate(
            pad_target,
            entry_va,
            bpm_current,
            track.bpm,
            track=track,
            target_emotion_label=want,
            current_embedding=None,
            candidate_embedding=list(seg.embedding) if seg.embedding else None,
            play_count=counts.get(track.id, 0),
        )
        quality = mood_quality(mood_dist)
        if best is None:
            best = (track, seg, idx, score, start_ms, entry_va, mood_dist, quality, want)
        elif score > best[3]:
            best = (track, seg, idx, score, start_ms, entry_va, mood_dist, quality, want)
        elif score == best[3] and counts.get(track.id, 0) < counts.get(best[0].id, 0):
            best = (track, seg, idx, score, start_ms, entry_va, mood_dist, quality, want)

    return best


def find_session_seed(
    tracks: Iterable[Track],
    exclude_ids: set[str],
    mood_label: str,
    play_counts: dict[str, int] | None = None,
) -> tuple[Track, Segment, int, float, int, VA, float, str, str] | None:
    """Session opener: mood track with the fewest global plays (0 preferred)."""
    want = mood_label.strip().lower()
    if want not in {"calm", "joy", "energy"}:
        want = "joy"
    branch = next(
        (b for b in EMOTION_BRANCHES if emotion_label_for_branch(b) == want),
        next(b for b in EMOTION_BRANCHES if b.name == "Joy"),
    )
    pad_target = VA(v=branch.pad_v, ar=branch.pad_ar)

    eligible: list[Track] = []
    for track in tracks:
        if track.id in exclude_ids or not track.segments:
            continue
        if not track_has_navigable_timeline(track):
            continue
        if count_segments_for_emotion(track, want) == 0:
            continue
        if segment_is_outro_at(track, 0):
            continue
        if effective_segment_emotion_label(track.segments[0]) != want:
            continue
        eligible.append(track)

    if not eligible:
        return None

    counts = play_counts or {}
    play_tiers = sorted({counts.get(track.id, 0) for track in eligible})
    for tier_plays in play_tiers:
        tier = [track for track in eligible if counts.get(track.id, 0) == tier_plays]
        if not tier:
            continue
        result = _pick_joy_session_opener(
            tier,
            pad_target,
            bpm_current=120,
            counts=counts,
            target_label=want,
        )
        if result is not None:
            return result

    return None


def find_joy_session_seed(
    tracks: Iterable[Track],
    exclude_ids: set[str],
    play_counts: dict[str, int] | None = None,
) -> tuple[Track, Segment, int, float, int, VA, float, str, str] | None:
    """Backward-compatible joy-only session opener."""
    return find_session_seed(tracks, exclude_ids, "joy", play_counts=play_counts)


def prefetch_intents(
    tracks: list[Track],
    user_target: VA,
    bpm_current: int,
    current_track_id: str,
    exclude_ids: set[str],
    *,
    current_track: Track | None = None,
    current_t_ms: int | None = None,
    play_counts: dict[str, int] | None = None,
    intent_filter: frozenset[int] | None = None,
    restrict_mood_share_intents: frozenset[int] | None = None,
    embedding_penalties: list[WeightedEmbedding] | None = None,
) -> dict[str, list[dict]]:
    current_va = (
        va_at_track_time(current_track, current_t_ms / 1000.0)
        if current_track is not None and current_t_ms is not None
        else None
    )
    cur_seg = _current_segment(current_track, current_t_ms)
    cur_emb = list(cur_seg.embedding) if cur_seg and cur_seg.embedding else None
    forward_search, forward_label = _resolve_forward_search_target(
        user_target,
        current_track=current_track,
        current_t_ms=current_t_ms,
    )

    result: dict[str, list[dict]] = {}
    intent_ids = [SAME_MOOD_INTENT, *[b.intent for b in EMOTION_BRANCHES]]
    if intent_filter is not None:
        intent_ids = [intent for intent in intent_ids if intent in intent_filter]
    counts = play_counts or {}

    for intent in intent_ids:
        restrict_mood_share = intent == SAME_MOOD_INTENT or (
            restrict_mood_share_intents is not None
            and intent in restrict_mood_share_intents
        )
        if intent == SAME_MOOD_INTENT:
            ctx = _same_mood_search_context(current_track, current_t_ms)
            if ctx is None:
                result[str(intent)] = []
                continue
            branch_target, search_target, target_label = ctx
        else:
            branch_target = branch_target_va(intent, current_va=current_va)
            search_target, branch = resolve_search_target(branch_target)
            target_label = emotion_label_for_branch(branch)
            if (
                current_track is not None
                and current_t_ms is not None
                and target_label == forward_label
            ):
                search_target = forward_search

        intent_excludes = set(exclude_ids)
        if intent == SAME_MOOD_INTENT:
            intent_excludes.add(current_track_id)
        elif (
            current_track is not None
            and current_t_ms is not None
            and _should_skip_current_track(
                current_track, current_t_ms, target_label, search_target
            )
        ):
            intent_excludes.add(current_track_id)

        pool = _track_pool(
            tracks,
            intent_excludes,
            search_target,
            target_label,
            play_counts=counts,
            restrict_mood_share=restrict_mood_share,
        )
        scored: list[tuple[float, Track, Segment, int, int, VA, float]] = []

        for track in pool:
            entry = _entry_for_track(
                track,
                search_target,
                target_label,
                current_track_id=current_track_id,
                current_t_ms=current_t_ms,
            )
            if entry is None:
                continue
            start_ms, entry_va, idx = entry
            seg = track.segments[idx]
            score, mood_dist = _score_candidate(
                branch_target,
                entry_va,
                bpm_current,
                track.bpm,
                track=track,
                target_emotion_label=target_label,
                current_embedding=cur_emb,
                candidate_embedding=list(seg.embedding) if seg.embedding else None,
                play_count=counts.get(track.id, 0),
                embedding_penalties=embedding_penalties,
            )
            scored.append((score, track, seg, idx, start_ms, entry_va, mood_dist))

        scored.sort(key=lambda item: (-item[0], counts.get(item[1].id, 0)))
        candidates: list[dict] = []
        for score, track, seg, idx, start_ms, entry_va, mood_dist in scored[:TOP_K]:
            transition = crossfade_plan_between_tracks(
                from_track=current_track,
                from_t_ms=current_t_ms,
                to_track=track,
                entry_ms=start_ms,
                entry_va=entry_va,
                bpm_from=bpm_current,
                bpm_to=track.bpm,
            )
            candidates.append(
                _candidate_dict(
                    track,
                    seg,
                    idx,
                    transition.entry_ms,
                    entry_va,
                    score,
                    mood_dist,
                    target_emotion_label=target_label,
                    crossfade=transition.plan,
                )
            )

        result[str(intent)] = candidates

    return result
