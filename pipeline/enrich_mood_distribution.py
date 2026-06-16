#!/usr/bin/env python3
"""Compute and persist mood_distribution on every track in catalog.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.catalog.mood_distribution import MOOD_DISTRIBUTION_LABELS  # noqa: E402
from app.catalog.normalize import normalize_catalog  # noqa: E402


def _default_catalog_path() -> Path:
    return ROOT / "catalog" / "catalog.json"


def enrich_mood_distribution(data: dict) -> tuple[dict, int]:
    """Return catalog dict with mood_distribution on each track; count of updates."""
    catalog = normalize_catalog(data)
    dist_by_id = {track.id: track.mood_distribution for track in catalog.tracks}

    updated = 0
    for raw in data.get("tracks", []):
        tid = str(raw.get("id", ""))
        if tid not in dist_by_id:
            continue
        raw["mood_distribution"] = [
            round(x, 6) for x in dist_by_id[tid]
        ]
        updated += 1

    return data, updated


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Precompute mood_distribution [calm, joy, energy, tension, sad] "
            "for every track and write it into the catalog JSON."
        )
    )
    parser.add_argument(
        "catalog",
        nargs="?",
        type=Path,
        default=_default_catalog_path(),
        help="Path to catalog.json (default: catalog/catalog.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute distributions without writing the file",
    )
    args = parser.parse_args()

    path: Path = args.catalog
    if not path.is_file():
        print(f"Catalog not found: {path}", file=sys.stderr)
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))
    enriched, updated = enrich_mood_distribution(data)
    track_count = len(data.get("tracks", []))

    if updated != track_count:
        print(
            f"Warning: updated {updated}/{track_count} tracks "
            f"(some ids missing after normalize)",
            file=sys.stderr,
        )

    if args.dry_run:
        print(f"Dry run — would update {updated} tracks in {path}")
        print(f"Axis order: {', '.join(MOOD_DISTRIBUTION_LABELS)}")
        return 0

    path.write_text(
        json.dumps(enriched, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote mood_distribution for {updated} tracks → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
