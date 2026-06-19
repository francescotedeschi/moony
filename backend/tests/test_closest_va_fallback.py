"""When strict emotion pools are empty, match falls back to closest V/A on the catalog."""

from app.catalog.normalize import normalize_catalog
from app.matching.core import find_best_match
from app.models.catalog import VA


def _joy_only_track(tid: str) -> dict:
    return {
        "id": tid,
        "title": tid,
        "artist": "A",
        "duration_sec": 100.0,
        "primary_emotion": "happy",
        "jamendo": {"audio_url": f"https://example.com/{tid}.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 50.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "main",
                "emotion_label": "joy",
            },
            {
                "start_sec": 50.0,
                "end_sec": 100.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "coda",
                "emotion_label": "joy",
            },
        ],
    }


def test_find_best_match_falls_back_to_closest_va_when_target_mood_missing():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_joy_only_track("joy_only")],
        }
    )
    calm_pad = VA(v=0.0, ar=-0.8)

    result = find_best_match(cat.tracks, calm_pad, VA(v=0.0, ar=0.0), 110, set(), pad_only=True)

    assert result is not None
    track, seg, _idx, _score, _start_ms, entry_va, _mood_dist, _quality, emotion = result
    assert track.id == "joy_only"
    assert emotion == "happy"
    assert entry_va.v == seg.v
    assert entry_va.ar == seg.ar
