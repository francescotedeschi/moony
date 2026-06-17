"""Tests for emotion matching v2 (core.py)."""

from app.catalog.normalize import normalize_catalog
from app.matching.core import find_best_match, prefetch_intents
from app.matching.emotions import resolve_search_target
from app.models.catalog import VA


def _track_with_motion() -> dict:
    return {
        "id": "motion_a",
        "title": "A",
        "artist": "X",
        "duration_sec": 12.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/a.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 5.0,
                "valence": -0.7,
                "arousal": -0.5,
                "label": "sad",
                "emotion_label": "sad",
            },
            {
                "start_sec": 5.0,
                "end_sec": 9.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "happy",
                "emotion_label": "joy",
            },
            {
                "start_sec": 9.0,
                "end_sec": 12.0,
                "valence": 0.75,
                "arousal": 0.55,
                "label": "coda",
                "emotion_label": "joy",
            },
        ],
        "motion": {
            "hop_sec": 1.0,
            "energy": [0.5] * 13,
            "vocal": [0.2] * 13,
            "valence_smooth": [-0.8, -0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.8, 0.75, 0.7],
            "arousal_smooth": [-0.5, -0.4, -0.3, -0.1, 0.0, 0.2, 0.3, 0.5, 0.6, 0.7, 0.7, 0.65, 0.6],
            "mood": [
                50 + 25 * v + 25 * a
                for v, a in zip(
                    [-0.8, -0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.8, 0.75, 0.7],
                    [-0.5, -0.4, -0.3, -0.1, 0.0, 0.2, 0.3, 0.5, 0.6, 0.7, 0.7, 0.65, 0.6],
                    strict=True,
                )
            ],
        },
    }


def test_calm_pad_maps_to_catalog_search_space():
    # (0.0, -0.8) is now nearest to "Chilled" zone (centroid +0.29, -0.18)
    search, branch = resolve_search_target(VA(v=0.0, ar=-0.8))
    assert branch.name == "Chilled"
    assert search.ar > -0.75
    assert search.ar < -0.10


def test_joy_target_picks_high_valence_entry():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_track_with_motion(), _track_with_motion()],
        }
    )
    cat.tracks[1].id = "other"
    result = find_best_match(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        VA(v=0.0, ar=0.0),
        110,
        {cat.tracks[0].id},
        current_t_ms=500,
        current_track=cat.tracks[0],
    )
    assert result is not None
    _t, _s, _i, _sc, start_ms, entry_va, dist, quality, _el = result
    assert entry_va.v > 0.35
    assert start_ms >= 4000
    assert dist < 0.5


def test_prefetch_calm_branch_not_sad():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                _track_with_motion(),
                {
                    **_track_with_motion(),
                    "id": "calmish",
                    "duration_sec": 20.0,
                    "segments": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 4.0,
                            "valence": 0.8,
                            "arousal": 0.6,
                            "label": "intro",
                            "emotion_label": "joy",
                        },
                        {
                            "start_sec": 4.0,
                            "end_sec": 14.0,
                            "valence": 0.0,
                            "arousal": -0.8,
                            "label": "verse",
                            "emotion_label": "calm",
                        },
                        {
                            "start_sec": 14.0,
                            "end_sec": 20.0,
                            "valence": 0.0,
                            "arousal": -0.8,
                            "label": "coda",
                            "emotion_label": "calm",
                        },
                    ],
                    "motion": {
                        "hop_sec": 1.0,
                        "energy": [0.3] * 11,
                        "vocal": [0.1] * 11,
                        "valence_smooth": [0.0] * 11,
                        "arousal_smooth": [-0.55] * 11,
                        "mood": [50 + 25 * 0 + 25 * -0.55] * 11,
                    },
                },
            ],
        }
    )
    intents = prefetch_intents(
        cat.tracks,
        VA(v=0.0, ar=-0.8),
        110,
        "motion_a",
        {"motion_a"},
        current_track=cat.tracks[0],
        current_t_ms=0,
    )
    calm = intents["8"][0]  # "8" is Chilled intent (was 7 = Calm)
    assert calm["track_id"] == "calmish"
    assert calm["segment"]["ar"] < -0.10
