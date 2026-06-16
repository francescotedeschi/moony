#!/usr/bin/env python3
"""Check catalog tracks: segment count, gaps, and end coverage vs duration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "catalog" / "catalog.json"

GAP_MS = 500  # ignore sub-500ms holes
TAIL_TOLERANCE_MS = 2000
HEAD_TOLERANCE_MS = 500


def track_duration_ms(track: dict, segments: list[dict]) -> int:
    dur_sec = float(track.get("duration_sec") or 0)
    if dur_sec > 0:
        return int(dur_sec * 1000)
    if segments:
        return max(int(s.get("t_end", 0)) for s in segments)
    return 0


def seg_bounds(raw: dict) -> tuple[int, int]:
    t_start = int(float(raw.get("t_start", raw.get("start_sec", 0) * 1000)))
    t_end = int(float(raw.get("t_end", raw.get("end_sec", 0) * 1000)))
    return t_start, t_end


def analyze_track(track: dict) -> dict:
    raw_segs = track.get("segments") or []
    segs = sorted(
        raw_segs,
        key=lambda s: float(s.get("end_sec", s.get("t_end", 0) / 1000.0)),
    )
    dur_ms = track_duration_ms(track, segs)
    issues: list[str] = []

    if not segs:
        issues.append("no_segments")
        return {"id": track.get("id"), "n": 0, "dur_ms": dur_ms, "issues": issues}

    parsed = [seg_bounds(s) for s in segs]
    n = len(parsed)

    if parsed[0][0] > HEAD_TOLERANCE_MS:
        issues.append(f"late_start:{parsed[0][0]}ms")

    for i in range(1, n):
        prev_end = parsed[i - 1][1]
        cur_start = parsed[i][0]
        if cur_start > prev_end + GAP_MS:
            issues.append(f"gap:{prev_end}-{cur_start}ms")
        if cur_start < prev_end - 1:
            issues.append(f"overlap:{cur_start}-{prev_end}ms")

    last_end = parsed[-1][1]
    if dur_ms > 0 and last_end < dur_ms - TAIL_TOLERANCE_MS:
        issues.append(f"short_tail:{last_end}<{dur_ms}ms")
    if dur_ms > 0 and last_end > dur_ms + TAIL_TOLERANCE_MS:
        issues.append(f"tail_past_duration:{last_end}>{dur_ms}ms")

    span_ms = last_end - parsed[0][0] if n else 0
    cover = (span_ms / dur_ms) if dur_ms > 0 else 0.0
    moss_ms = last_end
    moss_cover = (moss_ms / span_ms) if span_ms > 0 else 1.0
    internal_issues = [i for i in issues if not i.startswith("short_tail")]
    if n > 0 and moss_ms > 0 and moss_cover >= 0.98 and not internal_issues:
        moss_ok = True
    else:
        moss_ok = n > 0 and not internal_issues and parsed[0][0] <= HEAD_TOLERANCE_MS

    return {
        "id": track.get("id"),
        "title": (track.get("title") or "")[:40],
        "n": n,
        "dur_ms": dur_ms,
        "dur_sec": round(dur_ms / 1000, 1),
        "moss_sec": round(moss_ms / 1000, 1),
        "last_end_sec": round(last_end / 1000, 1),
        "cover": round(cover, 3),
        "moss_ok": moss_ok,
        "issues": issues,
    }


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else CATALOG
    data = json.loads(path.read_text(encoding="utf-8"))
    tracks = data.get("tracks") or []

    rows = [analyze_track(t) for t in tracks]
    with_issues = [r for r in rows if r["issues"]]
    few_segs = [r for r in rows if r["n"] > 0 and r["n"] < 4]
    low_cover = [r for r in rows if r.get("cover", 1) < 0.85 and r["n"] > 0]
    moss_short = [
        r
        for r in rows
        if r["n"] > 0 and r["dur_ms"] > 0 and r.get("moss_sec", 0) < r["dur_sec"] * 0.5
    ]
    moss_internal_bad = [r for r in rows if r["n"] > 0 and not r.get("moss_ok")]
    critical = [
        r
        for r in rows
        if r["n"] > 0
        and (r["n"] < 4 or not r.get("moss_ok") or (r["n"] <= 2 and r.get("moss_sec", 0) < 30))
    ]

    print(f"Catalog: {path}")
    print(f"Tracks: {len(rows)}")
    print(f"With issues: {len(with_issues)}")
    print(f"MOSS timeline contiguous (0 → last segment): {sum(1 for r in rows if r.get('moss_ok'))}")
    print(f"MOSS internal problems (gaps/overlap/late start): {len(moss_internal_bad)}")
    print(f"Critical (few segments or broken MOSS span): {len(critical)}")
    print(f"Few segments (<4): {len(few_segs)}")
    print(f"Coverage <85% (MOSS span vs Jamendo duration): {len(low_cover)}")
    print(f"MOSS ends before 50% of Jamendo duration: {len(moss_short)}")
    print("(short_tail vs Jamendo is expected when MOSS only labels part of the track)")
    print()

    by_issue: dict[str, int] = {}
    for r in with_issues:
        for iss in r["issues"]:
            key = iss.split(":")[0]
            by_issue[key] = by_issue.get(key, 0) + 1
    if by_issue:
        print("Issue types:")
        for k, v in sorted(by_issue.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")
        print()

    print("Worst coverage (sample 15):")
    for r in sorted(low_cover, key=lambda x: x["cover"])[:15]:
        print(
            f"  {r['id']} n={r['n']} cover={r['cover']} "
            f"dur={r['dur_sec']}s last_end={r['last_end_sec']}s {r['issues']}"
        )
    print()

    print("Most segments (top 5):")
    for r in sorted(rows, key=lambda x: -x["n"])[:5]:
        print(f"  {r['id']} n={r['n']} dur={r['dur_sec']}s")
    print()

    print("Fewest segments (sample 15):")
    for r in sorted([x for x in rows if x["n"] > 0], key=lambda x: x["n"])[:15]:
        print(
            f"  {r['id']} n={r['n']} moss={r.get('moss_sec')}s "
            f"jamendo={r['dur_sec']}s {r['issues']}"
        )
    print()

    print("Critical MOSS (sample 15):")
    for r in sorted(critical, key=lambda x: (x["n"], x.get("moss_sec", 0)))[:15]:
        print(
            f"  {r['id']} n={r['n']} moss={r.get('moss_sec')}s "
            f"jamendo={r['dur_sec']}s moss_ok={r.get('moss_ok')} {r['issues']}"
        )

    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
