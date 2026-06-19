from app.catalog.energy import (
    energy_at_time_ms,
    energy_preview_curve,
    energy_sample_at_sec,
    track_has_energy_curve,
)
from app.catalog.normalize import normalize_catalog


def _track_with_energy() -> dict:
    return {
        "id": "energy_a",
        "title": "A",
        "artist": "X",
        "duration_sec": 30.0,
        "jamendo": {"audio_url": "https://example.com/a.mp3", "tags": []},
        "sections": [
            {
                "start_sec": 0.0,
                "end_sec": 15.0,
                "structure_label": "verse",
                "cyanite_mood_tag": "calm",
                "cyanite_valence": 0.2,
                "cyanite_arousal": -0.3,
            },
            {
                "start_sec": 15.0,
                "end_sec": 30.0,
                "structure_label": "chorus",
                "cyanite_mood_tag": "happy",
                "cyanite_valence": 0.7,
                "cyanite_arousal": 0.5,
            },
        ],
        "cyanite": {
            "energy_curve": [0.2, 0.5, 0.8],
            "segment_timestamps_sec": [0.0, 15.0, 30.0],
        },
    }


def test_energy_at_time_ms_interpolates():
    values = [0.0, 1.0]
    ts = [0, 1000]
    assert energy_at_time_ms(values, ts, 500) == 0.5


def test_energy_sample_at_sec_uses_segment_va():
    track = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [_track_with_energy()]}
    ).tracks[0]
    sample = energy_sample_at_sec(track, 0.0)
    assert sample.energy == 0.2
    assert sample.valence == 0.2
    assert sample.arousal == -0.3

    sample_late = energy_sample_at_sec(track, 20.0)
    assert round(sample_late.energy, 2) == 0.6
    assert sample_late.valence == 0.7


def test_energy_preview_curve():
    track = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [_track_with_energy()]}
    ).tracks[0]
    assert track_has_energy_curve(track)
    curve = energy_preview_curve(track, duration_ms=30_000, max_points=8)
    assert len(curve) >= 2
    assert curve[0]["t_ms"] == 0
