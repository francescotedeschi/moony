from app.catalog.loader import CatalogStore, _resolve_catalog_name
from app.catalog.normalize import normalize_catalog


def test_resolve_catalog_name_from_jamendo_tags():
    assert _resolve_catalog_name({"jamendo_tags": ["chill"]}) == "Jamendo"


def test_resolve_catalog_name_explicit():
    assert _resolve_catalog_name({"catalog_name": "My Library"}) == "My Library"


def test_catalog_stats_includes_catalog_name():
    store = CatalogStore()
    store._loaded = True
    store._meta = {"catalog_name": "Jamendo", "catalog_schema": "moodpad-catalog-musicathon"}
    store._catalog = normalize_catalog({"catalog_schema": "moodpad-catalog-musicathon", "tracks": []})

    stats = store.stats()

    assert stats["catalog_name"] == "Jamendo"
    assert stats["track_count"] == 0


def test_catalog_stats_includes_mood_segment_mix():
    store = CatalogStore()
    store._loaded = True
    store._catalog = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                {
                    "id": "a",
                    "title": "A",
                    "artist": "A",
                    "duration_sec": 120,
                    "bpm": 100,
                    "audio_url": "https://example.com/a.mp3",
                    "segments": [
                        {"start_sec": 0, "end_sec": 60, "emotion_label": "joy", "v": 0.8, "ar": 0.6},
                        {"start_sec": 60, "end_sec": 120, "emotion_label": "sad", "v": -0.7, "ar": -0.5},
                    ],
                },
                {
                    "id": "b",
                    "title": "B",
                    "artist": "B",
                    "duration_sec": 60,
                    "bpm": 110,
                    "audio_url": "https://example.com/b.mp3",
                    "segments": [
                        {"start_sec": 0, "end_sec": 60, "emotion_label": "sad", "v": -0.7, "ar": -0.5},
                    ],
                },
            ],
        }
    )

    stats = store.stats()

    assert stats["segment_count"] == 3
    # 7-zone order: [energetic, happy, chilled, romantic, sad, dark, tense]
    assert stats["mood_labels"] == ["energetic", "happy", "chilled", "romantic", "sad", "dark", "tense"]
    assert stats["mood_segment_counts"][1] == 1  # happy (joy→happy)
    assert stats["mood_segment_counts"][4] == 2  # sad
    assert stats["mood_segment_share"][1] == round(1 / 3, 4)
    assert stats["dominant_mood_track_counts"][4] == 1
