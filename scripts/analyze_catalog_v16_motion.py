#!/usr/bin/env python3
"""Full motion timeline analysis for catalog v1.6."""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "catalog_V16.json"
OUT_DIR = ROOT / "catalog" / "analysis_v16"

PAD_VA = {
    "calm": (0.0, -0.8),
    "joy": (0.8, 0.6),
    "energy": (0.2, 0.9),
    "tension": (-0.5, 0.7),
    "sad": (-0.7, -0.5),
    "neutral": (0.0, 0.0),
}

PAD_SEARCH = {
    "calm": (-0.05, -0.51),
    "joy": (0.79, 0.61),
    "energy": (0.21, 0.93),
    "tension": (-0.50, 0.71),
    "sad": (-0.70, -0.51),
}


def load_catalog(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def nearest_pad(v: float, ar: float, table: dict[str, tuple[float, float]]) -> str:
    best, best_d = "neutral", 1e9
    for name, (pv, pa) in table.items():
        d = (v - pv) ** 2 + (ar - pa) ** 2
        if d < best_d:
            best_d, best = d, name
    return best


def analyze(path: Path) -> dict:
    data = load_catalog(path)
    tracks = data.get("tracks", [])

    n_tracks = len(tracks)
    n_with_motion = 0
    hop_secs: list[float] = []
    frame_counts: list[int] = []

    all_v: list[float] = []
    all_a: list[float] = []
    pad_at_frame = Counter()
    pad_search_at_frame = Counter()

    seg_label_vs_motion_pad = Counter()  # (emotion_label, nearest_pad_at_entry)
    seg_label_agree = 0
    seg_total = 0

    cross_mood_jumps: list[tuple[float, float]] = []  # (dv, dar) when emotion changes
    same_mood_jumps: list[tuple[float, float]] = []
    cross_pairs = Counter()

    track_va_span_v: list[float] = []
    track_va_span_a: list[float] = []

    motion_vs_segment_va_dist: list[float] = []

    duration_mismatch: list[float] = []

    for track in tracks:
        motion = track.get("motion")
        if not motion or not motion.get("valence_smooth"):
            continue
        n_with_motion += 1

        hop = float(motion.get("hop_sec", 1.0))
        hop_secs.append(hop)
        vs = motion["valence_smooth"]
        ars = motion["arousal_smooth"]
        n = len(vs)
        frame_counts.append(n)
        all_v.extend(vs)
        all_a.extend(ars)

        track_va_span_v.append(max(vs) - min(vs))
        track_va_span_a.append(max(ars) - min(ars))

        dur = float(track.get("duration_sec") or 0)
        motion_dur = n * hop
        if dur > 0:
            duration_mismatch.append(abs(motion_dur - dur) / dur)

        for v, a in zip(vs, ars, strict=True):
            pad_at_frame[nearest_pad(v, a, PAD_VA)] += 1
            pad_search_at_frame[nearest_pad(v, a, PAD_SEARCH)] += 1

        segments = sorted(track.get("segments") or [], key=lambda s: s["start_sec"])
        for i, seg in enumerate(segments):
            el = (seg.get("emotion_label") or "neutral").lower()
            t_entry = float(seg.get("start_sec", 0))
            idx = int(round(t_entry / hop)) if hop > 0 else 0
            idx = max(0, min(idx, n - 1))
            mv, ma = vs[idx], ars[idx]
            pad_m = nearest_pad(mv, ma, PAD_VA)
            seg_label_vs_motion_pad[(el, pad_m)] += 1
            seg_total += 1
            if el == pad_m:
                seg_label_agree += 1

            sv, sa = float(seg.get("valence", 0)), float(seg.get("arousal", 0))
            motion_vs_segment_va_dist.append(math.hypot(mv - sv, ma - sa))

            if i + 1 < len(segments):
                nxt = segments[i + 1]
                el2 = (nxt.get("emotion_label") or "neutral").lower()
                t2 = float(nxt.get("start_sec", 0))
                idx2 = max(0, min(int(round(t2 / hop)), n - 1))
                dv = vs[idx2] - mv
                da = ars[idx2] - ma
                if el != el2:
                    cross_mood_jumps.append((dv, da))
                    cross_pairs[(el, el2)] += 1
                else:
                    same_mood_jumps.append((dv, da))

    def stats(arr: list[float]) -> dict:
        if not arr:
            return {}
        a = np.asarray(arr, dtype=np.float64)
        return {
            "mean": round(float(a.mean()), 4),
            "std": round(float(a.std()), 4),
            "p05": round(float(np.percentile(a, 5)), 4),
            "p50": round(float(np.percentile(a, 50)), 4),
            "p95": round(float(np.percentile(a, 95)), 4),
            "min": round(float(a.min()), 4),
            "max": round(float(a.max()), 4),
        }

    def jump_stats(jumps: list[tuple[float, float]]) -> dict:
        if not jumps:
            return {}
        dvs = [j[0] for j in jumps]
        das = [j[1] for j in jumps]
        mags = [math.hypot(x, y) for x, y in jumps]
        return {
            "count": len(jumps),
            "dv": stats(dvs),
            "dar": stats(das),
            "magnitude": stats(mags),
        }

    # Reachability: % frames within radius of each pad search target
    reach_radius = 0.35
    reach = {}
    for name, (tv, ta) in PAD_SEARCH.items():
        cnt = sum(
            1 for v, a in zip(all_v, all_a, strict=True) if math.hypot(v - tv, a - ta) <= reach_radius
        )
        reach[name] = round(100 * cnt / max(len(all_v), 1), 2)

    # Top cross-mood transitions
    top_cross = cross_pairs.most_common(15)

    # Label vs motion disagreement matrix (compact)
    disagree = []
    for (el, pad_m), c in seg_label_vs_motion_pad.items():
        if el != pad_m:
            disagree.append({"segment_label": el, "motion_pad": pad_m, "count": c})
    disagree.sort(key=lambda x: -x["count"])

    agree_pct = round(100 * seg_label_agree / max(seg_total, 1), 2)

    return {
        "catalog": str(path),
        "version": data.get("version"),
        "n_tracks": n_tracks,
        "n_with_motion": n_with_motion,
        "motion_coverage_pct": round(100 * n_with_motion / max(n_tracks, 1), 2),
        "total_frames": len(all_v),
        "hop_sec": stats(hop_secs),
        "frames_per_track": stats([float(x) for x in frame_counts]),
        "duration_coverage_error_pct": stats(duration_mismatch),
        "valence_smooth_global": stats(all_v),
        "arousal_smooth_global": stats(all_a),
        "track_span_valence": stats(track_va_span_v),
        "track_span_arousal": stats(track_va_span_a),
        "pad_zone_frames_ui_table": dict(pad_at_frame),
        "pad_zone_frames_search_targets": dict(pad_search_at_frame),
        "reachability_within_0.35_search": reach,
        "segment_entry": {
            "total": seg_total,
            "label_matches_motion_pad_pct": agree_pct,
            "motion_vs_segment_table_distance": stats(motion_vs_segment_va_dist),
            "top_disagreements": disagree[:12],
        },
        "cross_segment_emotion_change": jump_stats(cross_mood_jumps),
        "same_emotion_segment_boundary": jump_stats(same_mood_jumps),
        "top_cross_emotion_pairs": [
            {"from": a, "to": b, "count": c} for (a, b), c in top_cross
        ],
        "emotion_label_segment_counts": dict(
            Counter(
                (s.get("emotion_label") or "?").lower()
                for t in tracks
                for s in t.get("segments") or []
            )
        ),
    }


def write_svg_scatter(report: dict, path: Path, *, sample: int = 6000) -> None:
    """2D histogram-style scatter of motion frames colored by nearest search pad."""
    data = load_catalog(CATALOG)
    pts: list[tuple[float, float, str]] = []
    for track in data["tracks"]:
        m = track.get("motion")
        if not m:
            continue
        for v, a in zip(m["valence_smooth"], m["arousal_smooth"], strict=True):
            pts.append((v, a, nearest_pad(v, a, PAD_SEARCH)))

    rng = np.random.default_rng(42)
    if len(pts) > sample:
        idx = rng.choice(len(pts), size=sample, replace=False)
        pts = [pts[i] for i in idx]

    colors = {
        "calm": "#1F8A65",
        "joy": "#E8C030",
        "energy": "#F0A040",
        "tension": "#C85898",
        "sad": "#5A6CC0",
        "neutral": "#888888",
    }
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    w, h, pad = 720, 520, 48

    def sx(v):
        return pad + (v - xmin) / (xmax - xmin or 1) * (w - 2 * pad)

    def sy(v):
        return h - pad - (v - ymin) / (ymax - ymin or 1) * (h - 2 * pad)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">',
        '<rect width="100%" height="100%" fill="#181818"/>',
        f'<text x="{pad}" y="28" fill="#ccc" font-size="14">Motion frames (valence_smooth × arousal_smooth) — sample {len(pts)}</text>',
    ]
    for px, py, lab in pts:
        lines.append(
            f'<circle cx="{sx(px):.1f}" cy="{sy(py):.1f}" r="2.2" fill="{colors.get(lab,"#888")}" opacity="0.5"/>'
        )
    for lab, (tv, ta) in PAD_SEARCH.items():
        lines.append(
            f'<circle cx="{sx(tv):.1f}" cy="{sy(ta):.1f}" r="5" fill="none" stroke="{colors.get(lab,"#fff")}" stroke-width="1.5"/>'
        )
        lines.append(
            f'<text x="{sx(tv)+6:.0f}" y="{sy(ta):.0f}" fill="{colors.get(lab,"#fff")}" font-size="11">{lab}</text>'
        )
    lines.append(
        f'<text x="{w/2:.0f}" y="{h-12}" fill="#999" font-size="11" text-anchor="middle">Valence (motion)</text>'
    )
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Analyzing motion in {CATALOG} …")
    report = analyze(CATALOG)
    out_json = OUT_DIR / "motion_analysis.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_svg_scatter(report, OUT_DIR / "scatter_motion_frames.svg")
    print(f"Wrote {out_json}")
    print(f"Wrote {OUT_DIR / 'scatter_motion_frames.svg'}")

    print("\n=== Motion coverage ===")
    print(f"  tracks with motion: {report['n_with_motion']}/{report['n_tracks']}")
    print(f"  total frames: {report['total_frames']}")

    print("\n=== Global valence_smooth ===")
    for k, v in report["valence_smooth_global"].items():
        print(f"  {k}: {v}")

    print("\n=== Global arousal_smooth ===")
    for k, v in report["arousal_smooth_global"].items():
        print(f"  {k}: {v}")

    print("\n=== Reachability (search targets, r=0.35) ===")
    for pad, pct in sorted(report["reachability_within_0.35_search"].items(), key=lambda x: -x[1]):
        print(f"  {pad}: {pct}%")

    print("\n=== Segment label vs motion at entry ===")
    print(f"  agree: {report['segment_entry']['label_matches_motion_pad_pct']}%")
    print(f"  dist motion↔table: {report['segment_entry']['motion_vs_segment_table_distance']}")

    print("\n=== Cross-emotion segment boundaries ===")
    cc = report["cross_segment_emotion_change"]
    if cc:
        print(f"  count: {cc['count']}, |Δ| mean: {cc['magnitude']['mean']}")

    print("\n=== Top cross-emotion transitions ===")
    for row in report["top_cross_emotion_pairs"][:8]:
        print(f"  {row['from']} → {row['to']}: {row['count']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
