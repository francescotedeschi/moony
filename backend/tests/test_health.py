import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "moony-api"
    assert "catalog" in data
    assert data["catalog"].get("lyrics_mode") in ("off", "musixmatch")


def test_catalog_stats():
    resp = client.get("/catalog/stats")
    assert resp.status_code == 200
