#!/usr/bin/env python3
"""Fetch vocal Jamendo tracks, pre-screen on Musixmatch, merge matches into catalog.

MOSS analysis is intentionally deferred — new tracks get ``analyzer: pending-moss``
and empty ``segments`` until you run MOSS later.

Example:
  python pipeline/expand_catalog_jamendo.py --target 200
  python pipeline/expand_catalog_jamendo.py --target 50 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from musixmatch_utils import (
    ROOT,
    catalog_jamendo_ids,
    is_instrumental_jamendo,
    jamendo_row_to_catalog_track,
    load_dotenv,
    match_track,
    sleep_between_calls,
    unescape,
)

JAMENDO_BASE = "https://api.jamendo.com/v3.0/tracks/"
DEFAULT_TAG_QUERIES = [
    "vocal+pop",
    "vocal+rock",
    "vocal+soul",
    "vocal+hiphop",
    "vocal+indie",
    "vocal+folk",
]


def fetch_jamendo_page(
    client: httpx.Client,
    *,
    client_id: str,
    tags: str,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    resp = client.get(
        JAMENDO_BASE,
        params={
            "client_id": client_id,
            "format": "json",
            "limit": limit,
            "offset": offset,
            "tags": tags,
            "order": "popularity_total_desc",
            "include": "musicinfo",
            "audioformat": "mp32",
        },
    )
    resp.raise_for_status()
    return list(resp.json().get("results") or [])


def iter_jamendo_candidates(
    client: httpx.Client,
    *,
    client_id: str,
    tag_queries: list[str],
    existing_ids: set[int],
    max_candidates: int,
    page_size: int,
) -> list[dict[str, Any]]:
    seen: set[int] = set(existing_ids)
    candidates: list[dict[str, Any]] = []

    for tags in tag_queries:
        offset = 0
        while len(candidates) < max_candidates:
            rows = fetch_jamendo_page(
                client,
                client_id=client_id,
                tags=tags,
                offset=offset,
                limit=page_size,
            )
            if not rows:
                break

            added = 0
            for row in rows:
                jamendo_id = int(row["id"])
                if jamendo_id in seen:
                    continue
                if is_instrumental_jamendo(row):
                    seen.add(jamendo_id)
                    continue
                if not row.get("audio"):
                    seen.add(jamendo_id)
                    continue
                seen.add(jamendo_id)
                candidates.append(row)
                added += 1
                if len(candidates) >= max_candidates:
                    break

            if added == 0 and len(rows) < page_size:
                break
            offset += page_size

        if len(candidates) >= max_candidates:
            break

    return candidates


def expand_catalog(
    catalog: dict[str, Any],
    *,
    client_id: str,
    api_key: str,
    tag_queries: list[str],
    target: int,
    max_candidates: int,
    page_size: int,
    delay_sec: float,
    dry_run: bool,
) -> dict[str, int]:
    stats = {
        "existing_tracks": len(catalog.get("tracks", [])),
        "candidates_fetched": 0,
        "searched": 0,
        "added": 0,
        "not_found": 0,
        "errors": 0,
    }

    existing_ids = catalog_jamendo_ids(catalog)
    with httpx.Client(timeout=20.0) as client:
        candidates = iter_jamendo_candidates(
            client,
            client_id=client_id,
            tag_queries=tag_queries,
            existing_ids=existing_ids,
            max_candidates=max_candidates,
            page_size=page_size,
        )
        stats["candidates_fetched"] = len(candidates)

        if dry_run:
            print(f"Would search up to {len(candidates)} candidates to reach target {target}")
            return stats

        for i, row in enumerate(candidates, start=1):
            if stats["added"] >= target:
                break

            title = unescape(str(row.get("name", "")))
            artist = unescape(str(row.get("artist_name", "")))
            stats["searched"] += 1
            try:
                match = match_track(
                    client,
                    api_key=api_key,
                    title=title,
                    artist=artist,
                )
                if match:
                    track = jamendo_row_to_catalog_track(row, match)
                    catalog.setdefault("tracks", []).append(track)
                    stats["added"] += 1
                    print(
                        f"[{i}/{len(candidates)}] +{stats['added']}/{target} "
                        f"{track['id']}: {title} -> mm:{match['track_id']}"
                    )
                else:
                    stats["not_found"] += 1
                    print(f"[{i}/{len(candidates)}] skip {row['id']}: {title} / {artist}")
            except Exception as exc:
                stats["errors"] += 1
                print(f"[{i}/{len(candidates)}] error {row['id']}: {exc}", file=sys.stderr)

            sleep_between_calls(delay_sec)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Expand catalog with Jamendo tracks that match on Musixmatch."
    )
    parser.add_argument(
        "catalog",
        nargs="?",
        type=Path,
        default=ROOT / "catalog" / "catalog.json",
    )
    parser.add_argument("--target", type=int, default=200, help="New matched tracks to add")
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=1200,
        help="Max Jamendo candidates to fetch/search",
    )
    parser.add_argument("--page-size", type=int, default=200, help="Jamendo page size (max 200)")
    parser.add_argument(
        "--tags",
        default=",".join(DEFAULT_TAG_QUERIES),
        help="Comma-separated Jamendo tag queries",
    )
    parser.add_argument("--delay", type=float, default=0.2, help="Seconds between Musixmatch calls")
    parser.add_argument("--dry-run", action="store_true", help="Fetch candidates only")
    args = parser.parse_args()

    load_dotenv()
    client_id = os.environ.get("JAMENDO_CLIENT_ID", "").strip()
    api_key = os.environ.get("MUSIXMATCH_API_KEY", "").strip()
    if not client_id:
        print("JAMENDO_CLIENT_ID missing in .env", file=sys.stderr)
        return 1
    if not api_key and not args.dry_run:
        print("MUSIXMATCH_API_KEY missing in .env", file=sys.stderr)
        return 1

    catalog_path = args.catalog if args.catalog.is_absolute() else ROOT / args.catalog
    catalog = json.loads(catalog_path.read_text())
    tag_queries = [q.strip() for q in args.tags.split(",") if q.strip()]

    stats = expand_catalog(
        catalog,
        client_id=client_id,
        api_key=api_key,
        tag_queries=tag_queries,
        target=args.target,
        max_candidates=args.max_candidates,
        page_size=min(args.page_size, 200),
        delay_sec=args.delay,
        dry_run=args.dry_run,
    )

    print(
        "existing={existing_tracks} candidates={candidates_fetched} searched={searched} "
        "added={added} not_found={not_found} errors={errors}".format(**stats)
    )

    if not args.dry_run and stats["added"] > 0:
        catalog["generated_at"] = datetime.now(UTC).isoformat()
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
        print(f"Wrote {catalog_path} (+{stats['added']} tracks, total {len(catalog['tracks'])})")

    if stats["added"] < args.target and not args.dry_run:
        print(
            f"Warning: added {stats['added']} < target {args.target}. "
            "Try increasing --max-candidates or adding tag queries.",
            file=sys.stderr,
        )
        return 2 if stats["added"] == 0 else 0

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
