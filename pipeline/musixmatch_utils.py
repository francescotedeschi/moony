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


GOSPEL_JAMENDO_TAGS = frozenset(
    {"gospel", "christian", "worship", "spiritual", "ccm", "religious"}
)

WORSHIP_OPENING_RE = re.compile(
    r"(your father above|from your father|father above|land of the living|"
    r"grace is handed|through christ|faith in the lord|praise the lord|"
    r"holy spirit|jesus christ|hallelujah|kingdom of heaven|savior of|"
    r"o lord my god|\bthy staff\b|staff and rod|ears to hear, my jesus|"
    r"foreshadow of your glory|be not silent to me|knowledge of your will|"
    r"higher purpose than god|god's love|never know a higher purpose)",
    re.IGNORECASE,
)


def parse_lrc_lines(body: str) -> list[tuple[int, str]]:
    """Return (t_ms, text) pairs sorted by timestamp."""
    lines: list[tuple[int, str]] = []
    for raw in (body or "").strip().splitlines():
        stripped = raw.strip()
        match = LRC_TIMESTAMP.search(stripped)
        if not match:
            continue
        mm, ss, frac = match.groups()
        ms = int(mm) * 60_000 + int(ss) * 1000
        if frac:
            ms += int(frac.ljust(3, "0")[:3])
        text = LRC_TIMESTAMP.sub("", stripped).strip().lower()
        if text:
            lines.append((ms, text))
    lines.sort(key=lambda row: row[0])
    return lines


def opening_lyric_text(lines: list[tuple[int, str]], window_ms: int = 60_000) -> str:
    return " ".join(text for t_ms, text in lines if t_ms < window_ms)


def jamendo_tags(track: dict[str, Any]) -> set[str]:
    tags = (track.get("jamendo") or {}).get("tags") or track.get("jamendo_tags") or []
    return {str(tag).lower() for tag in tags if tag}


def normalize_match_text(value: str) -> str:
    s = unescape(value).casefold()
    s = re.sub(r"\b(feat\.?|ft\.?|featuring)\b", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def artist_name_tokens(value: str) -> list[str]:
    """Split artist string into comparable name tokens."""
    s = unescape(value).casefold()
    s = re.sub(r"\b(feat\.?|ft\.?|featuring)\b.*", "", s)
    parts = re.split(r"[,/&]|\band\b", s)
    tokens: list[str] = []
    for part in parts:
        normalized = re.sub(r"[^a-z0-9]+", "", part.strip())
        if len(normalized) >= 3:
            tokens.append(normalized)
    return tokens


def artists_match(catalog_artist: str, mm_artist: str) -> bool:
    cat_norm = normalize_match_text(catalog_artist)
    mm_norm = normalize_match_text(mm_artist)
    if cat_norm in mm_norm or mm_norm in cat_norm:
        return True

    cat_tokens = artist_name_tokens(catalog_artist)
    mm_tokens = artist_name_tokens(mm_artist)
    if not cat_tokens or not mm_tokens:
        return True

    if len(cat_tokens) == 1 and len(mm_tokens) == 1:
        cat_t, mm_t = cat_tokens[0], mm_tokens[0]
        prefix = min(len(cat_t), len(mm_t), 5)
        if prefix >= 4 and cat_t[:prefix] == mm_t[:prefix]:
            return True

    for cat_t in cat_tokens:
        if not any(cat_t in mm_t or mm_t in cat_t for mm_t in mm_tokens):
            return False
    return True


def metadata_matches_catalog(
    catalog_title: str,
    catalog_artist: str,
    mm_title: str,
    mm_artist: str,
) -> bool:
    """Loose title/artist check for Musixmatch track.get vs catalog row."""
    cat_t = normalize_match_text(catalog_title)
    cat_a = normalize_match_text(catalog_artist)
    mm_t = normalize_match_text(mm_title)
    mm_a = normalize_match_text(mm_artist)
    if not cat_t or not cat_a or not mm_t or not mm_a:
        return True
    title_ok = cat_t in mm_t or mm_t in cat_t
    return title_ok and artists_match(catalog_artist, mm_artist)


def fetch_subtitle_body(
    client: httpx.Client,
    *,
    api_key: str,
    track_id: str | None,
    commontrack_id: str | None,
) -> str:
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
    if int(data.get("message", {}).get("header", {}).get("status_code") or 0) != 200:
        return ""
    subtitle = data.get("message", {}).get("body", {}).get("subtitle") or {}
    return str(subtitle.get("subtitle_body") or "")


def fetch_track_metadata(
    client: httpx.Client,
    *,
    api_key: str,
    track_id: str,
) -> tuple[str, str]:
    resp = client.get(
        f"{MUSIXMATCH_BASE}/track.get",
        params={"apikey": api_key, "track_id": track_id},
    )
    resp.raise_for_status()
    data = resp.json()
    track = data.get("message", {}).get("body", {}).get("track") or {}
    return str(track.get("track_name") or ""), str(track.get("artist_name") or "")


def audit_subtitle_trust(
    *,
    catalog_title: str,
    catalog_artist: str,
    jamendo_tag_set: set[str],
    subtitle_body: str,
    mm_title: str = "",
    mm_artist: str = "",
    opening_window_ms: int = 60_000,
) -> list[str]:
    """Return human-readable reasons to distrust Musixmatch subtitles."""
    reasons: list[str] = []
    if mm_title and mm_artist and not metadata_matches_catalog(
        catalog_title, catalog_artist, mm_title, mm_artist
    ):
        reasons.append("metadata_mismatch")

    lines = parse_lrc_lines(subtitle_body)
    if count_lrc_timed_lines(subtitle_body) < 2:
        return reasons

    opening = opening_lyric_text(lines, opening_window_ms)
    if opening and not (jamendo_tag_set & GOSPEL_JAMENDO_TAGS):
        worship_hit = WORSHIP_OPENING_RE.search(opening)
        if worship_hit:
            reasons.append(f"worship_opening:{worship_hit.group(0).lower()}")

    return reasons


def mark_untrusted_musixmatch(mm: dict[str, Any], reasons: list[str]) -> None:
    mm["lyrics_trusted"] = False
    mm["has_synced_subtitles"] = False
    mm["match_status"] = "subtitle_untrusted"
    mm["subtitle_audit_reasons"] = reasons


def restore_trusted_musixmatch(mm: dict[str, Any]) -> None:
    mm.pop("lyrics_trusted", None)
    mm.pop("subtitle_audit_reasons", None)
    if mm.get("match_status") == "subtitle_untrusted":
        mm["match_status"] = "matched"
    if mm.get("has_subtitles"):
        mm["has_synced_subtitles"] = True


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
