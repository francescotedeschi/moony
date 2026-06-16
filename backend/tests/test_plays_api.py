"""HTTP API for global play counts."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db as db_pkg
from app.config import get_settings
from app.main import app
from app.play_stats import play_stats_store


@pytest.fixture
def plays_client(tmp_path, monkeypatch, catalog):
    """Isolated SQLite file + fresh engine (avoids :memory: and cross-test leakage)."""
    db_path = tmp_path / "plays_api.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    db_pkg.session._engine = None
    db_pkg.session._session_factory = None
    play_stats_store._enabled = False
    play_stats_store._counts = {}
    play_stats_store._counts_loaded_at = 0.0
    play_stats_store.init()
    if not play_stats_store.enabled:
        pytest.skip("play stats DB not available in test env")
    with TestClient(app) as client:
        yield client


def test_play_count_unknown_track_404(plays_client):
    resp = plays_client.get("/tracks/nonexistent_track_xyz/play-count")
    assert resp.status_code == 404


def test_play_count_and_record_increment(plays_client, catalog):
    track_id = catalog.tracks[0].id

    before = plays_client.get(f"/tracks/{track_id}/play-count")
    assert before.status_code == 200
    data = before.json()
    assert data["track_id"] == track_id
    assert data["stats_enabled"] is True
    assert data["play_count"] >= 0
    start = data["play_count"]

    played = plays_client.post(f"/tracks/{track_id}/played")
    assert played.status_code == 200
    pdata = played.json()
    assert pdata["play_count"] == start + 1
    assert pdata["stats_enabled"] is True

    after = plays_client.get(f"/tracks/{track_id}/play-count")
    assert after.json()["play_count"] == start + 1


def test_health_includes_play_stats(plays_client):
    resp = plays_client.get("/health")
    assert resp.status_code == 200
    ps = resp.json()["play_stats"]
    assert ps["enabled"] is True
    assert "total_plays" in ps
