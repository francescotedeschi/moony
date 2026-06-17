#!/usr/bin/env python3
"""Verify Musixmatch timed subtitles for every catalog track via live API.

Sets ``musixmatch.has_synced_subtitles`` to true only when ``track.subtitle.get``
returns LRC lines with timestamps.

Example:
  python pipeline/verify_musixmatch_subtitles.py
  python pipeline/verify_musixmatch_subtitles.py --limit 10 --dry-run
  python pipeline/verify_musixmatch_subtitles.py --force
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

from musixmatch_utils import (  # noqa: E402
    ROOT,
    fetch_has_synced_subtitles,
    load_dotenv,
    pending_musixmatch_block,
    sleep_between_calls,
    unescape,
)


def ensure_musixmatch_block(track: dict[str, Any]) -> dict[str, Any]:
    mm = track.get("musixmatch")
    if not mm:
        mm = pending_musixmatch_block()
        track["musixmatch"] = mm
    return mm


def needs_verification(mm: dict[str, Any], *, force: bool) -> bool:
    if force:
        return True
    return "has_synced_subtitles" not in mm


def verify_catalog(
    data: dict[str, Any],
    *,
    api_key: str,
    delay_sec: float,
    limit: int | None,
    dry_run: bool,
    force: bool,
) -> dict[str, int]:
    stats = {
        "total": 0,
        "no_musixmatch_ref": 0,
        "already_verified": 0,
        "checked": 0,
        "synced_true": 0,
        "synced_false": 0,
        "errors": 0,
    }

    targets: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for track in data.get("tracks", []):
        stats["total"] += 1
        mm = ensure_musixmatch_block(track)
        track_id = mm.get("track_id")
        commontrack_id = mm.get("commontrack_id")
        if not track_id and not commontrack_id:
            mm["has_synced_subtitles"] = False
            stats["no_musixmatch_ref"] += 1
            continue

        if not needs_verification(mm, force=force):
            stats["already_verified"] += 1
            if mm.get("has_synced_subtitles"):
                stats["synced_true"] += 1
            else:
                stats["synced_false"] += 1
            continue

        targets.append((track, mm))

    if limit is not None:
        targets = targets[:limit]

    if dry_run:
        stats["checked"] = len(targets)
        return stats

    with httpx.Client(timeout=20.0) as client:
        for i, (track, mm) in enumerate(targets, start=1):
            stats["checked"] += 1
            title = unescape(str(track.get("title", "")))
            try:
                tid = mm.get("track_id")
                cid = mm.get("commontrack_id")
                has_synced, line_count = fetch_has_synced_subtitles(
                    client,
                    api_key=api_key,
                    track_id=str(tid) if tid else None,
                    commontrack_id=str(cid) if cid else None,
                )
                mm["has_synced_subtitles"] = has_synced
                if has_synced:
                    stats["synced_true"] += 1
                else:
                    stats["synced_false"] += 1
                print(
                    f"[{i}/{len(targets)}] {track['id']}: "
                    f"{'synced' if has_synced else 'no-sync'} "
                    f"({line_count} timed lines) — {title}"
                )
            except Exception as exc:
                stats["errors"] += 1
                mm["has_synced_subtitles"] = False
                print(
                    f"[{i}/{len(targets)}] error {track['id']}: {exc}",
                    file=sys.stderr,
                )

            sleep_between_calls(delay_sec)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Musixmatch timed subtitles for catalog tracks."
    )
    parser.add_argument(
        "catalog",
        nargs="?",
        default="catalog/catalog_V17.json",
        help="Catalog JSON path",
    )
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds between API calls")
    parser.add_argument("--limit", type=int, default=None, help="Only verify first N pending tracks")
    parser.add_argument("--dry-run", action="store_true", help="Count pending checks without API calls")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-verify tracks even if has_synced_subtitles is already set",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: overwrite input catalog)",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("MUSIXMATCH_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        print("MUSIXMATCH_API_KEY missing in .env", file=sys.stderr)
        return 1

    catalog_path = Path(args.catalog)
    if not catalog_path.is_absolute():
        catalog_path = ROOT / catalog_path
    if not catalog_path.is_file():
        print(f"Catalog not found: {catalog_path}", file=sys.stderr)
        return 1

    data = json.loads(catalog_path.read_text())
    stats = verify_catalog(
        data,
        api_key=api_key,
        delay_sec=args.delay,
        limit=args.limit,
        dry_run=args.dry_run,
        force=args.force,
    )

    out_path = args.out or catalog_path
    if not args.dry_run:
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"\nWrote {out_path}")

    print("\nStats:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
