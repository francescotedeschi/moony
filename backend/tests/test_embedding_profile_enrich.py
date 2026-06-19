from app.catalog.embedding_profile import (
    EMBEDDING_PROFILE,
    enrich_catalog_embedding_profile,
    enrich_section_fields,
    resolve_track_bpm,
    section_description,
)


def _estimate_bpm(duration_sec: float, tags: list[str], primary_emotion: str) -> int:
    return 120


def test_enrich_section_fields():
    section: dict = {"structure_label": "intro"}
    assert enrich_section_fields(section, track_bpm=89) is True
    assert section["bpm"] == 89
    assert section["embedding_profile"] == EMBEDDING_PROFILE
    assert enrich_section_fields(section, track_bpm=89) is False


def test_enrich_catalog_v17_sections():
    data = {
        "tracks": [
            {
                "id": "t1",
                "bpm": 95,
                "sections": [
                    {
                        "start_sec": 0,
                        "end_sec": 10,
                        "structure_label": "intro",
                        "description": "Voice: instrumental",
                    }
                ],
            }
        ]
    }
    tracks, sections = enrich_catalog_embedding_profile(data, estimate_bpm=_estimate_bpm)
    assert data["embedding_profile"] == EMBEDDING_PROFILE
    assert tracks == 1
    assert sections == 1
    assert data["tracks"][0]["sections"][0]["bpm"] == 95


def test_resolve_track_bpm_falls_back_to_estimate():
    track = {
        "duration_sec": 200,
        "primary_emotion": "energetic",
        "jamendo": {"tags": ["dance"]},
    }
    assert resolve_track_bpm(track, estimate_bpm=_estimate_bpm) == 120


def test_section_description_uses_description():
    assert section_description({"description": "Voice: instrumental"}) == "Voice: instrumental"
