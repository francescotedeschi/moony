from app.catalog.motion import motion_preview_curve
from app.models.catalog import TrackMotion


def test_motion_preview_downsamples_valence():
    motion = TrackMotion(
        hop_sec=1.0,
        energy=[0.5] * 11,
        vocal=[0.2] * 11,
        valence_smooth=[-1.0, -0.5, 0.0, 0.5, 1.0, 1.0, 0.5, 0.0, -0.5, -1.0, -0.8],
        arousal_smooth=[0.0] * 11,
        mood=[50.0] * 11,
    )
    curve = motion_preview_curve(motion, duration_ms=10_000, max_points=8)
    assert len(curve) >= 2
    assert curve[0]["t_ms"] == 0
    assert 0.0 <= curve[0]["y"] <= 1.0
