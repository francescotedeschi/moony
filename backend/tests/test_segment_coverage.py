from app.catalog.segment_coverage import track_has_navigable_timeline, track_moss_span_ms
from app.models.catalog import Segment, Track


def _track(
    *,
    segments: list[Segment],
    duration_sec: float | None = None,
) -> Track:
    return Track(
        id="t1",
        title="Test",
        artist="Artist",
        bpm=120,
        audio_url="https://example.com/a.mp3",
        duration_sec=duration_sec,
        segments=segments,
    )


def test_track_moss_span_ms_uses_last_segment_end():
    track = _track(
        segments=[
            Segment(t_start=0, t_end=20_000, v=0.0, ar=0.0, label="intro"),
            Segment(t_start=20_000, t_end=90_000, v=0.0, ar=0.0, label="verse"),
        ],
    )
    assert track_moss_span_ms(track) == 90_000


def test_navigable_requires_at_least_two_segments():
    track = _track(
        duration_sec=120.0,
        segments=[Segment(t_start=0, t_end=18_000, v=0.8, ar=0.6, label="intro")],
    )
    assert track_has_navigable_timeline(track) is False


def test_navigable_rejects_short_moss_on_long_preview():
    track = _track(
        duration_sec=147.0,
        segments=[
            Segment(t_start=0, t_end=18_480, v=0.8, ar=0.6, label="intro"),
            Segment(t_start=18_480, t_end=19_000, v=0.8, ar=0.6, label="verse"),
        ],
    )
    assert track_has_navigable_timeline(track) is False


def test_navigable_accepts_full_moss_timeline():
    track = _track(
        duration_sec=203.0,
        segments=[
            Segment(t_start=0, t_end=17_160, v=0.8, ar=0.6, label="intro"),
            Segment(t_start=17_160, t_end=200_770, v=0.5, ar=0.2, label="outro"),
        ],
    )
    assert track_has_navigable_timeline(track) is True
