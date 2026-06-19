"""Pad → legacy emotion label helpers for Cyanite section mapping."""

from __future__ import annotations

# Used by cyanite_enrich to map Cyanite mood tags onto coarse pad names.
_PAD_LABELS: dict[str, str] = {
    "Calm": "calm",
    "Joy": "joy",
    "Energy": "energy",
    "Tension": "tension",
    "Sad": "sad",
    "Neutral": "neutral",
}

_PAD_VA: dict[str, tuple[float, float]] = {
    "calm": (0.0, -0.8),
    "joy": (0.8, 0.6),
    "energy": (0.2, 0.9),
    "tension": (-0.5, 0.7),
    "sad": (-0.7, -0.5),
    "neutral": (0.0, 0.0),
}


def va_for_emotion_label(label: str) -> tuple[float, float]:
    return _PAD_VA.get((label or "").strip().lower(), (0.0, 0.0))


def emotion_label_for_pad_name(pad_name: str) -> str:
    return _PAD_LABELS.get(pad_name, "neutral")
