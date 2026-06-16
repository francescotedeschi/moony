"""Session embedding penalties for early skip / same-mood handoff (soft cosine push-away)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from app.models.api import EmbeddingPenaltyRange
from app.models.catalog import Track

EARLY_REJECT_MAX_MS = 15_000
PENALTY_HALF_LIFE_MS = 10 * 60 * 1000
EMBEDDING_PENALTY_WEIGHT = 1.25
PENALTY_MIN_WEIGHT = 0.01


@dataclass(frozen=True)
class WeightedEmbedding:
    embedding: list[float]
    weight: float


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-9 or nb <= 1e-9:
        return 0.0
    return dot / (na * nb)


def penalty_decay_weight(added_at_ms: int, now_ms: int) -> float:
    age = max(0, now_ms - added_at_ms)
    return 0.5 ** (age / PENALTY_HALF_LIFE_MS)


def segment_overlaps_range(seg_t_start: int, seg_t_end: int, from_ms: int, to_ms: int) -> bool:
    return seg_t_start < to_ms and seg_t_end > from_ms


def embeddings_for_play_range(track: Track, from_ms: int, to_ms: int) -> list[list[float]]:
    capped_to = min(to_ms, from_ms + EARLY_REJECT_MAX_MS)
    if capped_to <= from_ms:
        return []
    out: list[list[float]] = []
    seen: set[tuple[float, ...]] = set()
    for seg in track.segments:
        if not seg.embedding:
            continue
        if not segment_overlaps_range(seg.t_start, seg.t_end, from_ms, capped_to):
            continue
        key = tuple(seg.embedding)
        if key in seen:
            continue
        seen.add(key)
        out.append(list(seg.embedding))
    return out


def resolve_weighted_penalties(
    ranges: list[EmbeddingPenaltyRange],
    tracks_by_id: dict[str, Track],
    now_ms: int | None = None,
) -> list[WeightedEmbedding]:
    if not ranges:
        return []
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    weighted: list[WeightedEmbedding] = []
    for entry in ranges:
        decay = penalty_decay_weight(entry.added_at_ms, now)
        if decay < PENALTY_MIN_WEIGHT:
            continue
        track = tracks_by_id.get(entry.track_id)
        if not track:
            continue
        for emb in embeddings_for_play_range(track, entry.from_ms, entry.to_ms):
            weighted.append(WeightedEmbedding(embedding=emb, weight=decay))
    return weighted


def embedding_penalty_adjustment(
    candidate_embedding: list[float] | None,
    penalties: list[WeightedEmbedding],
) -> float:
    """Subtract score when candidate embedding aligns with penalized session segments."""
    if not candidate_embedding or not penalties:
        return 0.0
    max_weighted_sim = 0.0
    for item in penalties:
        if item.weight <= 0:
            continue
        sim = _cosine_similarity(candidate_embedding, item.embedding)
        max_weighted_sim = max(max_weighted_sim, item.weight * max(0.0, sim))
    return -EMBEDDING_PENALTY_WEIGHT * max_weighted_sim
