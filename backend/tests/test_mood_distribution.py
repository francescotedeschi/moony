from app.catalog.mood_distribution import (
    MOOD_DISTRIBUTION_LABELS,
    compute_mood_distribution,
    dominant_mood,
)
from app.catalog.normalize import normalize_catalog
from app.models.catalog import Segment, Track


def _seg(emotion_label: str = "", v: float = 0.0, ar: float = 0.0) -> Segment:
    return Segment(
        t_start=0,
        t_end=1000,
        v=v,
        ar=ar,
        label="verse",
        emotion_label=emotion_label,
    )


def test_compute_mood_distribution_from_emotion_labels():
    # MOSS labels are remapped: joy→happy, calm→chilled, energy→energetic
    # 7-zone order: [energetic, happy, chilled, romantic, sad, dark, tense]
    segments = [
        _seg("joy"),
        _seg("joy"),
        _seg("calm"),
        _seg("energy"),
        _seg("sad"),
    ]
    dist = compute_mood_distribution(segments)
    assert len(dist) == 7
    assert dist == [0.2, 0.4, 0.2, 0.0, 0.2, 0.0, 0.0]
    assert abs(sum(dist) - 1.0) < 1e-9


def test_compute_mood_distribution_falls_back_to_va():
    # Happy zone from V/A when no emotion_label (V/A (0.8, 0.6) → nearest to Happy)
    segments = [_seg(v=0.8, ar=0.6), _seg(v=0.8, ar=0.6)]
    dist = compute_mood_distribution(segments)
    happy_idx = MOOD_DISTRIBUTION_LABELS.index("happy")
    assert dist[happy_idx] == 1.0


def test_dominant_mood():
    # 7-zone order: [energetic, happy, chilled, romantic, sad, dark, tense]
    assert dominant_mood([0.1, 0.5, 0.2, 0.1, 0.1, 0.0, 0.0]) == "happy"
    assert dominant_mood([0.25, 0.25, 0.25, 0.25, 0.0, 0.0, 0.0]) == "energetic"


def test_track_model_sets_mood_distribution():
    # tension→tense (idx=6), calm→chilled (idx=2)
    segments = [_seg("tension"), _seg("tension"), _seg("calm")]
    track = Track(
        id="t1",
        title="T",
        artist="A",
        bpm=120,
        audio_url="https://example.com/a.mp3",
        segments=segments,
    )
    assert track.mood_distribution == [0.0, 0.0, 1 / 3, 0.0, 0.0, 0.0, 2 / 3]


def test_normalize_catalog_includes_mood_distribution():
    sample = {
        "catalog_schema": "moodpad-catalog-musicathon",
        "tracks": [
            {
                "id": "jamendo_1",
                "title": "Test",
                "artist": "Artist",
                "duration_sec": 120.0,
                "primary_emotion": "joy",
                "jamendo": {"audio_url": "https://example.com/t.mp3", "tags": []},
                "segments": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 60.0,
                        "emotion_label": "joy",
                        "label": "verse",
                    },
                    {
                        "start_sec": 60.0,
                        "end_sec": 120.0,
                        "emotion_label": "energy",
                        "label": "chorus",
                    },
                ],
            }
        ],
    }
    cat = normalize_catalog(sample)
    t = cat.tracks[0]
    # joy→happy (idx=1), energy→energetic (idx=0) → [0.5, 0.5, 0, 0, 0, 0, 0]
    assert len(t.mood_distribution) == 7
    assert t.mood_distribution == [0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert dominant_mood(t.mood_distribution) in ("happy", "energetic")
