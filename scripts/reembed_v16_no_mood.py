#!/usr/bin/env python3
"""
Re-embed catalog_V16 segments without mood: in profile text (structure + bpm + MOSS description).

Compares clustering metrics vs original embeddings (with mood: prefix).
Writes:
  catalog/analysis_v16/embeddings_no_mood.npy
  catalog/analysis_v16/cluster_compare_no_mood.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "catalog_V16.json"
OUT_DIR = ROOT / "catalog" / "analysis_v16"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# moodpad-catalog on path
CATALOG_SRC = Path.home() / "Projects" / "moodpad-catalog" / "src"
if CATALOG_SRC.is_dir():
    sys.path.insert(0, str(CATALOG_SRC))

from moodpad_catalog.embeddings import (  # noqa: E402
    build_segment_embedding,
    format_segment_profile,
    normalize_bpm,
)


def load_segments():
    with CATALOG.open(encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for track in data.get("tracks", []):
        for seg in track.get("segments") or []:
            emb = seg.get("embedding")
            if not emb:
                continue
            rows.append(
                {
                    "emotion_label": seg.get("emotion_label") or "neutral",
                    "structure_label": seg.get("structure_label") or "",
                    "description": seg.get("description") or seg.get("moss_mood_text") or "",
                    "bpm": int(seg.get("bpm") or track.get("bpm") or 0),
                    "mood_confidence": float(seg.get("emotion_confidence") or seg.get("moss_mood_confidence") or 0),
                    "old_embedding": np.asarray(emb, dtype=np.float32),
                }
            )
    return data, rows


def build_matrix_no_mood_batch(rows: list[dict], *, batch_size: int = 128) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    profiles = [
        format_segment_profile(
            emotion_label=r["emotion_label"],
            structure_label=r["structure_label"],
            description=r["description"],
            bpm=r["bpm"],
            include_mood=False,
        )
        for r in rows
    ]

    encoder = SentenceTransformer(MODEL_NAME)
    text_vecs = encoder.encode(
        profiles,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    text_vecs = np.asarray(text_vecs, dtype=np.float32)

    out = np.zeros((len(rows), text_vecs.shape[1] + 2), dtype=np.float32)
    for i, r in enumerate(rows):
        bpm_norm = normalize_bpm(r["bpm"])
        conf = float(np.clip(r["mood_confidence"], 0.0, 1.0))
        vec = np.concatenate([text_vecs[i], np.asarray([bpm_norm, conf], dtype=np.float32)])
        norm = float(np.linalg.norm(vec))
        if norm > 1e-9:
            vec /= norm
        out[i] = vec
    return out


def cluster_metrics(X: np.ndarray, labels: list[str], *, sample: int = 8000) -> dict:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score

    n = X.shape[0]
    rng = np.random.default_rng(42)
    if n > sample:
        idx = rng.choice(n, size=sample, replace=False)
        Xs = X[idx]
        ys = [labels[i] for i in idx]
    else:
        Xs = X
        ys = labels

    uniq = sorted(set(labels))
    lab_to_id = {l: i for i, l in enumerate(uniq)}
    y = np.array([lab_to_id[l] for l in ys])

    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(Xs)
    evr = [float(x) for x in pca.explained_variance_ratio_]

    sil = float(silhouette_score(Xs, y)) if len(uniq) > 1 else 0.0

    by_label: dict[str, list[np.ndarray]] = defaultdict(list)
    for c, lab in zip(coords, ys, strict=True):
        by_label[lab].append(c)

    centroids = []
    spreads = []
    for lab in uniq:
        if lab not in by_label:
            continue
        arr = np.stack(by_label[lab])
        cent = arr.mean(axis=0)
        spread = float(np.mean(np.linalg.norm(arr - cent, axis=1)))
        centroids.append(lab)
        spreads.append(spread)

    mean_spread = float(np.mean(spreads)) if spreads else 0.0

    # between-centroid distance (higher = more separated moods in 2D)
    cents = []
    for lab in centroids:
        arr = np.stack(by_label[lab])
        cents.append(arr.mean(axis=0))
    between = 0.0
    if len(cents) > 1:
        pairs = 0
        for i in range(len(cents)):
            for j in range(i + 1, len(cents)):
                between += float(np.linalg.norm(cents[i] - cents[j]))
                pairs += 1
        between /= pairs

    km = KMeans(n_clusters=min(6, len(uniq)), random_state=42, n_init=10)
    km_ids = km.fit_predict(coords)
    purity = []
    for cid in range(km.n_clusters):
        mask = km_ids == cid
        if not mask.any():
            continue
        ctr = Counter(ys[i] for i in range(len(ys)) if mask[i])
        purity.append(ctr.most_common(1)[0][1] / int(mask.sum()))

    return {
        "silhouette": round(sil, 4),
        "pca_variance_sum": round(sum(evr), 4),
        "pca_variance_ratio": [round(x, 4) for x in evr],
        "mean_intra_cluster_spread_2d": round(mean_spread, 4),
        "mean_centroid_distance_2d": round(between, 4),
        "kmeans_mean_purity": round(float(np.mean(purity)) if purity else 0.0, 4),
        "mood_spread_2d": {
            lab: round(sp, 4) for lab, sp in zip(centroids, spreads, strict=True)
        },
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading catalog …")
    meta, rows = load_segments()
    n = len(rows)
    print(f"Segments: {n}")

    X_old = np.stack([r["old_embedding"] for r in rows])
    labels = [r["emotion_label"] for r in rows]

    print("\n=== Original embeddings (with mood in profile) ===")
    m_old = cluster_metrics(X_old, labels)
    for k, v in m_old.items():
        if k != "mood_spread_2d":
            print(f"  {k}: {v}")

    print("\nRe-embedding without mood (batch MiniLM) …")
    X_new = build_matrix_no_mood_batch(rows)
    np.save(OUT_DIR / "embeddings_no_mood.npy", X_new)
    print(f"Saved {OUT_DIR / 'embeddings_no_mood.npy'} shape={X_new.shape}")

    print("\n=== New embeddings (no mood in profile) ===")
    m_new = cluster_metrics(X_new, labels)
    for k, v in m_new.items():
        if k != "mood_spread_2d":
            print(f"  {k}: {v}")

    def delta(key: str) -> float:
        return round(m_new[key] - m_old[key], 4)

    compare = {
        "catalog": str(CATALOG),
        "n_segments": n,
        "model": MODEL_NAME,
        "profile_note": "include_mood=False: structure + bpm + MOSS description only",
        "emotion_counts": dict(Counter(labels)),
        "with_mood": m_old,
        "without_mood": m_new,
        "delta": {
            "silhouette": delta("silhouette"),
            "pca_variance_sum": delta("pca_variance_sum"),
            "mean_intra_cluster_spread_2d": delta("mean_intra_cluster_spread_2d"),
            "mean_centroid_distance_2d": delta("mean_centroid_distance_2d"),
            "kmeans_mean_purity": delta("kmeans_mean_purity"),
        },
    }

    out_path = OUT_DIR / "cluster_compare_no_mood.json"
    out_path.write_text(json.dumps(compare, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")

    print("\n--- Delta (no_mood - with_mood) ---")
    for k, v in compare["delta"].items():
        sign = "+" if v > 0 else ""
        print(f"  {k}: {sign}{v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
