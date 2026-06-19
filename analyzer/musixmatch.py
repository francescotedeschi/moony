"""Musixmatch API client — fetch synced subtitles (runtime only, never persisted)."""



from __future__ import annotations



import re

import time

from dataclasses import dataclass



import httpx



MUSIXMATCH_API = "https://api.musixmatch.com/ws/1.1"



_LRC_LINE_RE = re.compile(

    r"""

    ^\s*

    [\[(]

    (?P<mm>\d{1,2})

    :

    (?P<ss>\d{2})

    (?:\.(?P<cs>\d{1,3}))?

    [\])]

    \s*

    (?P<text>.+?)

    \s*$

    """,

    re.VERBOSE,

)





@dataclass(frozen=True)

class LyricLine:

    time_sec: float

    text: str





@dataclass(frozen=True)

class TimestampedLyrics:

    """In-memory lyrics with timestamps — must not be written to catalog JSON."""



    lines: tuple[LyricLine, ...]

    language: str = ""



    def format_for_prompt(self, *, start_sec: float | None = None, end_sec: float | None = None) -> str:

        selected = self.lines

        if start_sec is not None or end_sec is not None:

            lo = start_sec if start_sec is not None else 0.0

            hi = end_sec if end_sec is not None else float("inf")

            selected = tuple(ln for ln in self.lines if lo <= ln.time_sec < hi)

        if not selected:

            return "(no synced lyrics in this time range)"

        return "\n".join(f"[{_format_mmss(ln.time_sec)}] {ln.text}" for ln in selected)



    def __bool__(self) -> bool:

        return bool(self.lines)





class MusixmatchClient:

    def __init__(self, api_key: str, *, sleep_sec: float = 0.2) -> None:

        self._api_key = api_key.strip()

        self._sleep_sec = sleep_sec

        self._http = httpx.Client(timeout=30.0)



    def close(self) -> None:

        self._http.close()



    def fetch_subtitle(self, track_id: str | int) -> TimestampedLyrics | None:

        if not self._api_key:

            return None

        tid = str(track_id).strip()

        if not tid:

            return None



        payload = self._get("track.subtitle.get", {"track_id": tid})

        subtitle = (payload.get("subtitle") or {}) if payload else {}

        body = str(subtitle.get("subtitle_body") or "").strip()

        language = str(subtitle.get("subtitle_language") or "")

        if body:

            lines = parse_subtitle_body(body)

            if lines:

                return TimestampedLyrics(lines=tuple(lines), language=language)



        lyrics_payload = self._get("track.lyrics.get", {"track_id": tid})

        lyrics_block = (lyrics_payload.get("lyrics") or {}) if lyrics_payload else {}

        plain = str(lyrics_block.get("lyrics_body") or "").strip()

        if not plain:

            return None

        lines = _plain_lines_to_timestamped(plain)

        return TimestampedLyrics(lines=tuple(lines), language=language) if lines else None



    def fetch_synced_subtitle(self, track_id: str | int) -> TimestampedLyrics | None:

        """Return lyrics only when Musixmatch provides timestamped LRC lines."""

        lyrics = self.fetch_subtitle(track_id)

        if lyrics and lyrics.lines:

            return lyrics

        return None



    def _get(self, method: str, params: dict[str, str]) -> dict | None:

        query = {"apikey": self._api_key, **params}

        resp = self._http.get(f"{MUSIXMATCH_API}/{method}", params=query)

        resp.raise_for_status()

        data = resp.json()

        header = (data.get("message") or {}).get("header") or {}

        code = int(header.get("status_code") or 0)

        if code != 200:

            return None

        body = (data.get("message") or {}).get("body") or {}

        time.sleep(self._sleep_sec)

        return body





def has_synced_lyrics(lyrics: TimestampedLyrics | None) -> bool:

    return bool(lyrics and lyrics.lines)





def parse_subtitle_body(body: str) -> list[LyricLine]:

    lines: list[LyricLine] = []

    for raw in body.splitlines():

        match = _LRC_LINE_RE.match(raw.strip())

        if not match:

            continue

        mm = int(match.group("mm"))

        ss = int(match.group("ss"))

        cs_raw = match.group("cs") or "0"

        cs = int(cs_raw)

        frac = cs / (10 ** len(cs_raw))

        time_sec = mm * 60 + ss + frac

        text = match.group("text").strip()

        if text:

            lines.append(LyricLine(time_sec=round(time_sec, 3), text=text))

    return sorted(lines, key=lambda ln: ln.time_sec)





def _plain_lines_to_timestamped(body: str) -> list[LyricLine]:

    rows = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.startswith("***")]

    if not rows:

        return []

    step = 4.0

    return [LyricLine(time_sec=round(i * step, 3), text=row) for i, row in enumerate(rows)]





def _format_mmss(time_sec: float) -> str:

    total = max(0, int(time_sec))

    mm, ss = divmod(total, 60)

    return f"{mm:02d}:{ss:02d}"

