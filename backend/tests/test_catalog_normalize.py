import json
from pathlib import Path

from app.catalog.normalize import normalize_catalog


def test_normalize_moodpad_v12_sample():
    sample = {
        "catalog_schema": "moodpad-catalog-musicathon",
        "tracks": [
            {
                "id": "jamendo_1215788",
                "title": "Test Song",
                "artist": "Artist",
                "duration_sec": 168.0,
                "primary_emotion": "calm",
                "jamendo": {
                    "audio_url": "https://example.com/track.mp3",
                    "tags": ["peaceful"],
                },
                "segments": [
                    {"start_sec": 0.0, "end_sec": 45.0, "valence": 0.0, "arousal": 0.0, "label": "intro"},
                    {"start_sec": 0.0, "end_sec": 90.0, "valence": 0.0, "arousal": 0.0, "label": "chorus1"},
                ],
                "musixmatch": {
                    "track_id": None,
                    "has_lyrics": False,
                },
            }
        ],
    }
    cat = normalize_catalog(sample)
    assert len(cat.tracks) == 1
    t = cat.tracks[0]
    assert t.audio_url.startswith("https://")
    assert t.bpm > 0
    assert len(t.segments) == 2
    assert t.segments[0].t_start == 0
    assert t.segments[1].t_start == 45000
    assert abs(t.segments[0].v - 0.25) < 0.01  # calm emotion fallback


def test_normalize_moodpad_v17_sections():
    """v1.7 export uses ``sections`` and ``structure_label`` (no legacy ``label``)."""
    sample = {
        "catalog_schema": "moodpad-catalog-musicathon",
        "version": "1.7",
        "tracks": [
            {
                "id": "jamendo_1036435",
                "title": "FLIGHT",
                "artist": "Sweet Play",
                "duration_sec": 30.0,
                "primary_emotion": "calm",
                "jamendo": {
                    "audio_url": "https://example.com/track.mp3",
                    "tags": ["peaceful"],
                },
                "sections": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 10.0,
                        "structure_label": "intro",
                        "emotion_label": "calm",
                        "valence": 0.0,
                        "arousal": 0.0,
                        "moss_emotion_label": "calm",
                        "description": "Voice: instrumental",
                    },
                    {
                        "start_sec": 10.0,
                        "end_sec": 30.0,
                        "structure_label": "chorus",
                        "emotion_label": "joy",
                        "valence": 0.8,
                        "arousal": 0.6,
                    },
                ],
            }
        ],
    }
    cat = normalize_catalog(sample)
    t = cat.tracks[0]
    assert len(t.segments) == 2
    assert t.segments[0].label == "intro"
    assert t.segments[0].emotion_label == "calm"
    assert t.segments[0].moss_emotion_label == "calm"
    assert t.segments[1].label == "chorus"
    assert t.segments[1].v == 0.8


def test_load_user_catalog_if_present():
    path = Path(__file__).resolve().parents[2] / "catalog" / "catalog.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    cat = normalize_catalog(data)
    assert len(cat.tracks) >= 1
    assert all(t.audio_url for t in cat.tracks)
