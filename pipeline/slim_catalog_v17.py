#!/usr/bin/env python3
"""Strip legacy / unused fields from catalog V17 (player uses Cyanite mood + energy curve).

Removes MOSS mood metadata, motion blocks, and duplicate Cyanite labels from sections.
Keeps: structure, description, embedding, cyanite_mood_* / V-A, track cyanite energy curve.

Example:
  python3 pipeline/slim_catalog_v17.py
  python3 pipeline/slim_catalog_v17.py catalog/catalog_V17.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SECTION_STRIP_KEYS = frozenset(
    {
        "emotion_label",
        "valence",
        "arousal",
        "moss_mood_text",
        "moss_emotion_label",
        "moss_mood_confidence",
        "emotion_confidence",
        "emotion_source",
        "emotion_method",
        "va_source",
        "cyanite_emotion_label",
        "description_source",
        "essentia_emotion_label",
        "essentia_confidence",
        "emotion_disagreement",
        "bpm",
        "embedding_profile",
    }
)

TRACK_STRIP_KEYS = frozenset(
    {
        "primary_emotion",
        "moss_status",
        "analyzer",
        "motion",
        "mood_distribution",
        "transitions",
        "beat_grid",
        "loudness",
    }
)

HEADER_STRIP_KEYS = frozenset({
    "motion_status",
    "moss_status",
    "embedding_profile",
    "analyzer",
    "cyanite_status",
    "fetch_mode",
    "candidates_per_emotion",
    "emotion_ids",
})

JAMENDO_STRIP_KEYS = frozenset({"local_audio_path"})

FORBIDDEN_LYRICS_KEYS = frozenset(
    {"lyrics_body", "subtitle_body", "lyrics", "subtitle", "lyric", "lyrics_text"}
)


def slim_player_track(track: dict[str, Any]) -> dict[str, Any]:
    """Return one track dict with only player-facing catalog V17 fields."""
    out = dict(track)
    for key in TRACK_STRIP_KEYS:
        out.pop(key, None)

    jamendo = out.get("jamendo")
    if isinstance(jamendo, dict):
        out["jamendo"] = {k: v for k, v in jamendo.items() if k not in JAMENDO_STRIP_KEYS}

    sections_key = "sections" if "sections" in out else "segments"
    sections = out.get(sections_key) or []
    if isinstance(sections, list):
        slim_sections: list[dict[str, Any]] = []
        for section in sections:
            if not isinstance(section, dict):
                slim_sections.append(section)
                continue
            slimmed, _ = _strip_section(section)
            slim_sections.append(slimmed)
        out[sections_key] = slim_sections
    return out


def assert_no_lyrics_in_payload(payload: dict[str, Any]) -> None:
    forbidden = {k.lower() for k in FORBIDDEN_LYRICS_KEYS}

    def walk(obj: Any, path: str = "root") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if str(key).lower() in forbidden:
                    raise ValueError(f"Catalog payload must not contain lyrics field: {path}.{key}")
                walk(value, f"{path}.{key}")
        elif isinstance(obj, list):
            for index, item in enumerate(obj):
                walk(item, f"{path}[{index}]")

    walk(payload)


def _strip_section(section: dict[str, Any]) -> tuple[dict[str, Any], int]:
    removed = 0
    out = dict(section)
    for key in SECTION_STRIP_KEYS:
        if key in out:
            del out[key]
            removed += 1
    return out, removed


def slim_catalog(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    removed = 0
    out = dict(data)
    for key in HEADER_STRIP_KEYS:
        if key in out:
            del out[key]
            removed += 1

    tracks_out: list[dict[str, Any]] = []
    for raw in out.get("tracks") or []:
        if not isinstance(raw, dict):
            continue
        track = dict(raw)
        for key in TRACK_STRIP_KEYS:
            if key in track:
                del track[key]
                removed += 1

        sections_key = "sections" if "sections" in track else "segments"
        sections = track.get(sections_key) or []
        if isinstance(sections, list):
            slim_sections: list[dict[str, Any]] = []
            for section in sections:
                if not isinstance(section, dict):
                    slim_sections.append(section)
                    continue
                slimmed, n = _strip_section(section)
                slim_sections.append(slimmed)
                removed += n
            track[sections_key] = slim_sections
        tracks_out.append(track)

    out["tracks"] = tracks_out
    return out, removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove legacy unused fields from catalog V17.")
    parser.add_argument(
        "catalog",
        nargs="?",
        type=Path,
        default=ROOT / "catalog" / "catalog_V17.json",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write")
    args = parser.parse_args()

    path = args.catalog if args.catalog.is_absolute() else ROOT / args.catalog
    if not path.is_file():
        print(f"Catalog not found: {path}", file=sys.stderr)
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))
    slimmed, removed = slim_catalog(data)
    track_count = len(slimmed.get("tracks") or [])
    print(f"Stripped {removed} unused field(s) across {track_count} tracks")

    if args.dry_run:
        print(f"Dry run — no write to {path}")
        return 0

    path.write_text(json.dumps(slimmed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
