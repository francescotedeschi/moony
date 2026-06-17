"""Skip must not enter the next section mood on the same or another track."""

from app.matching.core import find_best_match
from app.catalog.normalize import normalize_catalog
from app.models.catalog import VA


def test_skip_calm_target_never_enters_joy_segment():
    current = {
        "id": "current_calm_joy",
        "title": "Current",
        "artist": "X",
        "duration_sec": 12.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/c.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 6.0,
                "valence": -0.05,
                "arousal": -0.51,
                "label": "verse",
                "emotion_label": "calm",
            },
            {
                "start_sec": 6.0,
                "end_sec": 12.0,
                "valence": 0.79,
                "arousal": 0.61,
                "label": "chorus",
                "emotion_label": "joy",
            },
        ],
        "motion": {
            "hop_sec": 1.0,
            "energy": [0.4] * 13,
            "vocal": [0.2] * 13,
            "valence_smooth": [-0.05] * 6 + [0.79] * 7,
            "arousal_smooth": [-0.51] * 6 + [0.61] * 7,
            "mood": [50.0] * 13,
        },
    }
    other_calm = {
        "id": "other_calm",
        "title": "Other Calm",
        "artist": "Y",
        "duration_sec": 100.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/o.mp3", "tags": []},
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
                "start_sec": 8.0,
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
        "motion": {
            "hop_sec": 1.0,
            "energy": [0.4] * 101,
            "vocal": [0.2] * 101,
            "valence_smooth": [0.8] * 8 + [-0.05] * 42 + [-0.05] * 51,
            "arousal_smooth": [0.6] * 8 + [-0.51] * 42 + [-0.51] * 51,
            "mood": [50.0] * 101,
        },
    }
    cat = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [current, other_calm]}
    )
    calm_pad = VA(v=0.0, ar=-0.8)
    result = find_best_match(
        cat.tracks,
        calm_pad,
        VA(v=0.0, ar=0.0),
        110,
        {current["id"]},
        current_t_ms=2000,
        current_track=cat.get_track(current["id"]),
        pad_only=True,
    )
    assert result is not None
    track, seg, _idx, _score, _start, _va, _md, _mq, el = result
    assert track.id == "other_calm"
    assert el == "chilled"
    assert (seg.emotion_label or "").lower() == "chilled"
