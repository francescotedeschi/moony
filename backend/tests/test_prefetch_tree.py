from app.matching.engine import prefetch_tree
from app.models.catalog import VA


def _track(tid: str, title: str, v: float, ar: float, bpm: int = 100) -> dict:
    from app.matching.emotions import emotion_label_for_va

    main = emotion_label_for_va(VA(v=v, ar=ar))
    return {
        "id": tid,
        "title": title,
        "artist": "A",
        "bpm": bpm,
        "duration_sec": 100.0,
        "audio_url": f"https://example.com/{tid}.mp3",
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 10.0,
                "valence": 0.0,
                "arousal": 0.0,
                "label": "intro",
                "emotion_label": "calm",
            },
            {
                "start_sec": 10.0,
                "end_sec": 50.0,
                "valence": v,
                "arousal": ar,
                "label": "main",
                "emotion_label": main,
            },
            {
                "start_sec": 50.0,
                "end_sec": 100.0,
                "valence": v,
                "arousal": ar,
                "label": "coda",
                "emotion_label": main,
            },
        ],
        "transitions": [],
    }


def test_prefetch_tree_has_l2_branches():
    from app.catalog.normalize import normalize_catalog

    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                _track("root", "Root", 0.0, 0.0),
                _track("calm_a", "Calm A", 0.0, -0.8),
                _track("joy_a", "Joy A", 0.8, 0.6),
                _track("energy_a", "Energy A", 0.2, 0.9),
                _track("tension_a", "Tension A", -0.5, 0.7),
                _track("sad_a", "Sad A", -0.7, -0.5),
                _track("calm_b", "Calm B", 0.1, -0.7),
            ],
        }
    )

    tree = prefetch_tree(
        cat.tracks,
        VA(v=0.0, ar=0.0),
        100,
        "root",
        {"root"},
        depth=2,
    )

    assert "intents" in tree
    assert "l2" in tree
    assert len(tree["l2"]) >= 1
    for branch in tree["l2"].values():
        assert "from" in branch
        assert "intents" in branch
        assert branch["from"]["track_id"]
        assert isinstance(branch["intents"], dict)


def test_prefetch_sad_branch_targets_sad_frame_not_pad_position():
    from app.catalog.normalize import normalize_catalog
    from app.matching.engine import prefetch_intents

    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                _track("root", "Root", 0.8, 0.6),
                _track("sad_a", "Sad A", -0.7, -0.5),
                _track("joy_b", "Joy B", 0.85, 0.65),
            ],
        }
    )

    intents = prefetch_intents(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        100,
        "root",
        {"root"},
        current_track=cat.get_track("root"),
        current_t_ms=0,
    )
    sad = intents["6"][0]
    assert sad["segment"]["v"] < -0.2
    assert sad["track_id"] != "root"


def test_prefetch_tree_depth_one_skips_l2():
    from app.catalog.normalize import normalize_catalog

    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_track("root", "Root", 0.0, 0.0), _track("other", "Other", 0.5, 0.5)],
        }
    )

    tree = prefetch_tree(cat.tracks, VA(v=0.0, ar=0.0), 100, "root", {"root"}, depth=1)
    assert tree["intents"]
    assert tree["l2"] == {}


def test_prefetch_l2_endpoint():
    from fastapi.testclient import TestClient

    from app.catalog.normalize import normalize_catalog
    from app.main import app

    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                _track("root", "Root", 0.0, 0.0),
                _track("joy_a", "Joy A", 0.8, 0.6),
                _track("calm_b", "Calm B", 0.0, -0.8),
            ],
        }
    )
    l1 = prefetch_tree(cat.tracks, VA(v=0.0, ar=0.0), 100, "root", {"root"}, depth=1)
    branches = {k: v[:1] for k, v in l1["intents"].items() if v}

    client = TestClient(app)
    resp = client.post(
        "/prefetch/l2",
        json={"current_track_id": "root", "l1_intents": branches},
    )
    assert resp.status_code == 200
    assert "l2" in resp.json()
