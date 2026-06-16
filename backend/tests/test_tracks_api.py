import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_track_detail_404():
    resp = client.get("/tracks/nonexistent_track_xyz")
    assert resp.status_code == 404


@pytest.mark.skipif(
    client.get("/health").json().get("catalog", {}).get("track_count", 0) == 0,
    reason="empty catalog",
)
def test_track_detail_with_motion_summary():
    health = client.get("/health").json()
    assert health["catalog"].get("with_motion", 0) >= 0

    stats = client.get("/catalog/stats").json()
    if stats.get("with_motion", 0) == 0:
        pytest.skip("no tracks with motion in catalog")

    # Pick any loaded track from stats — need an id; use timeline from match flow
    from app.catalog.loader import catalog_store

    catalog_store.load()
    track = next((t for t in catalog_store.catalog.tracks if t.has_motion), None)
    if not track:
        pytest.skip("no motion tracks")

    resp = client.get(f"/tracks/{track.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_motion"] is True
    assert body["motion_samples"] == len(track.motion.energy)
    assert "motion" in body
    assert "segments" in body
    assert "local_audio_path" not in str(body)


def test_motion_endpoint_and_at():
    from app.catalog.loader import catalog_store

    catalog_store.load()
    track = next((t for t in catalog_store.catalog.tracks if t.has_motion), None)
    if not track:
        pytest.skip("no motion tracks")

    resp = client.get(f"/tracks/{track.id}/motion")
    assert resp.status_code == 200
    assert "hop_sec" in resp.json()

    at = client.get(f"/tracks/{track.id}/motion/at", params={"t_sec": 0})
    assert at.status_code == 200
    assert "mood" in at.json()
    assert at.json()["has_motion"] is True

    legacy = next((t for t in catalog_store.catalog.tracks if not t.has_motion), None)
    if legacy:
        fb = client.get(f"/tracks/{legacy.id}/motion/at", params={"t_sec": 1.0})
        assert fb.status_code == 200
        assert fb.json()["has_motion"] is False
