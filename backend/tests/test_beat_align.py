"""Tests for beat-grid alignment helpers."""

from app.catalog.normalize import normalize_catalog
from app.matching.beat_align import (
    bar_align_duration_ms,
    compute_crossfade_start_ms,
    snap_entry_ms,
)
from app.matching.motion_crossfade import crossfade_plan_between_tracks
from app.models.catalog import BeatGrid, Segment, Track, VA


def _track(
    *,
    bpm: int = 120,
    beat_grid: BeatGrid | None = None,
) -> Track:
    return Track(
        id="t1",
        title="T",
        artist="A",
        bpm=bpm,
        audio_url="https://example.com/a.mp3",
        duration_sec=180.0,
        beat_grid=beat_grid or BeatGrid(offset_ms=120, bar_ms=2000),
        segments=[
            Segment(t_start=0, t_end=90_000, v=0.0, ar=0.0, label="verse"),
            Segment(t_start=90_000, t_end=180_000, v=0.5, ar=0.5, label="chorus"),
        ],
    )


def test_snap_entry_ms_aligns_to_bar():
    track = _track()
    # offset 120, bar 2000 → grid at 120, 2120, 4120, ...
    assert snap_entry_ms(4100, track) == 4120


def test_crossfade_start_ms_on_downbeat():
    track = _track()
    start = compute_crossfade_start_ms(from_t_ms=3000, fade_ms=4000, from_track=track)
    bar = 2000
    offset = 120
    assert (start - offset) % bar == 0


def test_bar_align_duration_rounds_to_whole_bars():
    assert bar_align_duration_ms(2300, 2000, min_ms=900, max_ms=5500) == 2000
    assert bar_align_duration_ms(4500, 2000, min_ms=900, max_ms=5500) == 4000


def test_crossfade_plan_snaps_entry_and_sets_start():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                {
                    "id": "a",
                    "title": "A",
                    "artist": "X",
                    "duration_sec": 60.0,
                    "primary_emotion": "calm",
                    "bpm": 120,
                    "beat_grid": {"offset_ms": 0, "bar_ms": 2000},
                    "jamendo": {"audio_url": "https://example.com/a.mp3", "tags": []},
                    "segments": [
                        {
                            "start_sec": 0,
                            "end_sec": 30,
                            "valence": 0.0,
                            "arousal": 0.0,
                            "label": "verse",
                            "emotion_label": "calm",
                        },
                        {
                            "start_sec": 30,
                            "end_sec": 60,
                            "valence": 0.5,
                            "arousal": 0.5,
                            "label": "chorus",
                            "emotion_label": "joy",
                        },
                    ],
                }
            ],
        }
    )
    from_track = cat.tracks[0]
    transition = crossfade_plan_between_tracks(
        from_track=from_track,
        from_t_ms=3500,
        to_track=from_track,
        entry_ms=5100,
        entry_va=VA(v=0.5, ar=0.5),
        bpm_from=120,
        bpm_to=120,
    )
    assert transition.entry_ms % 2000 == 0
    assert transition.plan.crossfade_ms % 2000 == 0
    assert transition.plan.crossfade_ms <= 5500
    assert transition.plan.crossfade_start_ms is not None
    assert transition.plan.crossfade_start_ms is not None
    assert transition.plan.crossfade_start_ms >= 3500
