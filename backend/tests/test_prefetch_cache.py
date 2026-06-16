from app.matching.prefetch_cache import (
    clear_prefetch_cache,
    get_cached_prefetch,
    prefetch_cache_key,
    set_cached_prefetch,
)
from app.models.api import PrefetchRequest
from app.models.catalog import VA


def test_prefetch_cache_hit_same_bucket():
    clear_prefetch_cache()
    body = PrefetchRequest(
        current_track_id="t1",
        t_ms=5100,
        position=VA(v=0.21, ar=-0.49),
        bpm_current=120,
        depth=1,
    )
    payload = {"current_track_id": "t1", "t_ms": 5100, "intents": {}, "l2": {}}
    set_cached_prefetch(body, payload)

    near = PrefetchRequest(
        current_track_id="t1",
        t_ms=5200,
        position=VA(v=0.24, ar=-0.46),
        bpm_current=120,
        depth=1,
    )
    assert get_cached_prefetch(near) == payload
    assert prefetch_cache_key(body) == prefetch_cache_key(near)


def test_prefetch_cache_miss_different_track():
    clear_prefetch_cache()
    body = PrefetchRequest(
        current_track_id="t1",
        t_ms=0,
        position=VA(v=0.0, ar=0.0),
        bpm_current=100,
        depth=1,
    )
    set_cached_prefetch(body, {"intents": {}})
    other = PrefetchRequest(
        current_track_id="t2",
        t_ms=0,
        position=VA(v=0.0, ar=0.0),
        bpm_current=100,
        depth=1,
    )
    assert get_cached_prefetch(other) is None
