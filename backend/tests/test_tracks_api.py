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
def test_track_detail_with_energy_summary():
    health = client.get("/health").json()
    assert health["catalog"].get("with_energy", 0) >= 0

    stats = client.get("/catalog/stats").json()
    if stats.get("with_energy", 0) == 0:
        pytest.skip("no tracks with Cyanite energy curve in catalog")

    from app.catalog.loader import catalog_store

    catalog_store.load()
    track = next((t for t in catalog_store.catalog.tracks if t.has_energy_curve), None)
    if not track:
        pytest.skip("no energy tracks")

    resp = client.get(f"/tracks/{track.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_energy_curve"] is True
    assert body["energy_samples"] == len(track.energy_curve)
    assert "energy_curve" in body
    assert "segments" in body
    assert "local_audio_path" not in str(body)


def test_energy_endpoint_and_at():
    from app.catalog.loader import catalog_store

    catalog_store.load()
    track = next((t for t in catalog_store.catalog.tracks if t.has_energy_curve), None)
    if not track:
        pytest.skip("no energy tracks")

    resp = client.get(f"/tracks/{track.id}/energy")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["energy_curve"]) >= 2
    assert len(body["energy_curve_timestamps_ms"]) == len(body["energy_curve"])

    preview = client.get(f"/tracks/{track.id}/energy/preview")
    assert preview.status_code == 200
    assert isinstance(preview.json(), list)

    at = client.get(f"/tracks/{track.id}/energy/at", params={"t_sec": 0})
    assert at.status_code == 200
    payload = at.json()
    assert "energy" in payload
    assert payload["has_energy_curve"] is True
    assert "valence" in payload
    assert "arousal" in payload

    legacy = next((t for t in catalog_store.catalog.tracks if not t.has_energy_curve), None)
    if legacy:
        fb = client.get(f"/tracks/{legacy.id}/energy/at", params={"t_sec": 1.0})
        assert fb.status_code == 200
        assert fb.json()["has_energy_curve"] is False


def test_motion_endpoints_removed():
    from app.catalog.loader import catalog_store

    catalog_store.load()
    if not catalog_store.catalog.tracks:
        pytest.skip("empty catalog")
    track_id = catalog_store.catalog.tracks[0].id
    assert client.get(f"/tracks/{track_id}/motion").status_code == 404
    assert client.get(f"/tracks/{track_id}/motion/at", params={"t_sec": 0}).status_code == 404
    assert client.get(f"/tracks/{track_id}/motion/preview").status_code == 404
