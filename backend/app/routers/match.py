import random

from fastapi import APIRouter, HTTPException

from app.catalog.loader import catalog_store
from app.catalog.loudness import youtube_gain_for_track
from app.catalog.timeline import track_timeline_payload
from app.matching.embedding_penalties import resolve_weighted_penalties
from app.matching.engine import find_best_match, find_session_seed, prefetch_l2_tree, prefetch_tree
from app.matching.emotions import emotion_label_for_va
from app.matching.emotions import SAME_MOOD_INTENT
from app.matching.prefetch_cache import get_cached_prefetch, set_cached_prefetch
from app.play_stats import play_stats_store
from app.matching.motion_crossfade import crossfade_plan_between_tracks
from app.models.api import MatchRequest, MatchResponse, PrefetchL2Request, PrefetchRequest

router = APIRouter(tags=["matching"])


def _track_timeline(track_id: str) -> dict:
    track = catalog_store.catalog.get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return track_timeline_payload(track)


@router.get("/tracks/{track_id}/timeline")
async def get_track_timeline(track_id: str) -> dict:
    return _track_timeline(track_id)


@router.post("/match", response_model=MatchResponse)
async def match_track(body: MatchRequest) -> MatchResponse:
    cat = catalog_store.catalog
    if not cat.tracks:
        raise HTTPException(status_code=503, detail="Catalog not loaded")

    current_track = (
        cat.get_track(body.current_track_id) if body.current_track_id else None
    )
    play_counts = play_stats_store.get_play_counts()
    tracks_by_id = {t.id: t for t in cat.tracks}
    embedding_penalties = resolve_weighted_penalties(body.embedding_penalties, tracks_by_id)
    excludes = set(body.exclude_ids)
    if body.session_seed:
        mood = emotion_label_for_va(body.position)
        if mood not in {"chilled", "happy", "energetic"}:
            mood = random.choice(["chilled", "happy", "energetic"])
        result = find_session_seed(cat.tracks, excludes, mood, play_counts=play_counts)
    elif body.same_mood_handoff:
        result = find_best_match(
            cat.tracks,
            body.position,
            body.direction,
            body.bpm_current,
            excludes,
            body.current_t_ms,
            current_track=current_track,
            same_mood_handoff=True,
            play_counts=play_counts,
            embedding_penalties=embedding_penalties,
        )
    else:
        result = find_best_match(
            cat.tracks,
            body.position,
            body.direction,
            body.bpm_current,
            excludes,
            body.current_t_ms,
            current_track=current_track,
            pad_only=body.pad_only,
            play_counts=play_counts,
            embedding_penalties=embedding_penalties,
        )
    if not result:
        raise HTTPException(
            status_code=404,
            detail="No matching track found for target emotion in catalog",
        )

    track, seg, _idx, score, start_ms, entry_va, mood_distance, mood_quality, target_emotion = (
        result
    )
    mm = track.musixmatch.model_dump() if track.musixmatch else None
    transition = crossfade_plan_between_tracks(
        from_track=current_track,
        from_t_ms=body.current_t_ms,
        to_track=track,
        entry_ms=start_ms,
        entry_va=entry_va,
        bpm_from=body.bpm_current,
        bpm_to=track.bpm,
    )
    xf = transition.plan
    start_ms = transition.entry_ms

    return MatchResponse(
        track_id=track.id,
        title=track.title,
        artist=track.artist,
        bpm=track.bpm,
        audio_url=track.audio_url,
        start_ms=start_ms,
        score=round(score, 4),
        mood_distance=round(mood_distance, 4),
        mood_quality=mood_quality,
        emotion_label=target_emotion,
        segment={
            "v": entry_va.v,
            "ar": entry_va.ar,
            "label": seg.label,
            "emotion_label": seg.emotion_label or target_emotion,
            "t_start": start_ms,
            "t_end": seg.t_end,
        },
        musixmatch=mm,
        bpm_from=body.bpm_current,
        bpm_to=track.bpm,
        playback_rate_start=xf.playback_rate_start,
        playback_rate_end=xf.playback_rate_end,
        playback_rate_out_end=xf.playback_rate_out_end,
        crossfade_ms=xf.crossfade_ms,
        crossfade_curve=xf.curve,
        crossfade_mood_jump=xf.mood_jump,
        crossfade_start_ms=xf.crossfade_start_ms,
        youtube_playback_gain=youtube_gain_for_track(track),
    )


@router.post("/prefetch")
async def prefetch(body: PrefetchRequest) -> dict:
    cached = get_cached_prefetch(body)
    if cached is not None:
        return cached

    cat = catalog_store.catalog
    current_track = cat.get_track(body.current_track_id)
    prefetch_excludes = {body.current_track_id, *body.exclude_ids}
    play_counts = play_stats_store.get_play_counts()
    tracks_by_id = {t.id: t for t in cat.tracks}
    embedding_penalties = resolve_weighted_penalties(body.embedding_penalties, tracks_by_id)
    intent_filter: frozenset[int] | None = None
    restrict_mood_share_intents: frozenset[int] | None = None
    narrow_prefetch = body.same_mood_only or body.single_intent is not None
    if body.same_mood_only:
        intent_filter = frozenset({SAME_MOOD_INTENT})
        restrict_mood_share_intents = frozenset({SAME_MOOD_INTENT})
    elif body.single_intent is not None:
        intent_filter = frozenset({body.single_intent})
        if body.restrict_mood_share:
            restrict_mood_share_intents = frozenset({body.single_intent})
    tree = prefetch_tree(
        cat.tracks,
        body.position,
        body.bpm_current,
        body.current_track_id,
        prefetch_excludes,
        depth=1 if narrow_prefetch else body.depth,
        current_track=current_track,
        current_t_ms=body.t_ms,
        play_counts=play_counts,
        intent_filter=intent_filter,
        restrict_mood_share_intents=restrict_mood_share_intents,
        embedding_penalties=embedding_penalties,
    )
    payload = {
        "current_track_id": body.current_track_id,
        "t_ms": body.t_ms,
        "intents": tree["intents"],
        "l2": tree["l2"],
    }
    set_cached_prefetch(body, payload)
    return payload


@router.post("/prefetch/l2")
async def prefetch_l2(body: PrefetchL2Request) -> dict:
    """Background L2 tree from L1 branches already shown to the client."""
    cat = catalog_store.catalog
    l2 = prefetch_l2_tree(
        cat.tracks,
        body.l1_intents,
        body.current_track_id,
        {body.current_track_id},
    )
    return {"l2": l2}
