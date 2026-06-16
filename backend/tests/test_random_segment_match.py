"""
Sanity check: from a random segment V/A, matching must return results.

If find_best_match is None or prefetch mood branches are empty, the matcher is broken
for that input (or the catalog path is wrong).
"""

from __future__ import annotations

import random

import pytest

from app.matching.core import find_best_match, prefetch_intents
from app.matching.emotions import EMOTION_BRANCHES
from app.models.catalog import VA

MOOD_INTENT_IDS = {str(b.intent) for b in EMOTION_BRANCHES}


def _pick_random_segment(catalog, rng: random.Random):
    tracks = [t for t in catalog.tracks if t.segments]
    assert tracks, "no tracks with segments"
    track = rng.choice(tracks)
    seg = rng.choice(track.segments)
    t_ms = (seg.t_start + seg.t_end) // 2
    return track, seg, t_ms


def _assert_random_segment_match(catalog, rng: random.Random) -> None:
    track, seg, t_ms = _pick_random_segment(catalog, rng)
    target = VA(v=seg.v, ar=seg.ar)

    result = find_best_match(
        catalog.tracks,
        target,
        VA(v=0.0, ar=0.0),
        track.bpm,
        set(),
        current_t_ms=t_ms,
        current_track=track,
    )
    assert result is not None, (
        f"find_best_match returned None — track={track.id!r} segment={seg.label!r} "
        f"emotion_label={seg.emotion_label!r} t_ms={t_ms} v={seg.v} ar={seg.ar}"
    )

    _matched_track, matched_seg, _idx, _score, start_ms, entry_va, mood_dist, quality, target_emotion = (
        result
    )
    assert matched_seg is not None
    assert start_ms >= 0
    assert mood_dist < 2.0
    assert quality in ("excellent", "good", "weak", "poor")

    intents = prefetch_intents(
        catalog.tracks,
        target,
        track.bpm,
        track.id,
        {track.id},
        current_track=track,
        current_t_ms=t_ms,
    )

    mood_branches = {
        intent_id: candidates
        for intent_id, candidates in intents.items()
        if intent_id in MOOD_INTENT_IDS and candidates
    }
    assert len(mood_branches) >= 4, (
        f"expected mood prefetch branches (Calm/Joy/Energy/Tension/Sad), "
        f"got counts={ {k: len(v) for k, v in intents.items()} } "
        f"from track={track.id!r} seg={seg.label!r}"
    )

    for intent_id, candidates in mood_branches.items():
        top = candidates[0]
        assert top.get("track_id"), f"intent {intent_id} candidate missing track_id"
        assert top.get("segment"), f"intent {intent_id} candidate missing segment"
        seg_payload = top["segment"]
        assert "t_start" in seg_payload or "audio_start_ms" in top


def test_random_segment_yields_match_and_prefetch_branches(catalog):
    _assert_random_segment_match(catalog, random.Random(20260522))


@pytest.mark.slow
def test_random_segment_match_holds_over_several_trials(catalog):
    """Repeat draw — catches rare regressions (outro edge, empty emotion pools)."""
    rng = random.Random(99)
    for trial in range(8):
        try:
            _assert_random_segment_match(catalog, rng)
        except AssertionError as exc:
            raise AssertionError(f"trial {trial} failed: {exc}") from exc
