"""Audio proxy streams upstream without buffering the full file in memory."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.catalog.loader import catalog_store
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_audio_proxy_returns_streaming_response(client: TestClient):
    track = catalog_store.catalog.tracks[0]
    assert track.audio_url

    mock_resp = MagicMock()
    mock_resp.status_code = 206
    mock_resp.headers = {
        "content-type": "audio/mpeg",
        "content-length": "128",
        "content-range": "bytes 0-127/999999",
    }

    async def aiter_bytes(chunk_size=65536):
        yield b"fake-mp3-chunk"

    mock_resp.aiter_bytes = aiter_bytes
    mock_resp.aclose = AsyncMock()
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock(return_value=httpx.Request("GET", track.audio_url))
    mock_client.send = AsyncMock(return_value=mock_resp)
    mock_client.aclose = AsyncMock()

    with patch("app.routers.audio.httpx.AsyncClient", return_value=mock_client):
        with client.stream("GET", f"/tracks/{track.id}/audio", headers={"Range": "bytes=0-127"}) as resp:
            assert resp.status_code == 206
            assert resp.headers.get("accept-ranges") == "bytes"
            body = b"".join(resp.iter_bytes())

    assert body == b"fake-mp3-chunk"
    mock_resp.aclose.assert_awaited()
