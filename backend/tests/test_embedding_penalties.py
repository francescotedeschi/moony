"""Early-reject embedding penalties (skip / same-mood handoff ≤15s)."""

import time

from app.catalog.normalize import normalize_catalog
from app.matching.core import find_best_match, prefetch_intents
from app.matching.embedding_penalties import (
    PENALTY_HALF_LIFE_MS,
    embeddings_for_play_range,
    embedding_penalty_adjustment,
    penalty_decay_weight,
    resolve_weighted_penalties,
)
from app.models.api import EmbeddingPenaltyRange
from app.models.catalog import VA


def _track(tid: str, emb_a: list[float], emb_b: list[float] | None = None) -> dict:
    segs = [
        {
            "start_sec": 0.0,
            "end_sec": 15.0,
            "valence": -0.05,
            "arousal": -0.51,
            "label": "c1",
            "emotion_label": "calm",
            "embedding": emb_a,
        },
    ]
    if emb_b is not None:
        segs.append(
            {
                "start_sec": 15.0,
                "end_sec": 30.0,
                "valence": -0.04,
                "arousal": -0.50,
                "label": "c2",
                "emotion_label": "calm",
                "embedding": emb_b,
            },
        )
        segs.append(
            {
                "start_sec": 30.0,
                "end_sec": 40.0,
                "valence": -0.06,
                "arousal": -0.52,
                "label": "c3",
                "emotion_label": "calm",
                "embedding": emb_b,
            },
        )
    return {
        "id": tid,
        "title": tid,
        "artist": "A",
        "duration_sec": 40.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": f"https://example.com/{tid}.mp3", "tags": []},
        "segments": segs,
    }


def test_penalty_decay_halves_every_ten_minutes():
    now = 1_700_000_000_000
    assert penalty_decay_weight(now, now) == 1.0
    assert penalty_decay_weight(now, now + PENALTY_HALF_LIFE_MS) == 0.5


def test_embeddings_for_play_range_caps_at_fifteen_seconds():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_track("t", [1.0, 0.0], [0.0, 1.0])],
        }
    )
    track = cat.get_track("t")
    assert len(embeddings_for_play_range(track, 0, 5_000)) == 1
    assert len(embeddings_for_play_range(track, 0, 20_000)) == 1
    assert len(embeddings_for_play_range(track, 14_000, 30_000)) == 2


def test_embedding_penalty_demotes_similar_candidate():
    current = _track("current", [1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    aligned = _track("aligned", [0.95, 0.05, 0.0], [0.9, 0.1, 0.0])
    orthogonal = _track("other", [0.0, 1.0, 0.0], [0.0, 1.0, 0.0])
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [current, aligned, orthogonal],
        }
    )
    playing = cat.get_track("current")
    calm_pad = VA(v=0.0, ar=-0.8)
    tracks_by_id = {t.id: t for t in cat.tracks}
    now_ms = int(time.time() * 1000)
    penalties = resolve_weighted_penalties(
        [
            EmbeddingPenaltyRange(
                track_id="current",
                from_ms=0,
                to_ms=10_000,
                added_at_ms=now_ms,
            )
        ],
        tracks_by_id,
        now_ms=now_ms,
    )
    assert penalties
    assert embedding_penalty_adjustment([0.95, 0.05, 0.0], penalties) < 0.0
    assert embedding_penalty_adjustment([0.0, 1.0, 0.0], penalties) == 0.0

    result = find_best_match(
        cat.tracks,
        calm_pad,
        VA(v=0.0, ar=0.0),
        110,
        {"current"},
        current_t_ms=1000,
        current_track=playing,
        pad_only=True,
        embedding_penalties=penalties,
    )
    assert result is not None
    track, _seg, _idx, _score, _ms, _va, _md, _mq, el = result
    assert el == "chilled"
    assert track.id == "other"


def test_prefetch_intents_respects_embedding_penalties():
    current = _track("current", [1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    aligned = _track("aligned", [0.98, 0.02, 0.0], [0.95, 0.05, 0.0])
    orthogonal = _track("other", [0.0, 1.0, 0.0], [0.0, 1.0, 0.0])
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [current, aligned, orthogonal],
        }
    )
    playing = cat.get_track("current")
    tracks_by_id = {t.id: t for t in cat.tracks}
    now_ms = int(time.time() * 1000)
    penalties = resolve_weighted_penalties(
        [
            EmbeddingPenaltyRange(
                track_id="current",
                from_ms=0,
                to_ms=8_000,
                added_at_ms=now_ms,
            )
        ],
        tracks_by_id,
        now_ms=now_ms,
    )
    intents = prefetch_intents(
        cat.tracks,
        VA(v=0.0, ar=-0.8),
        110,
        "current",
        {"current"},
        current_track=playing,
        current_t_ms=2000,
        intent_filter=frozenset({8}),  # 8 = Chilled (was 7 = Calm)
        embedding_penalties=penalties,
    )
    top = intents["8"][0]
    assert top["track_id"] == "other"
