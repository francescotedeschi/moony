"""Same-mood handoff prefers tracks with mood_distribution share ≥ 0.5."""

from app.catalog.mood_distribution import mood_share_for_label
from app.catalog.normalize import normalize_catalog
from app.matching.core import find_best_match, prefetch_intents
from app.matching.emotions import EMOTION_BRANCHES, SAME_MOOD_INTENT
from app.models.catalog import VA


def _joy_track(track_id: str, *, joy_segments: int, other_label: str, other_segments: int) -> dict:
    segments = []
    t = 0.0
    for i in range(joy_segments):
        segments.append(
            {
                "start_sec": t,
                "end_sec": t + 10,
                "valence": 0.79,
                "arousal": 0.61,
                "label": f"joy{i}",
                "emotion_label": "joy",
            }
        )
        t += 10
    for i in range(other_segments):
        segments.append(
            {
                "start_sec": t,
                "end_sec": t + 10,
                "valence": -0.05,
                "arousal": -0.51,
                "label": f"other{i}",
                "emotion_label": other_label,
            }
        )
        t += 10
    return {
        "id": track_id,
        "title": track_id,
        "artist": "A",
        "duration_sec": t,
        "primary_emotion": "joy",
        "jamendo": {"audio_url": f"https://example.com/{track_id}.mp3", "tags": []},
        "segments": segments,
    }


def _current_joy_track() -> dict:
    return {
        "id": "current_joy",
        "title": "Current",
        "artist": "Live",
        "duration_sec": 40.0,
        "primary_emotion": "joy",
        "jamendo": {"audio_url": "https://example.com/current.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0,
                "end_sec": 20,
                "valence": 0.79,
                "arousal": 0.61,
                "label": "verse",
                "emotion_label": "joy",
            },
            {
                "start_sec": 20,
                "end_sec": 30,
                "valence": 0.79,
                "arousal": 0.61,
                "label": "chorus",
                "emotion_label": "joy",
            },
            {
                "start_sec": 30,
                "end_sec": 40,
                "valence": 0.0,
                "arousal": -0.2,
                "label": "outro",
                "emotion_label": "calm",
            },
        ],
    }


def test_same_mood_prefetch_prefers_mood_distribution_at_least_half():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                _current_joy_track(),
                _joy_track("shallow_joy", joy_segments=1, other_label="calm", other_segments=3),
                _joy_track("deep_joy", joy_segments=3, other_label="calm", other_segments=1),
            ],
        }
    )
    current = next(t for t in cat.tracks if t.id == "current_joy")
    shallow = next(t for t in cat.tracks if t.id == "shallow_joy")
    deep = next(t for t in cat.tracks if t.id == "deep_joy")

    assert mood_share_for_label(shallow, "joy") == 0.25
    assert mood_share_for_label(deep, "joy") == 0.75

    intents = prefetch_intents(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        120,
        "current_joy",
        {"current_joy"},
        current_track=current,
        current_t_ms=15_000,
        intent_filter=frozenset({SAME_MOOD_INTENT}),
    )
    same = intents[str(SAME_MOOD_INTENT)]
    assert same
    assert same[0]["track_id"] == "deep_joy"


def test_same_mood_only_prefetch_returns_single_intent_key():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_current_joy_track(), _joy_track("deep_joy", joy_segments=4, other_label="calm", other_segments=0)],
        }
    )
    current = cat.tracks[0]
    intents = prefetch_intents(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        120,
        "current_joy",
        {"current_joy"},
        current_track=current,
        current_t_ms=15_000,
        intent_filter=frozenset({SAME_MOOD_INTENT}),
    )
    assert set(intents.keys()) == {str(SAME_MOOD_INTENT)}


def test_pad_joy_intent_restrict_mood_share_prefers_deep_joy():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                _current_joy_track(),
                _joy_track("shallow_joy", joy_segments=1, other_label="calm", other_segments=3),
                _joy_track("deep_joy", joy_segments=4, other_label="calm", other_segments=0),
            ],
        }
    )
    current = cat.tracks[0]
    joy_intent = next(b.intent for b in EMOTION_BRANCHES if b.name == "Joy")
    intents = prefetch_intents(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        120,
        "current_joy",
        {"current_joy"},
        current_track=current,
        current_t_ms=15_000,
        intent_filter=frozenset({joy_intent}),
        restrict_mood_share_intents=frozenset({joy_intent}),
    )
    assert set(intents.keys()) == {str(joy_intent)}
    assert intents[str(joy_intent)][0]["track_id"] == "deep_joy"


def test_same_mood_handoff_replays_when_session_excludes_exhaust_catalog():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                _current_joy_track(),
                _joy_track("deep_joy", joy_segments=4, other_label="calm", other_segments=0),
            ],
        }
    )
    current = next(t for t in cat.tracks if t.id == "current_joy")
    other = next(t for t in cat.tracks if t.id == "deep_joy")
    played = {current.id, other.id}

    result = find_best_match(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        VA(v=0.0, ar=0.0),
        120,
        played,
        25_000,
        current_track=current,
        same_mood_handoff=True,
    )
    assert result is not None
    assert result[0].id == "deep_joy"
