"""Short-lived in-memory cache for POST /prefetch (same track + coarse position/time)."""

from __future__ import annotations

import time
from typing import Any

from app.models.api import PrefetchRequest
from app.models.catalog import VA

PREFETCH_CACHE_TTL_SEC = 45.0
PREFETCH_CACHE_MAX_ENTRIES = 64
_MS_BUCKET = 4000
_VA_BUCKET = 0.1

_cache: dict[tuple[Any, ...], tuple[float, dict]] = {}


def _bucket_ms(t_ms: int) -> int:
    return max(0, (t_ms // _MS_BUCKET) * _MS_BUCKET)


def _bucket_va(position: VA) -> tuple[float, float]:
    return (round(position.v / _VA_BUCKET) * _VA_BUCKET, round(position.ar / _VA_BUCKET) * _VA_BUCKET)


def prefetch_cache_key(body: PrefetchRequest) -> tuple[Any, ...]:
    single = (
        0
        if body.same_mood_only
        else body.single_intent
    )
    restrict = body.same_mood_only or (
        body.single_intent is not None and body.restrict_mood_share
    )
    return (
        body.current_track_id,
        _bucket_ms(body.t_ms),
        _bucket_va(body.position),
        body.bpm_current,
        body.depth,
        single,
        restrict,
        tuple(sorted(body.exclude_ids)),
        tuple(
            sorted(
                (p.track_id, p.from_ms, p.to_ms, p.added_at_ms)
                for p in body.embedding_penalties
            )
        ),
    )


def get_cached_prefetch(body: PrefetchRequest) -> dict | None:
    key = prefetch_cache_key(body)
    entry = _cache.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if time.monotonic() > expires_at:
        _cache.pop(key, None)
        return None
    return payload


def set_cached_prefetch(body: PrefetchRequest, payload: dict) -> None:
    if len(_cache) >= PREFETCH_CACHE_MAX_ENTRIES:
        now = time.monotonic()
        stale = [k for k, (exp, _) in _cache.items() if exp <= now]
        for k in stale:
            _cache.pop(k, None)
        if len(_cache) >= PREFETCH_CACHE_MAX_ENTRIES:
            oldest = min(_cache.items(), key=lambda item: item[1][0])[0]
            _cache.pop(oldest, None)
    key = prefetch_cache_key(body)
    _cache[key] = (time.monotonic() + PREFETCH_CACHE_TTL_SEC, payload)


def clear_prefetch_cache() -> None:
    _cache.clear()
