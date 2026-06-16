"""Segment embeddings contribute to match score (continuity + target-mood profile)."""

from app.catalog.normalize import normalize_catalog
from app.matching.core import find_best_match
from app.models.catalog import VA


def _track(tid: str, emb_a: list[float], emb_b: list[float] | None = None) -> dict:
    segs = [
        {
            "start_sec": 0.0,
            "end_sec": 15.0,
            "valence": -0.05,
            "arousal": -0.51,
            "label": "c1",
            "emotion_label": "calm",
            "embedding": emb_a,
        },
    ]
    if emb_b is not None:
        segs.append(
            {
                "start_sec": 15.0,
                "end_sec": 30.0,
                "valence": -0.04,
                "arousal": -0.50,
                "label": "c2",
                "emotion_label": "calm",
                "embedding": emb_b,
            },
        )
        segs.append(
            {
                "start_sec": 30.0,
                "end_sec": 40.0,
                "valence": -0.06,
                "arousal": -0.52,
                "label": "c3",
                "emotion_label": "calm",
                "embedding": emb_b,
            },
        )
    return {
        "id": tid,
        "title": tid,
        "artist": "A",
        "duration_sec": 40.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": f"https://example.com/{tid}.mp3", "tags": []},
        "segments": segs,
    }


def test_embedding_prefers_track_aligned_with_current_segment():
    current = _track("current", [1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    aligned = _track("aligned", [0.95, 0.05, 0.0], [0.9, 0.1, 0.0])
    orthogonal = _track("other", [0.0, 1.0, 0.0], [0.0, 1.0, 0.0])
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [current, aligned, orthogonal],
        }
    )
    playing = cat.get_track("current")
    calm_pad = VA(v=0.0, ar=-0.8)
    result = find_best_match(
        cat.tracks,
        calm_pad,
        VA(v=0.0, ar=0.0),
        110,
        {"current"},
        current_t_ms=1000,
        current_track=playing,
        pad_only=True,
    )
    assert result is not None
    track, _seg, _idx, _score, _ms, _va, _md, _mq, el = result
    assert el == "calm"
    assert track.id == "aligned"
