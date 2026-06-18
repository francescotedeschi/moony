#!/usr/bin/env python3
"""Audit Musixmatch subtitles against catalog tracks.

Flags rows where timed LRC lyrics are likely the wrong song — e.g. worship
lyrics on non-gospel pop tracks, or Musixmatch metadata that no longer matches
the catalog title/artist.

Example:
  python pipeline/audit_musixmatch_lyrics.py
  python pipeline/audit_musixmatch_lyrics.py --apply
  python pipeline/audit_musixmatch_lyrics.py --report catalog/lyrics_audit.json
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
    audit_subtitle_trust,
    fetch_subtitle_body,
    fetch_track_metadata,
    jamendo_tags,
    load_dotenv,
    mark_untrusted_musixmatch,
    opening_lyric_text,
    parse_lrc_lines,
    restore_trusted_musixmatch,
    sleep_between_calls,
    unescape,
)


def audit_catalog(
    data: dict[str, Any],
    *,
    api_key: str,
    delay_sec: float,
    limit: int | None,
    only_synced: bool,
    recheck_untrusted: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "total": 0,
        "skipped_no_ref": 0,
        "skipped_no_subtitles": 0,
        "checked": 0,
        "flagged": 0,
        "already_untrusted": 0,
        "errors": 0,
    }
    findings: list[dict[str, Any]] = []

    targets: list[dict[str, Any]] = []
    for track in data.get("tracks", []):
        stats["total"] += 1
        mm = track.get("musixmatch") or {}
        if not mm.get("track_id") and not mm.get("commontrack_id"):
            stats["skipped_no_ref"] += 1
            continue
        if only_synced and not mm.get("has_synced_subtitles"):
            stats["skipped_no_subtitles"] += 1
            continue
        if not mm.get("has_subtitles") and not mm.get("has_synced_subtitles"):
            stats["skipped_no_subtitles"] += 1
            continue
        if mm.get("lyrics_trusted") is False and not recheck_untrusted:
            stats["already_untrusted"] += 1
            continue
        targets.append(track)

    if limit is not None:
        targets = targets[:limit]

    with httpx.Client(timeout=20.0) as client:
        for i, track in enumerate(targets, start=1):
            stats["checked"] += 1
            mm = track["musixmatch"]
            title = unescape(str(track.get("title", "")))
            artist = unescape(str(track.get("artist", "")))
            tid = str(mm.get("track_id") or "")
            cid = str(mm.get("commontrack_id") or "")
            try:
                subtitle_body = fetch_subtitle_body(
                    client,
                    api_key=api_key,
                    track_id=tid or None,
                    commontrack_id=cid or None,
                )
                mm_title, mm_artist = fetch_track_metadata(
                    client, api_key=api_key, track_id=tid
                ) if tid else ("", "")
                reasons = audit_subtitle_trust(
                    catalog_title=title,
                    catalog_artist=artist,
                    jamendo_tag_set=jamendo_tags(track),
                    subtitle_body=subtitle_body,
                    mm_title=mm_title,
                    mm_artist=mm_artist,
                )
                if reasons:
                    stats["flagged"] += 1
                    opening = opening_lyric_text(parse_lrc_lines(subtitle_body))
                    row = {
                        "track_id": track["id"],
                        "title": title,
                        "artist": artist,
                        "musixmatch_track_id": tid,
                        "reasons": reasons,
                        "opening_60s": opening[:160],
                        "mm_title": mm_title,
                        "mm_artist": mm_artist,
                    }
                    findings.append(row)
                    print(
                        f"[{i}/{len(targets)}] FLAG {track['id']}: "
                        f"{title} — {', '.join(reasons)}"
                    )
                else:
                    print(f"[{i}/{len(targets)}] ok {track['id']}: {title}")
            except Exception as exc:
                stats["errors"] += 1
                print(f"[{i}/{len(targets)}] error {track['id']}: {exc}", file=sys.stderr)

            sleep_between_calls(delay_sec)

    return findings, stats


def apply_findings(data: dict[str, Any], findings: list[dict[str, Any]]) -> int:
    by_id = {track["id"]: track for track in data.get("tracks", [])}
    applied = 0
    for row in findings:
        track = by_id.get(row["track_id"])
        if not track:
            continue
        mm = track.setdefault("musixmatch", {})
        mark_untrusted_musixmatch(mm, row["reasons"])
        applied += 1
    return applied


def clear_trust_flags(data: dict[str, Any]) -> int:
    cleared = 0
    for track in data.get("tracks", []):
        mm = track.get("musixmatch")
        if not mm or mm.get("lyrics_trusted") is not False:
            continue
        restore_trusted_musixmatch(mm)
        cleared += 1
    return cleared


def reconcile_untrusted(
    data: dict[str, Any],
    *,
    api_key: str,
    delay_sec: float,
) -> list[str]:
    """Re-audit untrusted rows; restore those that now pass."""
    restored: list[str] = []
    targets = [
        track
        for track in data.get("tracks", [])
        if (track.get("musixmatch") or {}).get("lyrics_trusted") is False
    ]
    with httpx.Client(timeout=30.0) as client:
        for i, track in enumerate(targets, start=1):
            mm = track.get("musixmatch") or {}
            track_id = str(mm.get("track_id") or "")
            if not track_id:
                continue
            try:
                subtitle_body = fetch_subtitle_body(
                    client,
                    api_key=api_key,
                    track_id=track_id,
                    commontrack_id=str(mm.get("commontrack_id") or ""),
                )
                mm_title, mm_artist = fetch_track_metadata(
                    client, api_key=api_key, track_id=track_id
                )
                reasons = audit_subtitle_trust(
                    catalog_title=str(track.get("title") or ""),
                    catalog_artist=str(track.get("artist") or ""),
                    jamendo_tag_set=jamendo_tags(track),
                    subtitle_body=subtitle_body,
                    mm_title=mm_title,
                    mm_artist=mm_artist,
                )
                if not reasons:
                    restore_trusted_musixmatch(mm)
                    restored.append(track["id"])
                    print(f"[{i}/{len(targets)}] RESTORE {track['id']}: {track.get('title')}")
                else:
                    print(f"[{i}/{len(targets)}] keep  {track['id']}: {', '.join(reasons)}")
            except Exception as exc:
                print(f"[{i}/{len(targets)}] error {track['id']}: {exc}", file=sys.stderr)
            sleep_between_calls(delay_sec)
    return restored


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Musixmatch subtitle trust.")
    parser.add_argument(
        "catalog",
        nargs="?",
        default="catalog/catalog_V17.json",
        help="Catalog JSON path",
    )
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds between API calls")
    parser.add_argument("--limit", type=int, default=None, help="Only audit first N tracks")
    parser.add_argument(
        "--only-synced",
        action="store_true",
        help="Audit only tracks with has_synced_subtitles=true",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write lyrics_trusted=false on flagged tracks",
    )
    parser.add_argument(
        "--recheck-untrusted",
        action="store_true",
        help="Include tracks already marked lyrics_trusted=false",
    )
    parser.add_argument(
        "--reset-untrusted",
        action="store_true",
        help="Clear previous lyrics_trusted flags before auditing",
    )
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="Re-audit untrusted rows and restore false positives",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write JSON report of flagged tracks",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Catalog output path when --apply (default: overwrite input)",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("MUSIXMATCH_API_KEY", "").strip()
    if not api_key:
        print("MUSIXMATCH_API_KEY missing in .env", file=sys.stderr)
        return 1

    catalog_path = Path(args.catalog)
    if not catalog_path.is_absolute():
        catalog_path = ROOT / catalog_path
    if not catalog_path.is_file():
        print(f"Catalog not found: {catalog_path}", file=sys.stderr)
        return 1

    data = json.loads(catalog_path.read_text())
    if args.reconcile:
        restored = reconcile_untrusted(data, api_key=api_key, delay_sec=args.delay)
        out_path = args.out or catalog_path
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"\nRestored {len(restored)} tracks → {out_path}")
        return 0

    if args.reset_untrusted:
        cleared = clear_trust_flags(data)
        print(f"Reset {cleared} previous untrusted flags")
    findings, stats = audit_catalog(
        data,
        api_key=api_key,
        delay_sec=args.delay,
        limit=args.limit,
        only_synced=args.only_synced,
        recheck_untrusted=args.recheck_untrusted or args.reset_untrusted,
    )

    if args.report:
        report_path = args.report if args.report.is_absolute() else ROOT / args.report
        report_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2))
        print(f"\nReport: {report_path}")

    if args.apply and findings:
        applied = apply_findings(data, findings)
        out_path = args.out or catalog_path
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"\nApplied {applied} untrusted flags → {out_path}")

    print("\nStats:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
