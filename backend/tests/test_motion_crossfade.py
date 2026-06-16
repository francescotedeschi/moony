"""Tests for motion-guided crossfade planning."""

from app.catalog.normalize import normalize_catalog
from app.matching.motion_crossfade import crossfade_plan_between_tracks, motion_crossfade_plan
from app.models.catalog import VA


def _track_with_motion() -> dict:
    return {
        "id": "motion_a",
        "title": "A",
        "artist": "X",
        "duration_sec": 10.0,
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
                "end_sec": 10.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "happy",
                "emotion_label": "joy",
            },
        ],
        "motion": {
            "hop_sec": 1.0,
            "energy": [0.3, 0.35, 0.4, 0.45, 0.5, 0.7, 0.75, 0.8, 0.85, 0.9, 0.9],
            "vocal": [0.2] * 11,
            "valence_smooth": [-0.8, -0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.8],
            "arousal_smooth": [-0.5, -0.4, -0.3, -0.1, 0.0, 0.2, 0.3, 0.5, 0.6, 0.7, 0.7],
            "mood": [50.0] * 11,
        },
    }


def test_large_mood_jump_uses_longer_equal_power_fade():
    plan = motion_crossfade_plan(
        bpm_from=110,
        bpm_to=100,
        exit_va=VA(v=-0.7, ar=-0.5),
        entry_va=VA(v=0.8, ar=0.6),
        exit_energy=0.35,
        entry_energy=0.85,
    )
    assert plan.crossfade_ms >= 1800
    assert plan.curve == "equal_power"
    assert plan.mood_jump > 0.5


def test_small_mood_jump_uses_shorter_linear_fade():
    plan = motion_crossfade_plan(
        bpm_from=120,
        bpm_to=118,
        exit_va=VA(v=0.78, ar=0.58),
        entry_va=VA(v=0.8, ar=0.6),
        exit_energy=0.7,
        entry_energy=0.72,
    )
    assert plan.crossfade_ms < 2400
    assert plan.curve == "linear"


def test_crossfade_plan_between_tracks_uses_motion_timeline():
    cat = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [_track_with_motion()]}
    )
    track = cat.tracks[0]
    transition = crossfade_plan_between_tracks(
        from_track=track,
        from_t_ms=1000,
        to_track=track,
        entry_ms=5000,
        entry_va=VA(v=0.75, ar=0.55),
        bpm_from=110,
        bpm_to=110,
    )
    assert transition.plan.crossfade_ms >= 900
    assert transition.plan.playback_rate_start > 0.8
    assert transition.entry_ms >= 0
