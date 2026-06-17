"""Tracks with ≥50% target-mood segments score higher."""

from app.catalog.normalize import normalize_catalog
from app.matching.core import (
    TARGET_EMOTION_DEPTH_BONUS,
    TARGET_EMOTION_FRACTION,
    count_segments_for_emotion,
    find_best_match,
    target_emotion_depth_bonus,
    target_emotion_fraction,
)
from app.models.catalog import VA


def test_target_emotion_fraction_and_bonus():
    track = {
        "id": "t1",
        "title": "T",
        "artist": "A",
        "duration_sec": 60.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/a.mp3", "tags": []},
        "segments": [
            {"start_sec": 0, "end_sec": 10, "valence": 0, "arousal": -0.5, "label": "a", "emotion_label": "calm"},
            {"start_sec": 10, "end_sec": 20, "valence": 0.8, "arousal": 0.6, "label": "b", "emotion_label": "joy"},
            {"start_sec": 20, "end_sec": 30, "valence": 0, "arousal": -0.5, "label": "c", "emotion_label": "calm"},
            {"start_sec": 30, "end_sec": 40, "valence": 0, "arousal": -0.5, "label": "d", "emotion_label": "calm"},
        ],
    }
    cat = normalize_catalog({"catalog_schema": "moodpad-catalog-musicathon", "tracks": [track]})
    t = cat.tracks[0]
    assert count_segments_for_emotion(t, "calm") == 3
    assert target_emotion_fraction(t, "calm") == 0.75
    assert target_emotion_fraction(t, "calm") >= TARGET_EMOTION_FRACTION
    assert target_emotion_depth_bonus(t, "calm") == TARGET_EMOTION_DEPTH_BONUS

    sparse = {
        **track,
        "id": "sparse",
        "segments": track["segments"][:2],
    }
    cat2 = normalize_catalog({"catalog_schema": "moodpad-catalog-musicathon", "tracks": [sparse]})
    s = cat2.tracks[0]
    assert target_emotion_fraction(s, "calm") == 0.5
    assert target_emotion_depth_bonus(s, "calm") == TARGET_EMOTION_DEPTH_BONUS

    too_few = {
        **track,
        "id": "few",
        "segments": [
            track["segments"][0],
            track["segments"][1],
            {"start_sec": 20, "end_sec": 30, "valence": 0.8, "arousal": 0.6, "label": "x", "emotion_label": "joy"},
            {"start_sec": 30, "end_sec": 40, "valence": 0.8, "arousal": 0.6, "label": "y", "emotion_label": "joy"},
        ],
    }
    cat3 = normalize_catalog({"catalog_schema": "moodpad-catalog-musicathon", "tracks": [too_few]})
    f = cat3.tracks[0]
    assert target_emotion_fraction(f, "calm") == 0.25
    assert target_emotion_depth_bonus(f, "calm") == 0.0


def test_find_best_match_prefers_track_with_half_target_segments():
    shallow = {
        "id": "shallow_calm",
        "title": "Shallow",
        "artist": "A",
        "duration_sec": 30.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/s.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 10.0,
                "valence": -0.05,
                "arousal": -0.51,
                "label": "only",
                "emotion_label": "calm",
            },
            {
                "start_sec": 10.0,
                "end_sec": 20.0,
                "valence": 0.79,
                "arousal": 0.61,
                "label": "joy1",
                "emotion_label": "joy",
            },
            {
                "start_sec": 20.0,
                "end_sec": 30.0,
                "valence": 0.80,
                "arousal": 0.62,
                "label": "joy2",
                "emotion_label": "joy",
            },
        ],
    }
    deep = {
        "id": "deep_calm",
        "title": "Deep",
        "artist": "B",
        "duration_sec": 40.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/d.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 10.0,
                "valence": -0.05,
                "arousal": -0.51,
                "label": "c1",
                "emotion_label": "calm",
            },
            {
                "start_sec": 10.0,
                "end_sec": 20.0,
                "valence": -0.04,
                "arousal": -0.50,
                "label": "c2",
                "emotion_label": "calm",
            },
            {
                "start_sec": 20.0,
                "end_sec": 30.0,
                "valence": -0.06,
                "arousal": -0.52,
                "label": "c3",
                "emotion_label": "calm",
            },
            {
                "start_sec": 30.0,
                "end_sec": 40.0,
                "valence": 0.79,
                "arousal": 0.61,
                "label": "joy",
                "emotion_label": "joy",
            },
        ],
    }
    cat = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [shallow, deep]}
    )
    calm_pad = VA(v=0.0, ar=-0.8)
    result = find_best_match(
        cat.tracks,
        calm_pad,
        VA(v=0.0, ar=0.0),
        110,
        set(),
        pad_only=True,
    )
    assert result is not None
    track, _seg, _idx, _score, _ms, _va, _md, _mq, el = result
    assert el == "chilled"
    assert track.id == "deep_calm"
    shallow_t = next(t for t in cat.tracks if t.id == "shallow_calm")
    assert target_emotion_fraction(shallow_t, "calm") < TARGET_EMOTION_FRACTION
    assert target_emotion_fraction(track, "calm") >= TARGET_EMOTION_FRACTION
