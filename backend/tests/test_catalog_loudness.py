from app.catalog.loudness import compute_youtube_playback_gain, youtube_gain_for_track
from app.models.catalog import Track, TrackLoudness


def test_compute_youtube_playback_gain_attenuates_hot_track():
    gain = compute_youtube_playback_gain(-8.0, 0.0)
    assert 0 < gain < 1


def test_compute_youtube_playback_gain_never_boosts_quiet():
    quiet = compute_youtube_playback_gain(-20.0, -3.0)
    assert quiet == 1.0


def test_youtube_gain_for_track():
    track = Track(
        id="t1",
        title="T",
        artist="A",
        bpm=120,
        audio_url="http://example.com/a.mp3",
        loudness=TrackLoudness(
            integrated_lufs=-10.0,
            true_peak_dbfs=-1.0,
            youtube_gain=0.5,
        ),
    )
    assert youtube_gain_for_track(track) == 0.5
