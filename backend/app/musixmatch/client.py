import re
import time
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.models.api import LyricLine

LRC_TIMESTAMP = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")


def _lrc_timestamp_ms(mm: str, ss: str, frac: str | None) -> int:
    minutes = int(mm)
    seconds = int(ss)
    ms = minutes * 60_000 + seconds * 1000
    if frac:
        padded = frac.ljust(3, "0")[:3]
        ms += int(padded)
    return ms



@dataclass
class CachedLyrics:
    lines: list[LyricLine]
    lyrics_copyright: str
    pixel_tracking_url: str | None
    script_tracking_url: str | None
    source: str
    expires_at: float


class LyricsCache:
    """In-memory session cache — not persistent Musixmatch storage."""

    def __init__(self, ttl: int, max_entries: int) -> None:
        self._ttl = ttl
        self._max = max_entries
        self._store: dict[str, CachedLyrics] = {}

    def get(self, key: str) -> CachedLyrics | None:
        entry = self._store.get(key)
        if not entry:
            return None
        if time.time() > entry.expires_at:
            del self._store[key]
            return None
        return entry

    def set(self, key: str, value: CachedLyrics) -> None:
        if len(self._store) >= self._max:
            oldest = min(self._store, key=lambda k: self._store[k].expires_at)
            del self._store[oldest]
        self._store[key] = value


class MusixmatchClient:
    BASE = "https://api.musixmatch.com/ws/1.1"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.musixmatch_api_key
        self._cache = LyricsCache(
            settings.lyrics_cache_ttl_seconds,
            settings.lyrics_cache_max_entries,
        )

    def _params(self, **kwargs: str) -> dict[str, str]:
        return {"apikey": self._api_key, **{k: v for k, v in kwargs.items() if v}}

    async def _get(self, path: str, params: dict[str, str]) -> dict:
        if not self._api_key:
            return {"message": {"header": {"status_code": 401}, "body": {}}}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.BASE}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def parse_lrc(body: str) -> list[LyricLine]:
        lines: list[LyricLine] = []
        for i, raw in enumerate(body.strip().splitlines()):
            stripped = raw.strip()
            if not stripped:
                continue
            timestamps = list(LRC_TIMESTAMP.finditer(stripped))
            if not timestamps:
                continue
            text = LRC_TIMESTAMP.sub("", stripped).strip()
            if not text:
                continue
            for match in timestamps:
                mm, ss, frac = match.groups()
                t_ms = _lrc_timestamp_ms(mm, ss, frac)
                lines.append(LyricLine(t_ms=t_ms, text=text, line_index=len(lines)))
        lines.sort(key=lambda line: (line.t_ms, line.line_index))
        return [
            LyricLine(t_ms=line.t_ms, text=line.text, line_index=idx)
            for idx, line in enumerate(lines)
        ]

    async def get_subtitle_lines(
        self,
        *,
        commontrack_id: str | None = None,
        track_id: str | None = None,
    ) -> tuple[list[LyricLine], str, str | None, str | None] | None:
        cache_key = f"sub:{commontrack_id or track_id}"
        cached = self._cache.get(cache_key)
        if cached:
            return (
                cached.lines,
                cached.lyrics_copyright,
                cached.pixel_tracking_url,
                cached.script_tracking_url,
            )

        params = self._params(
            commontrack_id=commontrack_id or "",
            track_id=track_id or "",
            subtitle_format="lrc",
        )
        data = await self._get("/track.subtitle.get", params)
        header = data.get("message", {}).get("header", {})
        if header.get("status_code") != 200:
            return None

        subtitle = data.get("message", {}).get("body", {}).get("subtitle")
        if not subtitle or not subtitle.get("subtitle_body"):
            return None

        lines = self.parse_lrc(subtitle["subtitle_body"])
        copyright_text = subtitle.get("lyrics_copyright", "")
        pixel = subtitle.get("pixel_tracking_url")
        script = subtitle.get("script_tracking_url")

        settings = get_settings()
        self._cache.set(
            cache_key,
            CachedLyrics(
                lines=lines,
                lyrics_copyright=copyright_text,
                pixel_tracking_url=pixel,
                script_tracking_url=script,
                source="subtitle",
                expires_at=time.time() + settings.lyrics_cache_ttl_seconds,
            ),
        )
        return lines, copyright_text, pixel, script

    async def get_snippet(
        self,
        *,
        commontrack_id: str | None = None,
        track_id: str | None = None,
    ) -> tuple[list[LyricLine], str, str | None, str | None] | None:
        params = self._params(
            commontrack_id=commontrack_id or "",
            track_id=track_id or "",
        )
        data = await self._get("/track.snippet.get", params)
        if data.get("message", {}).get("header", {}).get("status_code") != 200:
            return None

        snippet = data.get("message", {}).get("body", {}).get("snippet")
        if not snippet:
            return None

        text = snippet.get("snippet_body", "")
        lines = [LyricLine(t_ms=0, text=text, line_index=0)] if text else []
        return (
            lines,
            snippet.get("lyrics_copyright", ""),
            snippet.get("pixel_tracking_url"),
            snippet.get("script_tracking_url"),
        )

    async def get_analysis(self, track_id: str) -> dict | None:
        data = await self._get("/track.lyrics.analysis.get", self._params(track_id=track_id))
        if data.get("message", {}).get("header", {}).get("status_code") != 200:
            return None
        return data.get("message", {}).get("body", {}).get("analysis")


musixmatch_client = MusixmatchClient()
