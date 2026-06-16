#!/usr/bin/env python3
"""Add ``embedding_profile`` + per-section ``bpm``; optionally re-embed to 386-dim vectors.

v1.7 MOSS exports often ship 384-dim text-only embeddings. v1.6 uses profile
``structure+bpm+description`` with L2-normalized concat(text, bpm_norm, mood_confidence).

Example:
  python pipeline/enrich_embedding_profile.py catalog/catalog_V17.json
  python pipeline/enrich_embedding_profile.py catalog/catalog_V17.json --reembed
  python pipeline/enrich_embedding_profile.py catalog/catalog.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.catalog.embedding_profile import (  # noqa: E402
    EMBEDDING_PROFILE,
    enrich_catalog_embedding_profile,
    resolve_track_bpm,
    section_description,
    section_mood_confidence,
)
from app.catalog.normalize import _estimate_bpm  # noqa: E402
from app.catalog.sections import raw_section_label, raw_track_sections  # noqa: E402

CATALOG_SRC = Path.home() / "Projects" / "moodpad-catalog" / "src"
if CATALOG_SRC.is_dir():
    sys.path.insert(0, str(CATALOG_SRC))


def _embedding_model_id(catalog: dict[str, Any]) -> str:
    raw = str(catalog.get("embedding_model") or "sentence-transformers/all-MiniLM-L6-v2")
    if raw.startswith("sentence-transformers/"):
        return raw.split("/", 1)[1]
    return raw


def reembed_sections(
    data: dict[str, Any],
    *,
    batch_size: int = 128,
    force: bool = False,
) -> tuple[int, int]:
    """Recompute section embeddings with structure+bpm+description profile."""
    try:
        from moodpad_catalog.embeddings import (  # type: ignore[import-not-found]
            build_segment_embedding,
            embedding_dim_for_model,
        )
    except ImportError as exc:
        raise SystemExit(
            "Re-embed requires moodpad-catalog on PYTHONPATH "
            f"(expected {CATALOG_SRC}). Metadata-only enrich omits --reembed."
        ) from exc

    model = _embedding_model_id(data)
    expected_dim = embedding_dim_for_model(model)
    rows: list[tuple[dict[str, Any], dict[str, Any], int]] = []

    for track in data.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        track_bpm = resolve_track_bpm(track, estimate_bpm=_estimate_bpm)
        for section in raw_track_sections(track):
            if not isinstance(section, dict):
                continue
            emb = section.get("embedding")
            if (
                not force
                and isinstance(emb, list)
                and len(emb) == expected_dim
                and section.get("embedding_profile") == EMBEDDING_PROFILE
                and section.get("bpm") == track_bpm
            ):
                continue
            rows.append((track, section, track_bpm))

    if not rows:
        return 0, expected_dim

    updated = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        for _track, section, track_bpm in batch:
            embedding, model_id = build_segment_embedding(
                emotion_label=str(
                    section.get("emotion_label") or section.get("moss_emotion_label") or "neutral"
                ),
                structure_label=raw_section_label(section, fallback="section"),
                description=section_description(section),
                bpm=track_bpm,
                mood_confidence=section_mood_confidence(section),
                model=model,
                include_mood=False,
            )
            section["embedding"] = embedding
            section["embedding_model"] = (
                f"sentence-transformers/{model_id}"
                if not str(model_id).startswith("sentence-transformers/")
                else str(model_id)
            )
            section["embedding_profile"] = EMBEDDING_PROFILE
            section["bpm"] = track_bpm
            updated += 1

    return updated, expected_dim


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich catalog sections with embedding_profile + bpm (optional re-embed)."
    )
    parser.add_argument(
        "catalog",
        nargs="?",
        type=Path,
        default=ROOT / "catalog" / "catalog_V17.json",
    )
    parser.add_argument(
        "--reembed",
        action="store_true",
        help="Recompute embeddings with structure+bpm+description (386-dim MiniLM)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --reembed, rebuild even when dim/profile already match",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Batch size for --reembed (default: 128)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing the catalog file",
    )
    args = parser.parse_args()

    path = args.catalog if args.catalog.is_absolute() else ROOT / args.catalog
    if not path.is_file():
        print(f"Catalog not found: {path}", file=sys.stderr)
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))
    tracks_updated, sections_updated = enrich_catalog_embedding_profile(
        data,
        estimate_bpm=_estimate_bpm,
    )
    print(
        f"Metadata: embedding_profile={EMBEDDING_PROFILE!r} on catalog; "
        f"updated {sections_updated} section(s) across {tracks_updated} track(s)"
    )

    reembedded = 0
    expected_dim = 0
    if args.reembed:
        reembedded, expected_dim = reembed_sections(
            data,
            batch_size=max(1, args.batch_size),
            force=args.force,
        )
        print(f"Re-embedded {reembedded} section(s) → dim={expected_dim}")

    if args.dry_run:
        print(f"Dry run — no write to {path}")
        return 0

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
