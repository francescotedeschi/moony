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
    """v1.7 export uses ``sections`` and Cyanite mood tags."""
    sample = {
        "catalog_schema": "moodpad-catalog-musicathon",
        "version": "1.7",
        "tracks": [
            {
                "id": "jamendo_1036435",
                "title": "FLIGHT",
                "artist": "Sweet Play",
                "duration_sec": 30.0,
                "jamendo": {
                    "audio_url": "https://example.com/track.mp3",
                    "tags": ["peaceful"],
                },
                "sections": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 10.0,
                        "structure_label": "intro",
                        "cyanite_mood_tag": "calm",
                        "cyanite_valence": 0.29,
                        "cyanite_arousal": -0.18,
                        "description": "Voice: instrumental",
                    },
                    {
                        "start_sec": 10.0,
                        "end_sec": 30.0,
                        "structure_label": "chorus",
                        "cyanite_mood_tag": "happy",
                        "cyanite_valence": 0.65,
                        "cyanite_arousal": 0.25,
                    },
                ],
            }
        ],
    }
    cat = normalize_catalog(sample)
    t = cat.tracks[0]
    assert len(t.segments) == 2
    assert t.segments[0].label == "intro"
    assert t.segments[0].emotion_label == "chilled"
    assert t.segments[0].v == 0.29
    assert t.segments[0].ar == -0.18
    assert t.segments[1].label == "chorus"
    assert t.segments[1].v == 0.65


def test_energy_curve_extended_to_track_bounds():
    """Cyanite samples start at 15s — synthetic points at 0 and duration cover intro/outro."""
    sample = {
        "catalog_schema": "moodpad-catalog-musicathon",
        "version": "1.7",
        "tracks": [
            {
                "id": "jamendo_test",
                "title": "Test",
                "artist": "Artist",
                "duration_sec": 208.0,
                "primary_emotion": "calm",
                "jamendo": {"audio_url": "https://example.com/track.mp3", "tags": []},
                "sections": [
                    {"start_sec": 0.0, "end_sec": 10.0, "structure_label": "intro", "emotion_label": "calm"},
                    {"start_sec": 10.0, "end_sec": 192.0, "structure_label": "verse", "emotion_label": "calm"},
                    {"start_sec": 192.0, "end_sec": 208.0, "structure_label": "outro", "emotion_label": "calm"},
                ],
                "cyanite": {
                    "energy_curve": [0.18, 0.45, 0.30],
                    "segment_timestamps_sec": [15.0, 90.0, 180.0],
                },
            }
        ],
    }
    t = normalize_catalog(sample).tracks[0]
    assert t.energy_curve_timestamps_ms[0] == 0
    assert t.energy_curve[0] == 0.18
    assert t.energy_curve_timestamps_ms[-1] == 208_000
    assert t.energy_curve[-1] == 0.30
    assert len(t.energy_curve) == 5


def test_normalize_excludes_untrusted_lyrics():
    sample = {
        "catalog_schema": "moodpad-catalog-musicathon",
        "tracks": [
            {
                "id": "jamendo_trusted",
                "title": "Trusted",
                "artist": "Artist",
                "duration_sec": 120.0,
                "primary_emotion": "calm",
                "jamendo": {"audio_url": "https://example.com/a.mp3", "tags": []},
                "sections": [
                    {"start_sec": 0.0, "end_sec": 120.0, "structure_label": "verse", "emotion_label": "calm"},
                ],
                "musixmatch": {"track_id": "1", "lyrics_trusted": True},
            },
            {
                "id": "jamendo_untrusted",
                "title": "Wrong Lyrics",
                "artist": "Artist",
                "duration_sec": 120.0,
                "primary_emotion": "calm",
                "jamendo": {"audio_url": "https://example.com/b.mp3", "tags": []},
                "sections": [
                    {"start_sec": 0.0, "end_sec": 120.0, "structure_label": "verse", "emotion_label": "calm"},
                ],
                "musixmatch": {
                    "track_id": "2",
                    "lyrics_trusted": False,
                    "subtitle_audit_reasons": ["metadata_mismatch"],
                },
            },
        ],
    }
    cat = normalize_catalog(sample)
    assert len(cat.tracks) == 1
    assert cat.get_track("jamendo_trusted") is not None
    assert cat.get_track("jamendo_untrusted") is None


def test_load_user_catalog_if_present():
    path = Path(__file__).resolve().parents[2] / "catalog" / "catalog.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    cat = normalize_catalog(data)
    assert len(cat.tracks) >= 1
    assert all(t.audio_url for t in cat.tracks)
