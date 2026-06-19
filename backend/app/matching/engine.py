"""Matching engine facade (v3 implementation in core.py)."""

from __future__ import annotations

from app.matching import core
from app.matching.embedding_penalties import WeightedEmbedding
from app.matching.emotions import EMOTION_INTENT_IDS
from app.models.catalog import Track, VA

# Re-export for tests and legacy imports
find_best_match = core.find_best_match
find_session_seed = core.find_session_seed
find_joy_session_seed = core.find_joy_session_seed
prefetch_intents = core.prefetch_intents


def prefetch_l2_tree(
    tracks: list[Track],
    l1_intents: dict[str, list[dict]],
    root_track_id: str,
    root_exclude: set[str],
    *,
    play_counts: dict[str, int] | None = None,
    embedding_penalties: list[WeightedEmbedding] | None = None,
) -> dict[str, dict]:
    l1_top_ids = {
        l1_intents[str(intent)][0]["track_id"]
        for intent in EMOTION_INTENT_IDS
        if l1_intents.get(str(intent))
    }
    l2: dict[str, dict] = {}

    for intent in EMOTION_INTENT_IDS:
        branch = l1_intents.get(str(intent))
        if not branch:
            continue
        top = branch[0]
        branch_id = top["track_id"]
        sibling_ids = l1_top_ids - {branch_id}
        excludes = set(root_exclude) | {root_track_id} | sibling_ids

        branch_track = next((t for t in tracks if t.id == branch_id), None)
        seg = top["segment"]
        child_intents = prefetch_intents(
            tracks,
            VA(v=float(seg["v"]), ar=float(seg["ar"])),
            int(top["bpm"]),
            branch_id,
            excludes,
            current_track=branch_track,
            current_t_ms=int(top.get("audio_start_ms", 0)),
            play_counts=play_counts,
            embedding_penalties=embedding_penalties,
        )
        l2[str(intent)] = {
            "from": {
                "track_id": branch_id,
                "title": top["title"],
                "artist": top["artist"],
            },
            "intents": child_intents,
        }

    return l2


def prefetch_tree(
    tracks: list[Track],
    position: VA,
    bpm_current: int,
    current_track_id: str,
    exclude_ids: set[str],
    *,
    depth: int = 2,
    current_track: Track | None = None,
    current_t_ms: int | None = None,
    play_counts: dict[str, int] | None = None,
    intent_filter: frozenset[int] | None = None,
    restrict_mood_share_intents: frozenset[int] | None = None,
    embedding_penalties: list[WeightedEmbedding] | None = None,
) -> dict:
    l1 = prefetch_intents(
        tracks,
        position,
        bpm_current,
        current_track_id,
        exclude_ids,
        current_track=current_track,
        current_t_ms=current_t_ms,
        play_counts=play_counts,
        intent_filter=intent_filter,
        restrict_mood_share_intents=restrict_mood_share_intents,
        embedding_penalties=embedding_penalties,
    )
    result: dict = {"intents": l1, "l2": {}}
    if depth >= 2 and intent_filter is None:
        result["l2"] = prefetch_l2_tree(
            tracks,
            l1,
            current_track_id,
            exclude_ids,
            play_counts=play_counts,
            embedding_penalties=embedding_penalties,
        )
    return result
