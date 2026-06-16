"""
HTTP sanity: POST /prefetch (and /match) from a random catalog segment.

Guards the FastAPI router + catalog_store wiring, not only core.find_best_match.
"""

from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.matching.emotions import EMOTION_BRANCHES

MOOD_INTENT_IDS = {str(b.intent) for b in EMOTION_BRANCHES}

client = TestClient(app)


def _pick_random_segment(catalog, rng: random.Random):
    tracks = [t for t in catalog.tracks if t.segments]
    assert tracks, "no tracks with segments"
    track = rng.choice(tracks)
    seg = rng.choice(track.segments)
    t_ms = (seg.t_start + seg.t_end) // 2
    return track, seg, t_ms


@pytest.mark.skipif(
    client.get("/health").json().get("catalog", {}).get("track_count", 0) == 0,
    reason="catalog not loaded (check CATALOG_PATH)",
)
def test_prefetch_api_random_segment_returns_mood_branches(catalog):
    track, seg, t_ms = _pick_random_segment(catalog, random.Random(20260522))

    resp = client.post(
        "/prefetch",
        json={
            "current_track_id": track.id,
            "t_ms": t_ms,
            "position": {"v": seg.v, "ar": seg.ar},
            "bpm_current": track.bpm,
            "depth": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["current_track_id"] == track.id
    assert body["t_ms"] == t_ms
    assert isinstance(body["intents"], dict)
    assert isinstance(body["l2"], dict)

    mood_branches = {
        intent_id: candidates
        for intent_id, candidates in body["intents"].items()
        if intent_id in MOOD_INTENT_IDS and candidates
    }
    assert len(mood_branches) >= 4, (
        f"POST /prefetch returned too few mood branches: "
        f"{ {k: len(v) for k, v in body['intents'].items()} }"
    )

    for intent_id, candidates in mood_branches.items():
        top = candidates[0]
        assert top.get("track_id"), f"intent {intent_id}: missing track_id"
        assert top.get("segment"), f"intent {intent_id}: missing segment"
        assert top.get("audio_start_ms", 0) >= 0


@pytest.mark.skipif(
    client.get("/health").json().get("catalog", {}).get("track_count", 0) == 0,
    reason="catalog not loaded (check CATALOG_PATH)",
)
def test_match_api_random_segment_returns_entry(catalog):
    track, seg, t_ms = _pick_random_segment(catalog, random.Random(20260522))

    resp = client.post(
        "/match",
        json={
            "position": {"v": seg.v, "ar": seg.ar},
            "direction": {"v": 0.0, "ar": 0.0},
            "bpm_current": track.bpm,
            "exclude_ids": [],
            "current_track_id": track.id,
            "current_t_ms": t_ms,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["track_id"]
    assert body["title"]
    assert body["start_ms"] >= 0
    assert body["segment"]
    assert "v" in body["segment"] and "ar" in body["segment"]
    assert body.get("mood_quality") in ("excellent", "good", "weak", "poor", None)
