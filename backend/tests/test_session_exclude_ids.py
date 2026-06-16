"""Session exclude_ids: tracks already played must not reappear in match/prefetch."""

from app.catalog.normalize import normalize_catalog
from app.matching.core import find_best_match, prefetch_intents
from app.models.catalog import VA


def _calm_track(tid: str, *, start_sec: float = 10.0) -> dict:
    return {
        "id": tid,
        "title": tid,
        "artist": "A",
        "duration_sec": 100.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": f"https://example.com/{tid}.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 8.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "intro",
                "emotion_label": "joy",
            },
            {
                "start_sec": start_sec,
                "end_sec": 50.0,
                "valence": -0.05,
                "arousal": -0.51,
                "label": "main",
                "emotion_label": "calm",
            },
            {
                "start_sec": 50.0,
                "end_sec": 100.0,
                "valence": -0.05,
                "arousal": -0.51,
                "label": "coda",
                "emotion_label": "calm",
            },
        ],
    }


def test_find_best_match_skips_session_played_tracks():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_calm_track("a"), _calm_track("b", start_sec=12.0)],
        }
    )
    calm_pad = VA(v=0.0, ar=-0.8)
    first = find_best_match(cat.tracks, calm_pad, VA(v=0.0, ar=0.0), 110, set(), pad_only=True)
    assert first is not None
    assert first[0].id == "a"

    second = find_best_match(
        cat.tracks,
        calm_pad,
        VA(v=0.0, ar=0.0),
        110,
        {"a"},
        pad_only=True,
    )
    assert second is not None
    assert second[0].id == "b"

    none_left = find_best_match(
        cat.tracks,
        calm_pad,
        VA(v=0.0, ar=0.0),
        110,
        {"a", "b"},
        pad_only=True,
    )
    assert none_left is None


def test_prefetch_intents_honors_session_exclude_ids():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_calm_track("root"), _calm_track("alt", start_sec=12.0)],
        }
    )
    root = cat.tracks[0]
    intents = prefetch_intents(
        cat.tracks,
        VA(v=0.0, ar=-0.8),
        110,
        root.id,
        {root.id, "alt"},
        current_track=root,
        current_t_ms=20_000,
    )
    calm_branch = intents.get("7") or []
    assert not calm_branch or all(c["track_id"] not in {"root", "alt"} for c in calm_branch)
