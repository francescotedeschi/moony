"""Read MOSS sections from MoodPad catalog JSON (v1.7+ uses ``sections``, older uses ``segments``)."""

from __future__ import annotations

from typing import Any


def raw_track_sections(track: dict[str, Any]) -> list[dict[str, Any]]:
    """Return timeline blocks from a raw catalog track dict."""
    sections = track.get("sections")
    if isinstance(sections, list) and sections:
        return sections
    segments = track.get("segments")
    if isinstance(segments, list):
        return segments
    return []


def raw_section_label(raw: dict[str, Any], *, fallback: str = "unknown") -> str:
    """Structure label from v1.7 ``structure_label`` or legacy ``label``."""
    label = raw.get("label") or raw.get("structure_label") or fallback
    return str(label).lower()
