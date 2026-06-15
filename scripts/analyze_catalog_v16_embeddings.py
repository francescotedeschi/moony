#!/usr/bin/env python3
"""Analyze catalog_V16 MiniLM embeddings: stats, 2D projection, mood clusters."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

CATALOG = Path(__file__).resolve().parents[1] / "catalog" / "catalog_V16.json"
OUT_DIR = Path(__file__).resolve().parents[1] / "catalog" / "analysis_v16"
PAD_COLORS = {
    "calm": "#6b9bd1",
    "joy": "#f4c542",
    "energy": "#e85d4c",
    "tension": "#9b59b6",
    "sad": "#5c6bc0",
    "neutral": "#9e9e9e",
}


def load_segments(path: Path, max_segments: int | None = None):
    """Stream-parse is heavy; load full JSON (RAM ~few GB)."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for track in data.get("tracks", []):
        tid = track.get("id", "")
        primary = track.get("primary_emotion", "")
        for seg in track.get("segments") or []:
            emb = seg.get("embedding")
            if not emb:
                continue
            rows.append(
                {
                    "track_id": tid,
                    "primary_emotion": primary,
                    "emotion_label": seg.get("emotion_label") or "unknown",
                    "moss_emotion_label": seg.get("moss_emotion_label") or "unknown",
                    "essentia_emotion_label": seg.get("essentia_emotion_label") or "unknown",
                    "emotion_source": seg.get("emotion_source") or "",
                    "emotion_disagreement": bool(seg.get("emotion_disagreement")),
                    "structure_label": seg.get("structure_label") or "",
                    "moss_mood_text": (seg.get("moss_mood_text") or "")[:80],
                    "embedding": np.asarray(emb, dtype=np.float32),
                }
            )
            if max_segments and len(rows) >= max_segments:
                return data, rows
    return data, rows


def pca_2d(X: np.ndarray) -> np.ndarray:
    from sklearn.decomposition import PCA

    pca = PCA(n_components=2, random_state=42)
    return pca.fit_transform(X)


def try_umap_2d(X: np.ndarray) -> np.ndarray | None:
    try:
        import umap

        reducer = umap.UMAP(n_components=2, random_state=42, n_neighbors=30, min_dist=0.1)
        return reducer.fit_transform(X)
    except Exception:
        return None


def cluster_summary(coords: np.ndarray, labels: list[str], top_n: int = 8) -> list[dict]:
    """Per-label centroid and spread in 2D."""
    by_label: dict[str, list[np.ndarray]] = defaultdict(list)
    for c, lab in zip(coords, labels, strict=True):
        by_label[lab].append(c)
    out = []
    for lab, pts in sorted(by_label.items(), key=lambda x: -len(x[1])):
        arr = np.stack(pts)
        centroid = arr.mean(axis=0)
        spread = float(np.mean(np.linalg.norm(arr - centroid, axis=1)))
        out.append(
            {
                "label": lab,
                "count": len(pts),
                "centroid_x": round(float(centroid[0]), 4),
                "centroid_y": round(float(centroid[1]), 4),
                "mean_radius": round(spread, 4),
            }
        )
    return out[:top_n]


def kmeans_mood(coords: np.ndarray, k: int = 6) -> np.ndarray:
    from sklearn.cluster import KMeans

    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    return km.fit_predict(coords)


def dominant_mood_per_cluster(cluster_ids: np.ndarray, mood_labels: list[str]) -> dict[int, str]:
    cross: dict[int, Counter] = defaultdict(Counter)
    for cid, mood in zip(cluster_ids, mood_labels, strict=True):
        cross[int(cid)][mood] += 1
    return {cid: ctr.most_common(1)[0][0] for cid, ctr in cross.items()}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Loading {CATALOG} ...")
    meta, rows = load_segments(CATALOG)
    n = len(rows)
    print(f"Segments with embeddings: {n}")

    X = np.stack([r["embedding"] for r in rows])
    print(f"Matrix shape: {X.shape}")

    mood_labels = [r["emotion_label"] for r in rows]
    moss_labels = [r["moss_emotion_label"] for r in rows]
    ess_labels = [r["essentia_emotion_label"] for r in rows]

    print("\n--- emotion_label distribution ---")
    for lab, cnt in Counter(mood_labels).most_common():
        print(f"  {lab}: {cnt} ({100*cnt/n:.1f}%)")

    print("\n--- emotion_source ---")
    for src, cnt in Counter(r["emotion_source"] for r in rows).most_common():
        print(f"  {src}: {cnt}")

    disagree = sum(1 for r in rows if r["emotion_disagreement"])
    print(f"\nMOSS vs Essentia disagreement: {disagree} ({100*disagree/n:.1f}%)")

    agree_mask = [r["emotion_label"] == r["moss_emotion_label"] == r["essentia_emotion_label"] for r in rows]
    print(f"Triple agreement (final=moss=essentia): {sum(agree_mask)} ({100*sum(agree_mask)/n:.1f}%)")

    print("\nPCA 2D ...")
    coords_pca = pca_2d(X)
    explained = None
    try:
        from sklearn.decomposition import PCA

        p = PCA(n_components=2, random_state=42).fit(X)
        explained = [round(float(x), 4) for x in p.explained_variance_ratio_]
        print(f"PCA explained variance ratio: {explained} (sum={sum(explained):.3f})")
    except Exception:
        pass

    coords_umap = try_umap_2d(X)
    use_coords = coords_umap if coords_umap is not None else coords_pca
    method = "umap" if coords_umap is not None else "pca"

    print(f"\nUsing 2D projection: {method}")
    mood_centroids = cluster_summary(use_coords, mood_labels)
    print("\n--- Mood centroids in 2D (by emotion_label) ---")
    for row in mood_centroids:
        print(f"  {row['label']:10} n={row['count']:5}  center=({row['centroid_x']}, {row['centroid_y']})  spread={row['mean_radius']}")

    km_ids = kmeans_mood(use_coords, k=6)
    cluster_moods = dominant_mood_per_cluster(km_ids, mood_labels)
    print("\n--- KMeans k=6 on 2D coords → dominant emotion_label ---")
    for cid in sorted(cluster_moods):
        mask = km_ids == cid
        cnt = int(mask.sum())
        dom = cluster_moods[cid]
        mix = Counter(mood_labels[i] for i in range(n) if km_ids[i] == cid).most_common(4)
        print(f"  cluster {cid}: n={cnt}, dominant={dom}, mix={mix}")

    # Subsample for canvas JSON (max 4000 points)
    rng = np.random.default_rng(42)
    idx = np.arange(n)
    if n > 4000:
        idx = rng.choice(n, size=4000, replace=False)

    points = []
    for i in idx:
        points.append(
            {
                "x": round(float(use_coords[i, 0]), 4),
                "y": round(float(use_coords[i, 1]), 4),
                "mood": mood_labels[i],
                "moss": moss_labels[i],
                "essentia": ess_labels[i],
                "structure": rows[i]["structure_label"],
                "disagree": rows[i]["emotion_disagreement"],
            }
        )

    report = {
        "catalog": str(CATALOG),
        "version": meta.get("version"),
        "embedding_model": meta.get("embedding_model"),
        "n_tracks": len(meta.get("tracks", [])),
        "n_segments": n,
        "embedding_dim": int(X.shape[1]),
        "projection": method,
        "pca_explained_variance_ratio": explained,
        "emotion_counts": dict(Counter(mood_labels)),
        "emotion_source_counts": dict(Counter(r["emotion_source"] for r in rows)),
        "disagreement_pct": round(100 * disagree / n, 2),
        "mood_centroids_2d": mood_centroids,
        "kmeans_clusters": [
            {"id": int(cid), "dominant_mood": cluster_moods[cid], "size": int((km_ids == cid).sum())}
            for cid in sorted(cluster_moods)
        ],
        "points_sample": points,
        "pad_colors": PAD_COLORS,
    }

    out_json = OUT_DIR / "embedding_analysis.json"
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote {out_json}")

    # Simple SVG scatter for quick view
    svg_path = OUT_DIR / "scatter_mood.svg"
    _write_svg(points, svg_path)
    print(f"Wrote {svg_path}")

    return 0


def _write_svg(points: list[dict], path: Path, size: int = 800) -> None:
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    pad = 40

    def scale(v, lo, hi):
        if hi == lo:
            return size / 2
        return pad + (v - lo) / (hi - lo) * (size - 2 * pad)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">',
        '<rect width="100%" height="100%" fill="#1a1a1e"/>',
        f'<text x="{pad}" y="24" fill="#ccc" font-size="14">catalog_V16 MiniLM embeddings ({len(points)} pts)</text>',
    ]
    for p in points:
        cx = scale(p["x"], xmin, xmax)
        cy = scale(p["y"], ymin, ymax)
        col = PAD_COLORS.get(p["mood"], "#888")
        lines.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.5" fill="{col}" opacity="0.55"/>')
    for mood, col in PAD_COLORS.items():
        if mood == "neutral":
            continue
        lines.append(f'<circle cx="0" cy="0" r="0" fill="{col}"/>')  # legend via text
    ly = size - 20
    for i, (mood, col) in enumerate(PAD_COLORS.items()):
        lines.append(
            f'<text x="{pad + i*110}" y="{ly}" fill="{col}" font-size="12">{mood}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
