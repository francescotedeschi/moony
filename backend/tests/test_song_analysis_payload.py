"""Unit tests for player-facing V17 payload shaping (no MOSS/Cyanite runtime)."""

from __future__ import annotations

import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[2] / "pipeline"
sys.path.insert(0, str(PIPELINE))

from slim_catalog_v17 import assert_no_lyrics_in_payload, slim_player_track  # noqa: E402


def test_slim_player_track_drops_pipeline_fields():
    raw = {
        "id": "jamendo_1",
        "title": "T",
        "artist": "A",
        "duration_sec": 120.0,
        "bpm": 100,
        "moss_status": "done",
        "analyzer": "moss",
        "primary_emotion": "calm",
        "motion": {"curve": [0.1]},
        "jamendo": {"track_id": 1, "audio_url": "https://x", "local_audio_path": "/tmp/x.mp3"},
        "musixmatch": {"track_id": "9", "has_lyrics": 1},
        "sections": [
            {
                "start_sec": 0.0,
                "end_sec": 60.0,
                "structure_label": "verse",
                "cyanite_mood_tag": "calm",
                "cyanite_valence": 0.2,
                "cyanite_arousal": -0.1,
                "description": "soft pads",
                "embedding": [0.1, 0.2],
                "valence": 0.9,
                "emotion_label": "joy",
                "moss_mood_text": "legacy",
            }
        ],
        "cyanite": {"status": "done", "energy_curve": [0.2], "segment_timestamps_sec": [15.0]},
    }

    slim = slim_player_track(raw)

    assert "moss_status" not in slim
    assert "analyzer" not in slim
    assert "motion" not in slim
    assert "local_audio_path" not in slim["jamendo"]
    section = slim["sections"][0]
    assert section["cyanite_mood_tag"] == "calm"
    assert "valence" not in section
    assert "emotion_label" not in section
    assert "moss_mood_text" not in section


def test_assert_no_lyrics_in_payload():
    assert_no_lyrics_in_payload({"tracks": [{"id": "a", "title": "ok"}]})

    try:
        assert_no_lyrics_in_payload({"subtitle_body": "secret"})
        raised = False
    except ValueError:
        raised = True
    assert raised
