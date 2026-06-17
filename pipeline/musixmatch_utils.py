"""Shared Musixmatch matching helpers for offline pipeline scripts."""

from __future__ import annotations

import html
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.catalog.sections import raw_section_label, raw_track_sections  # noqa: E402
MUSIXMATCH_BASE = "https://api.musixmatch.com/ws/1.1"

TITLE_CLEAN_RE = re.compile(
    r"\s*[\(\[](?:album version|feat\.?|ft\.?|prod\.?|with|remix|mix|wav)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
LRC_TIMESTAMP = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")


def count_lrc_timed_lines(body: str) -> int:
    """Count non-empty lyric lines that carry at least one LRC timestamp."""
    count = 0
    for raw in (body or "").strip().splitlines():
        stripped = raw.strip()
        if not stripped or not LRC_TIMESTAMP.search(stripped):
            continue
        text = LRC_TIMESTAMP.sub("", stripped).strip()
        if text:
            count += 1
    return count


def fetch_has_synced_subtitles(
    client: httpx.Client,
    *,
    api_key: str,
    track_id: str | None,
    commontrack_id: str | None,
) -> tuple[bool, int]:
    """Live Musixmatch check: True when subtitle_body contains timed LRC lines."""
    if not track_id and not commontrack_id:
        return False, 0

    resp = client.get(
        f"{MUSIXMATCH_BASE}/track.subtitle.get",
        params={
            "apikey": api_key,
            "track_id": track_id or "",
            "commontrack_id": commontrack_id or "",
            "subtitle_format": "lrc",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    header = data.get("message", {}).get("header", {})
    if int(header.get("status_code") or 0) != 200:
        return False, 0

    subtitle = data.get("message", {}).get("body", {}).get("subtitle") or {}
    body = subtitle.get("subtitle_body") or ""
    line_count = count_lrc_timed_lines(body)
    return line_count > 0, line_count


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def unescape(text: str) -> str:
    return html.unescape(text or "").strip()


def clean_title_for_match(title: str) -> str:
    cleaned = unescape(title)
    while True:
        next_title = TITLE_CLEAN_RE.sub("", cleaned).strip()
        if next_title == cleaned:
            break
        cleaned = next_title
    return cleaned


def pending_musixmatch_block() -> dict[str, Any]:
    return {
        "commontrack_id": None,
        "track_id": None,
        "has_lyrics": 0,
        "has_subtitles": 0,
        "has_synced_subtitles": False,
        "match_status": "pending",
    }


def musixmatch_from_match(track: dict[str, Any]) -> dict[str, Any]:
    return {
        "commontrack_id": str(track["commontrack_id"]),
        "track_id": str(track["track_id"]),
        "has_lyrics": int(track.get("has_lyrics") or 0),
        "has_subtitles": int(track.get("has_subtitles") or 0),
        "has_synced_subtitles": False,
        "match_status": "matched",
    }


def matcher_track_get(
    client: httpx.Client,
    *,
    api_key: str,
    title: str,
    artist: str,
) -> tuple[int, dict[str, Any] | None]:
    resp = client.get(
        f"{MUSIXMATCH_BASE}/matcher.track.get",
        params={
            "apikey": api_key,
            "q_track": title,
            "q_artist": artist,
            "f_has_lyrics": "1",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    header = data.get("message", {}).get("header", {})
    status = int(header.get("status_code") or 0)
    if status != 200:
        return status, None
    body_track = data.get("message", {}).get("body", {}).get("track")
    return status, body_track


def match_track(
    client: httpx.Client,
    *,
    api_key: str,
    title: str,
    artist: str,
) -> dict[str, Any] | None:
    """Try matcher with raw title, then a cleaned variant."""
    attempts = [
        (unescape(title), unescape(artist)),
        (clean_title_for_match(title), unescape(artist)),
    ]
    seen: set[tuple[str, str]] = set()
    for q_track, q_artist in attempts:
        key = (q_track.casefold(), q_artist.casefold())
        if not q_track or not q_artist or key in seen:
            continue
        seen.add(key)
        status, match = matcher_track_get(
            client,
            api_key=api_key,
            title=q_track,
            artist=q_artist,
        )
        if match:
            return match
        if status not in (404, 200):
            break
    return None


def is_instrumental_catalog_track(track: dict[str, Any]) -> bool:
    """Skip tracks with no vocal segments (MOSS descriptions + Jamendo tags)."""
    tags = [t.lower() for t in ((track.get("jamendo") or {}).get("tags") or [])]
    if "instrumental" in tags and "vocal" not in tags and "voice" not in tags:
        return True

    segments = raw_track_sections(track)
    if not segments:
        return "instrumental" in tags

    vocal_segments = 0
    for seg in segments:
        label = raw_section_label(seg)
        desc = (seg.get("description") or "").lower()
        if label == "instrumental" or "voice: instrumental" in desc:
            continue
        if "lyrics topic: none (instrumental)" in desc:
            continue
        vocal_segments += 1
    return vocal_segments == 0


def is_instrumental_jamendo(row: dict[str, Any]) -> bool:
    musicinfo = row.get("musicinfo") or {}
    if musicinfo.get("vocalinstrumental") == "instrumental":
        return True
    tags = flatten_jamendo_tags(musicinfo)
    lowered = [t.lower() for t in tags]
    return "instrumental" in lowered and "vocal" not in lowered and "voice" not in lowered


def flatten_jamendo_tags(musicinfo: dict[str, Any] | None) -> list[str]:
    if not musicinfo:
        return []
    grouped = musicinfo.get("tags") or {}
    tags: list[str] = []
    for key in ("genres", "instruments", "vartags"):
        for tag in grouped.get(key) or []:
            if tag not in tags:
                tags.append(tag)
    return tags


def estimate_bpm(duration_sec: float, tags: list[str], primary_emotion: str = "calm") -> int:
    tag_str = " ".join(tags).lower()
    if any(k in tag_str for k in ("ambient", "slow", "peaceful", "calm")):
        return 80
    if any(k in tag_str for k in ("dance", "electronic", "energetic", "fast")):
        return 128
    if primary_emotion in ("calm", "melancholic", "dreamy"):
        return 85
    if primary_emotion in ("energetic", "playful", "tense"):
        return 120
    if duration_sec > 240:
        return 90
    return 110


def estimate_primary_emotion(tags: list[str]) -> str:
    tag_str = " ".join(tags).lower()
    if any(k in tag_str for k in ("sad", "melancholic", "melancholy")):
        return "melancholic"
    if any(k in tag_str for k in ("happy", "uplifting", "joy")):
        return "hopeful"
    if any(k in tag_str for k in ("energetic", "dance", "rock")):
        return "energetic"
    if any(k in tag_str for k in ("tense", "dark")):
        return "tense"
    return "calm"


def catalog_jamendo_ids(catalog: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    for track in catalog.get("tracks", []):
        tid = str(track.get("id", ""))
        if tid.startswith("jamendo_"):
            try:
                ids.add(int(tid.replace("jamendo_", "")))
            except ValueError:
                pass
        jamendo = track.get("jamendo") or {}
        raw_id = jamendo.get("track_id")
        if raw_id is not None:
            try:
                ids.add(int(raw_id))
            except (TypeError, ValueError):
                pass
    return ids


def jamendo_row_to_catalog_track(row: dict[str, Any], mm_match: dict[str, Any]) -> dict[str, Any]:
    jamendo_id = int(row["id"])
    musicinfo = row.get("musicinfo") or {}
    tags = flatten_jamendo_tags(musicinfo)
    duration_sec = float(row.get("duration") or 180)
    primary_emotion = estimate_primary_emotion(tags)
    return {
        "id": f"jamendo_{jamendo_id}",
        "title": unescape(str(row.get("name", ""))),
        "artist": unescape(str(row.get("artist_name", ""))),
        "duration_sec": duration_sec,
        "bpm": estimate_bpm(duration_sec, tags, primary_emotion),
        "primary_emotion": primary_emotion,
        "jamendo": {
            "track_id": jamendo_id,
            "audio_url": str(row.get("audio") or ""),
            "audiodownload_allowed": bool(row.get("audiodownload_allowed")),
            "license_cc": str(row.get("license_ccurl") or ""),
            "tags": tags,
            "listens_total": 0,
            "popularity_total": 0.0,
        },
        "musixmatch": musixmatch_from_match(mm_match),
        "segments": [],
        "transitions": [],
        "analyzer": "pending-moss",
        "moss_status": "pending",
    }


def sleep_between_calls(delay_sec: float) -> None:
    if delay_sec > 0:
        time.sleep(delay_sec)
