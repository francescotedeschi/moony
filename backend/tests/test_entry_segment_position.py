"""Entry must not be the first segment; cross-track start ≤ 40% of duration."""

from app.catalog.normalize import normalize_catalog
from app.matching.core import find_best_match
from app.matching.motion_match import (
    MAX_ENTRY_POSITION_FRACTION,
    best_target_entry_for_emotion,
    segment_entry_eligible,
    segment_index_at_ms,
    track_duration_sec,
)
from app.models.catalog import VA


def test_segment_entry_eligible_rules():
    track = {
        "id": "pos",
        "title": "P",
        "artist": "A",
        "duration_sec": 100.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/p.mp3", "tags": []},
        "segments": [
            {"start_sec": 0, "end_sec": 15, "valence": 0, "arousal": -0.5, "label": "a", "emotion_label": "calm"},
            {"start_sec": 15, "end_sec": 35, "valence": 0, "arousal": -0.5, "label": "b", "emotion_label": "calm"},
            {"start_sec": 35, "end_sec": 50, "valence": 0, "arousal": -0.5, "label": "c", "emotion_label": "calm"},
            {"start_sec": 50, "end_sec": 100, "valence": 0, "arousal": -0.5, "label": "d", "emotion_label": "calm"},
        ],
    }
    cat = normalize_catalog({"catalog_schema": "moodpad-catalog-musicathon", "tracks": [track]})
    t = cat.tracks[0]
    dur = track_duration_sec(t)
    assert not segment_entry_eligible(t, 0)
    assert segment_entry_eligible(t, 1)
    assert segment_entry_eligible(t, 2)
    assert t.segments[2].t_start / 1000.0 == dur * 0.35
    assert segment_entry_eligible(t, 2)
    assert not segment_entry_eligible(t, 3)
    assert t.segments[3].t_start / 1000.0 == dur * MAX_ENTRY_POSITION_FRACTION + 10.0


def test_cross_track_entry_skips_first_and_late_segments():
    early_only = {
        "id": "early",
        "title": "Early",
        "artist": "A",
        "duration_sec": 100.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/e.mp3", "tags": []},
        "segments": [
            {"start_sec": 0, "end_sec": 80, "valence": 0, "arousal": -0.5, "label": "long", "emotion_label": "calm"},
            {"start_sec": 80, "end_sec": 100, "valence": 0, "arousal": -0.5, "label": "tail", "emotion_label": "calm"},
        ],
    }
    good_mid = {
        "id": "mid",
        "title": "Mid",
        "artist": "B",
        "duration_sec": 100.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/m.mp3", "tags": []},
        "segments": [
            {"start_sec": 0, "end_sec": 10, "valence": 0.8, "arousal": 0.6, "label": "intro", "emotion_label": "joy"},
            {"start_sec": 10, "end_sec": 50, "valence": 0, "arousal": -0.5, "label": "calm", "emotion_label": "calm"},
            {"start_sec": 50, "end_sec": 100, "valence": 0.8, "arousal": 0.6, "label": "out", "emotion_label": "joy"},
        ],
    }
    cat = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [early_only, good_mid]}
    )
    t_early = cat.tracks[0]
    assert best_target_entry_for_emotion(t_early, VA(v=0.0, ar=-0.5), "calm") is None

    t_mid = cat.tracks[1]
    entry = best_target_entry_for_emotion(t_mid, VA(v=0.0, ar=-0.5), "calm")
    assert entry is not None
    start_ms, _va, idx = entry
    assert idx == 1
    assert start_ms == t_mid.segments[1].t_start
    assert segment_entry_eligible(t_mid, idx)

    result = find_best_match(
        cat.tracks,
        VA(v=0.0, ar=-0.8),
        VA(v=0.0, ar=0.0),
        110,
        set(),
        pad_only=True,
    )
    assert result is not None
    track, _seg, idx, _score, start_ms, _va, _md, _mq, _el = result
    assert track.id == "mid"
    assert idx > 0
    assert segment_entry_eligible(track, idx)
    assert segment_index_at_ms(track, start_ms) == idx
