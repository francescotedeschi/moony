#!/usr/bin/env python3
"""Match non-instrumental Jamendo catalog tracks against Musixmatch (IDs only).

Stores Musixmatch reference IDs in each track's ``musixmatch`` field — never lyrics.

Example:
  python pipeline/match_musixmatch.py
  python pipeline/match_musixmatch.py --catalog catalog/catalog.json --dry-run
  python pipeline/match_musixmatch.py --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from musixmatch_utils import (
    ROOT,
    is_instrumental_catalog_track,
    load_dotenv,
    match_track,
    musixmatch_from_match,
    pending_musixmatch_block,
    sleep_between_calls,
    unescape,
)


def enrich_catalog(
    data: dict[str, Any],
    *,
    api_key: str,
    delay_sec: float,
    limit: int | None,
    dry_run: bool,
) -> dict[str, int]:
    stats = {
        "total": 0,
        "skipped_instrumental": 0,
        "searched": 0,
        "matched": 0,
        "not_found": 0,
        "errors": 0,
    }

    targets: list[dict[str, Any]] = []
    for track in data.get("tracks", []):
        stats["total"] += 1
        mm = track.get("musixmatch") or pending_musixmatch_block()
        track["musixmatch"] = mm

        if is_instrumental_catalog_track(track):
            stats["skipped_instrumental"] += 1
            mm["match_status"] = "skipped_instrumental"
            continue

        if mm.get("track_id") and mm.get("match_status") == "matched":
            stats["matched"] += 1
            continue

        targets.append(track)

    if limit is not None:
        targets = targets[:limit]

    if dry_run:
        stats["searched"] = len(targets)
        return stats

    with httpx.Client(timeout=20.0) as client:
        for i, track in enumerate(targets, start=1):
            title = unescape(str(track.get("title", "")))
            artist = unescape(str(track.get("artist", "")))
            stats["searched"] += 1
            try:
                match = match_track(
                    client,
                    api_key=api_key,
                    title=title,
                    artist=artist,
                )
                if match:
                    track["musixmatch"] = musixmatch_from_match(match)
                    stats["matched"] += 1
                    print(
                        f"[{i}/{len(targets)}] matched {track['id']}: "
                        f"{title} -> track_id={match['track_id']}"
                    )
                else:
                    track["musixmatch"]["match_status"] = "not_found"
                    stats["not_found"] += 1
                    print(
                        f"[{i}/{len(targets)}] not found {track['id']}: "
                        f"{title} / {artist}"
                    )
            except Exception as exc:
                track["musixmatch"]["match_status"] = "error"
                stats["errors"] += 1
                print(f"[{i}/{len(targets)}] error {track['id']}: {exc}", file=sys.stderr)

            sleep_between_calls(delay_sec)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Match vocal catalog tracks to Musixmatch IDs (no lyrics stored)."
    )
    parser.add_argument(
        "catalog",
        nargs="?",
        type=Path,
        default=ROOT / "catalog" / "catalog.json",
    )
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds between API calls")
    parser.add_argument("--limit", type=int, default=None, help="Max vocal tracks to search")
    parser.add_argument("--dry-run", action="store_true", help="Count targets without API calls")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("MUSIXMATCH_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        print("MUSIXMATCH_API_KEY missing in .env", file=sys.stderr)
        return 1

    catalog_path = args.catalog if args.catalog.is_absolute() else ROOT / args.catalog
    data = json.loads(catalog_path.read_text())
    stats = enrich_catalog(
        data,
        api_key=api_key,
        delay_sec=args.delay,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print(
        f"total={stats['total']} skipped_instrumental={stats['skipped_instrumental']} "
        f"searched={stats['searched']} matched={stats['matched']} "
        f"not_found={stats['not_found']} errors={stats['errors']}"
    )

    if not args.dry_run:
        catalog_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        print(f"Wrote {catalog_path}")

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
