"""Global play counts bias matching toward underplayed tracks."""

import os

import pytest

from app.catalog.normalize import normalize_catalog
from app.matching.core import _restrict_ranked_by_play_fairness, _track_pool, find_best_match
from app.models.catalog import VA
from app.play_stats.fairness import play_fairness_pool_bonus
from app.play_stats.store import PlayStatsStore


def _calm_track(tid: str) -> dict:
    return {
        "id": tid,
        "title": tid,
        "artist": "A",
        "duration_sec": 100.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": f"https://example.com/{tid}.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 8.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "intro",
                "emotion_label": "joy",
            },
            {
                "start_sec": 10.0,
                "end_sec": 50.0,
                "valence": -0.05,
                "arousal": -0.51,
                "label": "main",
                "emotion_label": "calm",
            },
            {
                "start_sec": 50.0,
                "end_sec": 100.0,
                "valence": -0.05,
                "arousal": -0.51,
                "label": "coda",
                "emotion_label": "calm",
            },
        ],
    }


def test_play_fairness_pool_bonus_grows_with_plays():
    assert play_fairness_pool_bonus(0) == 0.0
    assert play_fairness_pool_bonus(9) < play_fairness_pool_bonus(100)


def test_track_pool_prefers_underplayed_track():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_calm_track("often"), _calm_track("rare"), _calm_track("fresh")],
        }
    )
    target = VA(v=0.0, ar=-0.8)
    with_counts = _track_pool(
        cat.tracks,
        set(),
        target,
        "calm",
        limit=3,
        play_counts={"often": 80, "rare": 1, "fresh": 0},
    )
    assert [t.id for t in with_counts] == ["fresh"]


def test_restrict_ranked_keeps_unplayed_tier_only():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_calm_track("a"), _calm_track("b"), _calm_track("c")],
        }
    )
    ranked = [(0.1, cat.tracks[0]), (0.2, cat.tracks[1]), (0.3, cat.tracks[2])]
    out = _restrict_ranked_by_play_fairness(
        ranked,
        {"a": 5, "b": 0, "c": 12},
    )
    assert [t.id for _, t in out] == ["b"]


def _joy_track(tid: str, *, subtitles: bool = False) -> dict:
    row = {
        "id": tid,
        "title": tid,
        "artist": "A",
        "duration_sec": 60.0,
        "primary_emotion": "joy",
        "jamendo": {"audio_url": f"https://example.com/{tid}.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 10.0,
                "valence": 0.79,
                "arousal": 0.61,
                "label": "intro",
                "emotion_label": "joy",
            },
            {
                "start_sec": 10.0,
                "end_sec": 50.0,
                "valence": 0.79,
                "arousal": 0.61,
                "label": "main",
                "emotion_label": "joy",
            },
            {
                "start_sec": 50.0,
                "end_sec": 60.0,
                "valence": 0.79,
                "arousal": 0.61,
                "label": "outro",
                "emotion_label": "joy",
            },
        ],
    }
    if subtitles:
        row["musixmatch"] = {
            "track_id": f"mm-{tid}",
            "commontrack_id": f"ct-{tid}",
            "has_subtitles": 1,
            "has_lyrics": 1,
            "has_synced_subtitles": True,
        }
    return row


def test_find_session_seed_calm_opener():
    from app.matching.core import find_session_seed

    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                {
                    "id": "calm-opener",
                    "title": "calm-opener",
                    "artist": "A",
                    "duration_sec": 90.0,
                    "primary_emotion": "calm",
                    "jamendo": {"audio_url": "https://example.com/calm.mp3", "tags": []},
                    "segments": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 30.0,
                            "valence": -0.05,
                            "arousal": -0.51,
                            "label": "intro",
                            "emotion_label": "calm",
                        },
                        {
                            "start_sec": 30.0,
                            "end_sec": 90.0,
                            "valence": 0.79,
                            "arousal": 0.61,
                            "label": "main",
                            "emotion_label": "joy",
                        },
                    ],
                }
            ],
        }
    )
    result = find_session_seed(cat.tracks, set(), "calm", play_counts={})
    assert result is not None
    assert result[0].id == "calm-opener"
    assert result[8] == "chilled"


def test_find_joy_session_seed_prefers_zero_plays():
    from app.matching.core import find_joy_session_seed

    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_joy_track("played"), _joy_track("fresh")],
        }
    )
    result = find_joy_session_seed(
        cat.tracks,
        set(),
        play_counts={"played": 12, "fresh": 0},
    )
    assert result is not None
    assert result[0].id == "fresh"
    assert result[8] == "happy"


def test_find_session_seed_prefers_synced_subtitles():
    from app.matching.core import find_session_seed

    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                _joy_track("no-subs"),
                _joy_track("with-subs", subtitles=True),
            ],
        }
    )
    result = find_session_seed(cat.tracks, set(), "happy", play_counts={})
    assert result is not None
    assert result[0].id == "with-subs"
    assert result[0].musixmatch is not None
    assert result[0].musixmatch.has_synced_subtitles is True


def test_find_joy_session_seed_joy_only_at_first_segment():
    """Openers start at index 0; best_target_entry_for_emotion skips segment 0."""
    from app.matching.core import find_joy_session_seed

    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                {
                    "id": "opener",
                    "title": "opener",
                    "artist": "A",
                    "duration_sec": 120.0,
                    "primary_emotion": "joy",
                    "jamendo": {"audio_url": "https://example.com/opener.mp3", "tags": []},
                    "segments": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 20.0,
                            "valence": 0.79,
                            "arousal": 0.61,
                            "label": "intro",
                            "emotion_label": "joy",
                        },
                        {
                            "start_sec": 20.0,
                            "end_sec": 100.0,
                            "valence": -0.2,
                            "arousal": -0.3,
                            "label": "verse",
                            "emotion_label": "calm",
                        },
                    ],
                }
            ],
        }
    )
    result = find_joy_session_seed(cat.tracks, set(), play_counts={"opener": 0})
    assert result is not None
    assert result[0].id == "opener"
    assert result[2] == 0


def test_find_joy_session_seed_starts_at_first_segment():
    from app.matching.core import find_joy_session_seed

    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_joy_track("fresh")],
        }
    )
    result = find_joy_session_seed(cat.tracks, set(), play_counts={})
    assert result is not None
    track, seg, idx, _score, start_ms, entry_va, *_rest = result
    assert idx == 0
    assert seg.label == "intro"
    assert start_ms == track.segments[0].t_start
    assert entry_va.v == pytest.approx(0.79, abs=0.05)


def test_find_best_match_respects_play_counts():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_calm_track("heavy"), _calm_track("light")],
        }
    )
    result = find_best_match(
        cat.tracks,
        VA(v=0.0, ar=-0.8),
        VA(v=0.0, ar=0.0),
        110,
        set(),
        pad_only=True,
        play_counts={"heavy": 120, "light": 0},
    )
    assert result is not None
    assert result[0].id == "light"


@pytest.fixture()
def play_stats_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "plays.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from app.config import get_settings
    import app.db.session as db_session

    get_settings.cache_clear()
    db_session._engine = None
    db_session._session_factory = None
    store = PlayStatsStore()
    store.init()
    if not store.enabled:
        pytest.skip("sqlite play stats init failed")
    yield store
    get_settings.cache_clear()
    db_session._engine = None
    db_session._session_factory = None


def test_play_stats_store_records(play_stats_sqlite: PlayStatsStore):
    assert play_stats_sqlite.record_play("t1") == 1
    assert play_stats_sqlite.record_play("t1") == 2
    assert play_stats_sqlite.get_play_counts()["t1"] == 2
