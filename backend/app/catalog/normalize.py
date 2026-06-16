"""Normalize MoodPad / MOSS catalog v1.2 into internal Track models."""

from __future__ import annotations

import logging
from typing import Any

from app.catalog.mood_distribution import compute_mood_distribution
from app.catalog.sections import raw_section_label, raw_track_sections
from app.models.catalog import (
    BeatGrid,
    Catalog,
    TrackLoudness,
    MusixmatchRef,
    Segment,
    Track,
    TrackMotion,
    Transition,
)

logger = logging.getLogger(__name__)


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


# Moony pad labels (5 zones) — used when segment has emotion_label but no V/A
PAD_EMOTION_VA: dict[str, tuple[float, float]] = {
    "calm": (0.0, -0.8),
    "joy": (0.8, 0.6),
    "energy": (0.2, 0.9),
    "tension": (-0.5, 0.7),
    "sad": (-0.7, -0.5),
    "neutral": (0.0, 0.0),
}

# Maps catalog primary_emotion → Valence / Arousal (8 fetch buckets)
EMOTION_VA: dict[str, tuple[float, float]] = {
    "calm": (0.25, -0.65),
    "melancholic": (-0.55, -0.35),
    "hopeful": (0.45, 0.25),
    "energetic": (0.55, 0.85),
    "tense": (-0.35, 0.75),
    "warm": (0.65, 0.15),
    "dreamy": (0.35, -0.25),
    "playful": (0.75, 0.45),
}

LABEL_AROUSAL_NUDGE: dict[str, float] = {
    "chorus": 0.12,
    "chorus1": 0.12,
    "chorus2": 0.12,
    "intro": -0.08,
    "outro": -0.1,
    "verse": 0.0,
    "verse1": 0.0,
    "verse2": 0.0,
}


def _estimate_bpm(duration_sec: float, tags: list[str], primary_emotion: str) -> int:
    tag_str = " ".join(tags).lower()
    if any(k in tag_str for k in ("ambient", "slow", "peaceful", "calm")):
        return 80
    if any(k in tag_str for k in ("dance", "electronic", "energetic", "fast")):
        return 128
    if primary_emotion in ("calm", "melancholic", "dreamy"):
        return 85
    if primary_emotion in ("energetic", "playful", "tense"):
        return 120
    if duration_sec > 240:
        return 90
    return 110


def _normalize_segments(
    raw_segments: list[dict[str, Any]],
    base_v: float,
    base_ar: float,
) -> list[Segment]:
    if not raw_segments:
        return []

    sorted_segs = sorted(raw_segments, key=lambda s: float(s.get("end_sec", s.get("t_end", 0))))
    normalized: list[Segment] = []
    prev_end_ms = 0

    for raw in sorted_segs:
        end_sec = float(raw.get("end_sec", raw.get("t_end", 0) / 1000.0))
        start_sec = float(raw.get("start_sec", raw.get("t_start", prev_end_ms / 1000.0) / 1000.0))
        t_start = int(max(start_sec, prev_end_ms / 1000.0) * 1000) if start_sec <= 0 else int(start_sec * 1000)
        t_end = int(end_sec * 1000)
        if t_end <= t_start:
            continue

        label = raw_section_label(raw)
        v = float(raw.get("valence", raw.get("v", 0.0)))
        ar = float(raw.get("arousal", raw.get("ar", 0.0)))
        if abs(v) < 1e-6 and abs(ar) < 1e-6:
            seg_emotion = str(raw.get("emotion_label") or "").strip().lower()
            if seg_emotion in PAD_EMOTION_VA:
                v, ar = PAD_EMOTION_VA[seg_emotion]
                ar = ar + LABEL_AROUSAL_NUDGE.get(label, 0.0)
            else:
                v, ar = base_v, base_ar + LABEL_AROUSAL_NUDGE.get(label, 0.0)

        emb = raw.get("embedding")
        embedding = [float(x) for x in emb] if isinstance(emb, list) else []

        normalized.append(
            Segment(
                t_start=t_start,
                t_end=t_end,
                v=max(-1.0, min(1.0, v)),
                ar=max(-1.0, min(1.0, ar)),
                label=label,
                emotion_label=str(
                    raw.get("emotion_label") or raw.get("moss_emotion_label") or ""
                ).strip().lower(),
                description=str(raw.get("description") or "").strip(),
                moss_emotion_label=str(raw.get("moss_emotion_label") or "").strip().lower(),
                essentia_emotion_label=str(raw.get("essentia_emotion_label") or "").strip().lower(),
                embedding=embedding,
            )
        )
        prev_end_ms = t_end

    return normalized


def _build_transitions(segments: list[Segment]) -> list[Transition]:
    transitions: list[Transition] = []
    for i in range(1, len(segments)):
        prev, curr = segments[i - 1], segments[i]
        transitions.append(
            Transition(
                from_seg=i - 1,
                to_seg=i,
                dv=_clamp(curr.v - prev.v),
                dar=_clamp(curr.ar - prev.ar),
            )
        )
    return transitions


def _normalize_motion(raw: Any) -> TrackMotion | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or not raw.get("energy"):
        return None
    try:
        return TrackMotion.model_validate(raw)
    except Exception:
        logger.warning("Invalid motion block — skipping")
        return None


def _normalize_beat_grid(raw: dict[str, Any], bpm: int) -> BeatGrid:
    bg = raw.get("beat_grid")
    if isinstance(bg, dict):
        bar = int(bg.get("bar_ms") or 0)
        return BeatGrid(
            offset_ms=max(0, int(bg.get("offset_ms") or 0)),
            bar_ms=bar if bar > 0 else int(60000 / max(40, bpm) * 4),
        )
    return BeatGrid(offset_ms=0, bar_ms=int(60000 / max(40, bpm) * 4))


def _normalize_loudness(raw: Any) -> TrackLoudness | None:
    if raw is None:
        return None
    if isinstance(raw, dict) and "integrated_lufs" in raw:
        try:
            return TrackLoudness.model_validate(raw)
        except Exception:
            logger.debug("Skipping invalid track loudness: %s", raw)
            return None
    if isinstance(raw, list):
        candidates: list[dict] = [item for item in raw if isinstance(item, dict)]
        if not candidates:
            return None
        at_zero = next(
            (c for c in candidates if c.get("start_bucket_sec") in (0, None)),
            None,
        )
        pick = at_zero or min(
            candidates,
            key=lambda c: int(c.get("start_bucket_sec", 0)),
        )
        try:
            return TrackLoudness(
                integrated_lufs=float(pick["integrated_lufs"]),
                true_peak_dbfs=float(pick["true_peak_dbfs"]),
                youtube_gain=float(pick["youtube_gain"]),
            )
        except (KeyError, TypeError, ValueError):
            logger.debug("Skipping legacy loudness list entry: %s", pick)
            return None
    return None


def _normalize_musixmatch(raw: dict[str, Any] | None) -> MusixmatchRef | None:
    if not raw:
        return None
    track_id = raw.get("track_id")
    commontrack_id = raw.get("commontrack_id")
    tid = str(track_id) if track_id not in (None, "", "null") else None
    cid = str(commontrack_id) if commontrack_id not in (None, "", "null") else None
    return MusixmatchRef(
        commontrack_id=cid,
        track_id=tid,
        has_lyrics=int(raw.get("has_lyrics") or 0),
        has_subtitles=int(raw.get("has_subtitles") or 0),
    )


def normalize_catalog(data: dict[str, Any]) -> Catalog:
    """Accept MoodPad v1.2 export or native moony catalog."""
    version = str(data.get("version", "1.2"))
    if data.get("catalog_schema") == "moodpad-catalog-musicathon" or _looks_like_v12_track(
        data.get("tracks", [{}])[0] if data.get("tracks") else {}
    ):
        return _from_moodpad_export(data, version)
    return Catalog.model_validate(data)


def _looks_like_v12_track(track: dict[str, Any]) -> bool:
    return "jamendo" in track and isinstance(track.get("jamendo"), dict)


def _from_moodpad_export(data: dict[str, Any], version: str = "1.2") -> Catalog:
    tracks: list[Track] = []
    for raw in data.get("tracks", []):
        primary = str(raw.get("primary_emotion", "calm")).lower()
        base_v, base_ar = EMOTION_VA.get(primary, (0.0, 0.0))
        jamendo = raw.get("jamendo") or {}
        audio_url = jamendo.get("audio_url") or raw.get("audio_url", "")
        if not audio_url:
            logger.debug("Skipping %s — no audio_url", raw.get("id"))
            continue

        tags = jamendo.get("tags") or raw.get("jamendo_tags") or []
        duration = float(raw.get("duration_sec", jamendo.get("duration", 180)) or 180)
        bpm = int(raw.get("bpm") or _estimate_bpm(duration, tags, primary))

        segments = _normalize_segments(raw_track_sections(raw), base_v, base_ar)
        if not segments:
            segments = [
                Segment(
                    t_start=0,
                    t_end=int(duration * 1000),
                    v=base_v,
                    ar=base_ar,
                    label="full",
                )
            ]

        transitions = [
            Transition.model_validate(t) for t in raw.get("transitions", [])
        ] or _build_transitions(segments)

        mood_distribution = compute_mood_distribution(segments)
        tracks.append(
            Track(
                id=str(raw["id"]),
                title=str(raw.get("title", "")),
                artist=str(raw.get("artist", "")),
                bpm=bpm,
                audio_url=str(audio_url),
                duration_sec=duration,
                jamendo_tags=list(tags) if isinstance(tags, list) else [],
                musixmatch=_normalize_musixmatch(raw.get("musixmatch")),
                beat_grid=_normalize_beat_grid(raw, bpm),
                segments=segments,
                transitions=transitions,
                motion=_normalize_motion(raw.get("motion")),
                loudness=_normalize_loudness(raw.get("loudness")),
                mood_distribution=mood_distribution,
            )
        )

    with_motion = sum(1 for t in tracks if t.has_motion)
    logger.info(
        "Normalized %d tracks from MoodPad catalog (version=%s, with_motion=%d)",
        len(tracks),
        version,
        with_motion,
    )
    return Catalog(tracks=tracks)
