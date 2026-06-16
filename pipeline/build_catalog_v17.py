#!/usr/bin/env python3
"""Build catalog v1.7 — Musixmatch-matched tracks only, MOSS/motion stripped.

Keeps song metadata (Jamendo + Musixmatch IDs). Drops segments, transitions,
motion, mood_distribution, loudness so MOSS and motion can be re-run from scratch.

Example:
  python pipeline/build_catalog_v17.py
  python pipeline/build_catalog_v17.py catalog/catalog.json catalog/catalog_V17.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

STRIP_TRACK_KEYS = frozenset(
    {
        "segments",
        "transitions",
        "motion",
        "mood_distribution",
        "loudness",
        "beat_grid",
    }
)

STRIP_JAMENDO_KEYS = frozenset({"local_audio_path"})

STRIP_CATALOG_KEYS = frozenset(
    {
        "embedding_model",
        "embedding_profile",
    }
)


def has_musixmatch_match(track: dict[str, Any]) -> bool:
    mm = track.get("musixmatch") or {}
    track_id = mm.get("track_id")
    if track_id in (None, "", "null"):
        return False
    return mm.get("match_status", "matched") == "matched"


def slim_musixmatch(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "commontrack_id": str(raw["commontrack_id"])
        if raw.get("commontrack_id") not in (None, "", "null")
        else None,
        "track_id": str(raw["track_id"]),
        "has_lyrics": int(raw.get("has_lyrics") or 0),
        "has_subtitles": int(raw.get("has_subtitles") or 0),
        "match_status": "matched",
    }


def slim_jamendo(raw: dict[str, Any]) -> dict[str, Any]:
    jamendo = {k: v for k, v in raw.items() if k not in STRIP_JAMENDO_KEYS}
    return jamendo


def slim_track(raw: dict[str, Any]) -> dict[str, Any]:
    track: dict[str, Any] = {
        "id": raw["id"],
        "title": raw.get("title", ""),
        "artist": raw.get("artist", ""),
        "duration_sec": raw.get("duration_sec"),
        "bpm": raw.get("bpm"),
        "primary_emotion": raw.get("primary_emotion", "calm"),
        "jamendo": slim_jamendo(raw.get("jamendo") or {}),
        "musixmatch": slim_musixmatch(raw.get("musixmatch") or {}),
        "analyzer": "pending-moss",
        "moss_status": "pending",
    }
    return track


def build_catalog_v17(source: dict[str, Any]) -> dict[str, Any]:
    matched = [slim_track(t) for t in source.get("tracks", []) if has_musixmatch_match(t)]

    catalog: dict[str, Any] = {
        k: v for k, v in source.items() if k != "tracks" and k not in STRIP_CATALOG_KEYS
    }
    catalog.update(
        {
            "version": "1.7",
            "catalog_schema": "moodpad-catalog-musicathon",
            "catalog_name": "Jamendo (Musixmatch)",
            "generated_at": datetime.now(UTC).isoformat(),
            "source_catalog_version": source.get("version"),
            "source_track_count": len(source.get("tracks", [])),
            "analyzer": "pending-moss",
            "moss_status": "pending",
            "motion_status": "pending",
            "tracks": matched,
        }
    )
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Musixmatch-only catalog v1.7.")
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=ROOT / "catalog" / "catalog.json",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=ROOT / "catalog" / "catalog_V17.json",
    )
    args = parser.parse_args()

    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    output_path = args.output if args.output.is_absolute() else ROOT / args.output

    source = json.loads(input_path.read_text())
    catalog = build_catalog_v17(source)

    output_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
    print(
        f"Wrote {output_path}: {len(catalog['tracks'])} tracks "
        f"(from {catalog['source_track_count']} in {input_path.name})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
