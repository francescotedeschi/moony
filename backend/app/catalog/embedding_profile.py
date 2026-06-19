"""Catalog section embedding profile — structure + BPM + MOSS description (v1.6 convention)."""

from __future__ import annotations

from typing import Any

from app.catalog.sections import raw_section_label, raw_track_sections

EMBEDDING_PROFILE = "structure+bpm+description"


def section_description(raw: dict[str, Any]) -> str:
    return str(raw.get("description") or "").strip()


def section_mood_confidence(raw: dict[str, Any]) -> float:
    for key in ("emotion_confidence", "moss_mood_confidence"):
        val = raw.get(key)
        if val is not None:
            try:
                return float(max(0.0, min(1.0, float(val))))
            except (TypeError, ValueError):
                continue
    return 0.0


def resolve_track_bpm(track: dict[str, Any], *, estimate_bpm) -> int:
    """Track BPM from catalog field or heuristic fallback."""
    try:
        bpm = int(track.get("bpm") or 0)
    except (TypeError, ValueError):
        bpm = 0
    if bpm > 0:
        return bpm

    jamendo = track.get("jamendo") or {}
    tags = jamendo.get("tags") or track.get("jamendo_tags") or []
    if not isinstance(tags, list):
        tags = []
    duration = float(track.get("duration_sec") or jamendo.get("duration") or 180)
    primary = str(track.get("primary_emotion") or "calm").lower()
    return int(estimate_bpm(duration, tags, primary))


def enrich_section_fields(
    section: dict[str, Any],
    *,
    track_bpm: int,
    embedding_profile: str = EMBEDDING_PROFILE,
) -> bool:
    """Set ``bpm`` and ``embedding_profile`` on a raw section when missing or stale."""
    changed = False
    if section.get("bpm") != track_bpm:
        section["bpm"] = track_bpm
        changed = True
    if section.get("embedding_profile") != embedding_profile:
        section["embedding_profile"] = embedding_profile
        changed = True
    return changed


def enrich_catalog_embedding_profile(
    data: dict[str, Any],
    *,
    estimate_bpm,
    embedding_profile: str = EMBEDDING_PROFILE,
) -> tuple[int, int]:
    """
    Add catalog-level ``embedding_profile``, per-section ``bpm`` and ``embedding_profile``.

    Returns (tracks_updated, sections_updated).
    """
    if data.get("embedding_profile") != embedding_profile:
        data["embedding_profile"] = embedding_profile

    tracks_updated = 0
    sections_updated = 0
    for track in data.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        track_bpm = resolve_track_bpm(track, estimate_bpm=estimate_bpm)
        track_changed = False
        for section in raw_track_sections(track):
            if not isinstance(section, dict):
                continue
            if enrich_section_fields(
                section,
                track_bpm=track_bpm,
                embedding_profile=embedding_profile,
            ):
                track_changed = True
                sections_updated += 1
        if track_changed:
            tracks_updated += 1

    return tracks_updated, sections_updated
