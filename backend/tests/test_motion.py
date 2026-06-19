import json
from pathlib import Path

import pytest

from app.catalog.motion import (
    expected_motion_length,
    motion_at_sec,
    motion_at_sec_interpolated,
    motion_fallback_at_sec,
    motion_for_track,
    motion_index_at_sec,
)
from app.catalog.normalize import normalize_catalog
from app.catalog.validate import validate_catalog
from app.models.catalog import Segment, TrackMotion


def _sample_motion(n: int = 5, hop: float = 1.0) -> TrackMotion:
    return TrackMotion(
        hop_sec=hop,
        energy=[0.2 + 0.1 * i for i in range(n)],
        vocal=[0.3] * n,
        valence_smooth=[-0.5 + 0.2 * i for i in range(n)],
        arousal_smooth=[0.1 + 0.1 * i for i in range(n)],
        mood=[50.0 + 25.0 * (-0.5 + 0.2 * i) + 25.0 * (0.1 + 0.1 * i) for i in range(n)],
    )


def test_motion_index_bounds():
    m = _sample_motion(10)
    assert motion_index_at_sec(m, 0) == 0
    assert motion_index_at_sec(m, 4.2) == 4
    assert motion_index_at_sec(m, 999) == 9


def test_motion_at_sec_and_interpolated():
    m = _sample_motion(5)
    s0 = motion_at_sec(m, 0)
    assert s0.valence == m.valence_smooth[0]
    s_mid = motion_at_sec_interpolated(m, 1.5)
    assert 0.0 <= s_mid.energy <= 1.0
    # t beyond last sample must not crash
    s_end = motion_at_sec_interpolated(m, 999.0)
    assert s_end.valence == m.valence_smooth[-1]


def test_motion_fallback_segments():
    segs = [
        Segment(t_start=0, t_end=30_000, v=0.5, ar=0.2, label="a"),
        Segment(t_start=30_000, t_end=60_000, v=-0.3, ar=0.8, label="b"),
    ]
    s = motion_fallback_at_sec(segs, 60.0, 45.0)
    assert s.valence == -0.3
    assert abs(s.mood - (50 + 25 * s.valence + 25 * s.arousal)) < 0.01


def test_motion_fallback_flat():
    s = motion_fallback_at_sec([], 120.0, 10.0)
    assert s.valence == 0.0
    assert s.arousal == 0.3
    assert s.mood == 50.0 + 25 * 0.3


def test_motion_for_track_prefers_precomputed():
    m = _sample_motion(3)
    segs = [Segment(t_start=0, t_end=1000, v=1.0, ar=1.0, label="x")]
    s = motion_for_track(motion=m, segments=segs, duration_sec=3.0, t_sec=1.0)
    assert s.valence == m.valence_smooth[1]


def test_expected_motion_length():
    assert expected_motion_length(222.0, 1.0) == 223
    assert expected_motion_length(168.0, 1.0) == 169


def test_validate_motion_ok():
    data = {
        "version": "1.3",
        "tracks": [
            {
                "id": "t1",
                "duration_sec": 4.0,
                "segments": [{"label": "a", "v": 0, "ar": 0, "end_sec": 4}],
                "motion": {
                    "hop_sec": 1.0,
                    "energy": [0.5, 0.5, 0.5, 0.5, 0.5],
                    "vocal": [0.5, 0.5, 0.5, 0.5, 0.5],
                    "valence_smooth": [0.0, 0.0, 0.0, 0.0, 0.0],
                    "arousal_smooth": [0.3, 0.3, 0.3, 0.3, 0.3],
                    "mood": [57.5, 57.5, 57.5, 57.5, 57.5],
                },
            }
        ],
    }
    report = validate_catalog(data)
    assert report.ok
    assert not any(i.code == "motion_mood_inconsistent" for i in report.issues)


def test_validate_motion_mood_inconsistent():
    data = {
        "tracks": [
            {
                "id": "bad",
                "duration_sec": 2.0,
                "segments": [],
                "motion": {
                    "hop_sec": 1.0,
                    "energy": [0.5, 0.5, 0.5],
                    "vocal": [0.5, 0.5, 0.5],
                    "valence_smooth": [0.0, 0.0, 0.0],
                    "arousal_smooth": [0.0, 0.0, 0.0],
                    "mood": [99.0, 50.0, 50.0],
                },
            }
        ],
    }
    report = validate_catalog(data)
    assert not report.ok
    assert any(i.code == "motion_mood_inconsistent" for i in report.errors)


def test_normalize_v13_motion():
    sample = {
        "version": "1.3",
        "catalog_schema": "moodpad-catalog-musicathon",
        "tracks": [
            {
                "id": "jamendo_1",
                "title": "T",
                "artist": "A",
                "duration_sec": 3.0,
                "primary_emotion": "calm",
                "jamendo": {"audio_url": "https://example.com/a.mp3", "tags": []},
                "segments": [
                    {"start_sec": 0.0, "end_sec": 3.0, "valence": 0.1, "arousal": 0.2, "label": "full"},
                ],
                "motion": {
                    "hop_sec": 1.0,
                    "energy": [0.1, 0.2, 0.3, 0.4],
                    "vocal": [0.1, 0.2, 0.3, 0.4],
                    "valence_smooth": [0.0, 0.0, 0.0, 0.0],
                    "arousal_smooth": [0.3, 0.3, 0.3, 0.3],
                    "mood": [57.5, 57.5, 57.5, 57.5],
                },
            }
        ],
    }
    cat = normalize_catalog(sample)
    t = cat.tracks[0]
    assert t.has_motion
    assert t.duration_sec == 3.0
    assert len(t.motion.energy) == 4


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "catalog" / "catalog_V17.json").is_file(),
    reason="catalog_V17.json not present",
)
def test_live_catalog_energy_import():
    path = Path(__file__).resolve().parents[2] / "catalog" / "catalog_V17.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    cat = normalize_catalog(data)
    with_energy = sum(1 for t in cat.tracks if t.has_energy_curve)
    assert with_energy >= 1
    t = next(t for t in cat.tracks if t.has_energy_curve)
    assert t.energy_curve
    assert t.energy_curve_timestamps_ms
