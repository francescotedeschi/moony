#!/usr/bin/env python3
"""Precompute per-track EBU R128 loudness + YouTube-style gain into catalog.json.

Requires ffmpeg with the ebur128 filter. Measures up to 90 s from t=0 (whole-track proxy).

Example:
  python scripts/enrich_catalog_loudness.py --catalog catalog/catalog.json --limit 5
  python scripts/enrich_catalog_loudness.py --force  # recompute tracks that already have loudness
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.catalog.loudness import (  # noqa: E402
    MAX_ANALYZE_SEC,
    compute_youtube_playback_gain,
    is_plausible_lufs,
)

INTEGRATED_RE = re.compile(r"^\s*I:\s*([-\d.]+)\s+LUFS", re.MULTILINE)
PEAK_RE = re.compile(r"^\s*Peak:\s*([-\d.]+)\s+dBFS", re.MULTILINE)


def audio_path_for_track(track: dict, download_dir: Path | None) -> Path | None:
    jamendo = track.get("jamendo") or {}
    local = jamendo.get("local_audio_path") or track.get("local_audio_path")
    if local:
        p = Path(str(local))
        if p.is_file():
            return p
    url = jamendo.get("audio_url") or track.get("audio_url")
    if not url or download_dir is None:
        return None
    dest = download_dir / f"{track['id']}.mp3"
    if dest.is_file():
        return dest
    try:
        import urllib.request

        urllib.request.urlretrieve(url, dest)
        return dest if dest.is_file() else None
    except Exception:
        return None


def measure_track(path: Path) -> tuple[float, float] | None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "info",
        "-t",
        str(MAX_ANALYZE_SEC),
        "-i",
        str(path),
        "-af",
        "ebur128=peak=true:dualmono=true",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    text = (proc.stderr or "") + (proc.stdout or "")
    i_match = INTEGRATED_RE.findall(text)
    p_match = PEAK_RE.findall(text)
    if not i_match or not p_match:
        return None
    integrated = float(i_match[-1])
    peak = float(p_match[-1])
    if not is_plausible_lufs(integrated):
        return None
    return integrated, peak


def has_track_loudness(track: dict) -> bool:
    loud = track.get("loudness")
    return isinstance(loud, dict) and "youtube_gain" in loud


def coerce_legacy_loudness(track: dict) -> bool:
    """Convert old per-segment list format to a single track-level object."""
    loud = track.get("loudness")
    if not isinstance(loud, list) or not loud:
        return False
    candidates = [e for e in loud if isinstance(e, dict) and "youtube_gain" in e]
    if not candidates:
        track.pop("loudness", None)
        return False
    at_zero = next(
        (c for c in candidates if c.get("start_bucket_sec") in (0, None)),
        None,
    )
    pick = at_zero or min(
        candidates,
        key=lambda c: int(c.get("start_bucket_sec", 0)),
    )
    track["loudness"] = {
        "integrated_lufs": pick["integrated_lufs"],
        "true_peak_dbfs": pick["true_peak_dbfs"],
        "youtube_gain": pick["youtube_gain"],
    }
    return True


def enrich_track(track: dict, *, download_dir: Path | None, force: bool) -> bool:
    if has_track_loudness(track) and not force:
        return False
    if isinstance(track.get("loudness"), list):
        if coerce_legacy_loudness(track) and not force:
            return True

    path = audio_path_for_track(track, download_dir)
    if path is None:
        return False

    measured = measure_track(path)
    if measured is None:
        return False
    integrated, peak = measured
    gain = compute_youtube_playback_gain(integrated, peak)
    track["loudness"] = {
        "integrated_lufs": round(integrated, 2),
        "true_peak_dbfs": round(peak, 2),
        "youtube_gain": round(gain, 4),
    }
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich catalog with per-track loudness")
    parser.add_argument("--catalog", type=Path, default=ROOT / "catalog" / "catalog.json")
    parser.add_argument("--out", type=Path, default=None, help="Write here; default overwrites --catalog")
    parser.add_argument("--limit", type=int, default=0, help="Max tracks to process (0 = all)")
    parser.add_argument("--force", action="store_true", help="Recompute even when loudness exists")
    parser.add_argument("--download", action="store_true", help="Download missing audio into a temp dir")
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=25,
        help="Rewrite catalog every N tracks updated (0 = only at end)",
    )
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg not found on PATH", file=sys.stderr)
        return 1

    catalog_path = args.catalog
    if not catalog_path.is_file():
        print(f"Catalog not found: {catalog_path}", file=sys.stderr)
        return 1

    with catalog_path.open(encoding="utf-8") as f:
        data = json.load(f)

    tracks: list[dict[str, Any]] = data.get("tracks", [])
    out_path = args.out or catalog_path
    download_dir: Path | None = None
    if args.download:
        download_dir = Path(tempfile.mkdtemp(prefix="moony-loudness-"))

    def write_catalog() -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")

    processed = 0
    updated = 0
    touched_since_save = 0
    for track in tracks:
        if args.limit and processed >= args.limit:
            break
        changed = enrich_track(track, download_dir=download_dir, force=args.force)
        if changed:
            updated += 1
            touched_since_save += 1
        if changed or has_track_loudness(track):
            processed += 1

        if args.checkpoint_every > 0 and touched_since_save >= args.checkpoint_every:
            write_catalog()
            print(f"Checkpoint: {processed} tracks, {updated} updated", flush=True)
            touched_since_save = 0

    write_catalog()
    print(f"Wrote {out_path} — tracks seen={processed}, updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
