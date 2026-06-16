#!/usr/bin/env python3
"""Test Musixmatch song structure for one catalog v17 track.

Downloads Jamendo preview audio and fetches timed lyrics structure from Musixmatch.
Note: section labels (verse/chorus) via track.subtitle.macro.get require Pro+ tier (403).

Example:
  python pipeline/test_musixmatch_structure.py
  python pipeline/test_musixmatch_structure.py jamendo_1719234
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from musixmatch_utils import load_dotenv, unescape  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MUSIXMATCH_BASE = "https://api.musixmatch.com/ws/1.1"
LRC_LINE = re.compile(r"\[(\d{2}):(\d{2}\.\d{2})\]\s*(.*)")
DFXP_LINE = re.compile(r'begin="([^"]+)"\s+end="([^"]+)"[^>]*>([^<]+)</p>')


def parse_lrc(body: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for i, raw in enumerate(body.strip().splitlines()):
        m = LRC_LINE.match(raw.strip())
        if not m:
            continue
        mm, ss, text = m.groups()
        t_start_ms = int(mm) * 60_000 + int(float(ss) * 1000)
        lines.append({"index": i, "t_start_ms": t_start_ms, "text": text.strip()})
    for i, line in enumerate(lines):
        if i + 1 < len(lines):
            line["t_end_ms"] = lines[i + 1]["t_start_ms"]
        else:
            line["t_end_ms"] = line["t_start_ms"] + 3000
    return lines


def parse_dfxp(body: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for i, m in enumerate(DFXP_LINE.finditer(body)):
        begin, end, text = m.groups()
        lines.append(
            {
                "index": i,
                "t_start_ms": _ttml_to_ms(begin),
                "t_end_ms": _ttml_to_ms(end),
                "text": text.strip(),
            }
        )
    return lines


def _ttml_to_ms(value: str) -> int:
    # HH:MM:SS.mmm
    hh, mm, rest = value.split(":")
    ss, ms = rest.split(".")
    return (int(hh) * 3600 + int(mm) * 60 + int(ss)) * 1000 + int(ms.ljust(3, "0")[:3])


def infer_sections(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Heuristic verse/chorus blocks from repeated lyric lines."""
    if not lines:
        return []

    blocks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_key = ""

    def flush() -> None:
        nonlocal current, current_key
        if not current:
            return
        blocks.append(
            {
                "label": _label_block(current_key),
                "t_start_ms": current[0]["t_start_ms"],
                "t_end_ms": current[-1]["t_end_ms"],
                "lines": current,
            }
        )
        current = []

    for line in lines:
        key = line["text"].casefold()
        if key == current_key:
            current.append(line)
        else:
            flush()
            current_key = key
            current = [line]
    flush()
    return blocks


def _label_block(key: str) -> str:
    if not key:
        return "unknown"
    return f"block:{key[:48]}{'…' if len(key) > 48 else ''}"


def mm_get(client: httpx.Client, api_key: str, path: str, **params: str) -> dict[str, Any]:
    resp = client.get(f"{MUSIXMATCH_BASE}/{path}", params={"apikey": api_key, **params})
    resp.raise_for_status()
    return resp.json()


def fetch_structure(
    client: httpx.Client,
    *,
    api_key: str,
    track_id: str,
    commontrack_id: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"track_id": track_id, "commontrack_id": commontrack_id}

    track_resp = mm_get(client, api_key, "track.get", track_id=track_id)
    result["track"] = track_resp.get("message", {}).get("body", {}).get("track", {})

    macro = mm_get(
        client,
        api_key,
        "track.subtitle.macro.get",
        track_id=track_id,
        commontrack_id=commontrack_id or "",
    )
    macro_code = macro.get("message", {}).get("header", {}).get("status_code")
    result["macro_status"] = macro_code
    result["macro"] = macro.get("message", {}).get("body", {})

    sub_dfxp = mm_get(
        client,
        api_key,
        "track.subtitle.get",
        track_id=track_id,
        subtitle_format="dfxp",
    )
    subtitle = sub_dfxp.get("message", {}).get("body", {}).get("subtitle", {})
    result["subtitle_meta"] = {
        k: subtitle.get(k)
        for k in (
            "subtitle_id",
            "subtitle_length",
            "subtitle_language",
            "subtitle_language_description",
        )
    }
    lines = parse_dfxp(subtitle.get("subtitle_body", ""))
    result["lines"] = lines
    result["inferred_sections"] = infer_sections(lines)
    return result


def download_audio(client: httpx.Client, url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url, follow_redirects=True) as resp:
        resp.raise_for_status()
        dest.write_bytes(resp.read())
    return dest


def pick_track(catalog: dict[str, Any], track_id: str | None) -> dict[str, Any]:
    tracks = catalog.get("tracks", [])
    if track_id:
        for t in tracks:
            if t["id"] == track_id:
                return t
        raise SystemExit(f"Track {track_id} not found in catalog")
    for t in tracks:
        mm = t.get("musixmatch") or {}
        if mm.get("has_subtitles") and mm.get("track_id"):
            return t
    raise SystemExit("No track with Musixmatch subtitles found")


def print_structure(track: dict[str, Any], structure: dict[str, Any]) -> None:
    mm = track["musixmatch"]
    print("=" * 72)
    print(f"Track: {track['title']} — {track['artist']}")
    print(f"Catalog id: {track['id']}  |  Musixmatch track_id: {mm['track_id']}")
    print(f"Duration: {track.get('duration_sec')}s  |  Subtitle lines: {len(structure['lines'])}")
    print(f"Macro API status: {structure['macro_status']} (403 = Pro tier required for section labels)")
    print("=" * 72)
    print("\nTimed lyrics structure (DFXP → lines):\n")
    for line in structure["lines"][:20]:
        print(f"  [{line['t_start_ms']/1000:6.2f}s → {line['t_end_ms']/1000:6.2f}s]  {line['text']}")
    if len(structure["lines"]) > 20:
        print(f"  ... +{len(structure['lines']) - 20} more lines")
    print("\nInferred repeating blocks (heuristic):\n")
    for i, block in enumerate(structure["inferred_sections"][:12], start=1):
        print(
            f"  [{i}] {block['t_start_ms']/1000:.1f}s–{block['t_end_ms']/1000:.1f}s  "
            f"({len(block['lines'])} lines)  {block['label']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Musixmatch structure for one v17 track.")
    parser.add_argument("track_id", nargs="?", default="jamendo_1719234", help="Catalog track id")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "catalog" / "catalog_V17.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "pipeline" / "data" / "tmp",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("MUSIXMATCH_API_KEY", "").strip()
    if not api_key:
        print("MUSIXMATCH_API_KEY missing in .env", file=sys.stderr)
        return 1

    catalog_path = args.catalog if args.catalog.is_absolute() else ROOT / args.catalog
    catalog = json.loads(catalog_path.read_text())
    track = pick_track(catalog, args.track_id)
    mm = track["musixmatch"]
    audio_url = (track.get("jamendo") or {}).get("audio_url") or track.get("audio_url")
    if not audio_url:
        print("No audio_url on track", file=sys.stderr)
        return 1

    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    audio_path = out_dir / f"{track['id']}.mp3"
    json_path = out_dir / f"{track['id']}_musixmatch_structure.json"

    with httpx.Client(timeout=60.0) as client:
        print(f"Downloading audio → {audio_path}")
        download_audio(client, audio_url, audio_path)
        print(f"Audio saved ({audio_path.stat().st_size // 1024} KB)")

        structure = fetch_structure(
            client,
            api_key=api_key,
            track_id=str(mm["track_id"]),
            commontrack_id=str(mm.get("commontrack_id") or ""),
        )

    payload = {
        "catalog_track": {
            "id": track["id"],
            "title": track["title"],
            "artist": track["artist"],
            "duration_sec": track.get("duration_sec"),
            "audio_path": str(audio_path),
        },
        "musixmatch": structure,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Structure JSON → {json_path}\n")
    print_structure(track, structure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
