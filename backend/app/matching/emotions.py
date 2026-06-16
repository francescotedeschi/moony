"""Pad emotion zones and catalog-aligned search targets."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.models.catalog import VA

# API prefetch key "0" — segment mood at playhead (legacy name: same_mood). Not pad target mood.
SEGMENT_MOOD_INTENT = 0
SAME_MOOD_INTENT = SEGMENT_MOOD_INTENT


@dataclass(frozen=True)
class EmotionBranch:
    name: str
    intent: int
    """Where the label sits on the pad UI."""
    pad_v: float
    pad_ar: float
    """Best achievable mood in loaded catalog (1000-track analysis)."""
    catalog_v: float
    catalog_ar: float


# Pad label positions (UI) — unchanged for EmotionPad rendering.
EMOTION_BRANCHES: tuple[EmotionBranch, ...] = (
    EmotionBranch("Calm", 7, 0.0, -0.8, -0.05, -0.51),
    EmotionBranch("Joy", 2, 0.8, 0.6, 0.79, 0.61),
    EmotionBranch("Energy", 3, 0.2, 0.9, 0.21, 0.93),
    EmotionBranch("Tension", 4, -0.5, 0.7, -0.50, 0.71),
    EmotionBranch("Sad", 6, -0.7, -0.5, -0.70, -0.51),
)

EMOTION_INTENT_IDS: list[int] = [b.intent for b in EMOTION_BRANCHES]

# Catalog segment emotion_label (5 zones) per pad branch
BRANCH_EMOTION_LABEL: dict[str, str] = {
    "Calm": "calm",
    "Joy": "joy",
    "Energy": "energy",
    "Tension": "tension",
    "Sad": "sad",
}


def emotion_label_for_branch(branch: EmotionBranch) -> str:
    return BRANCH_EMOTION_LABEL.get(branch.name, "neutral")


def emotion_label_for_va(user: VA) -> str:
    return emotion_label_for_branch(nearest_branch(user))

# Legacy map for tests / L2 tree
EMOTION_TARGETS: dict[int, VA] = {
    b.intent: VA(v=b.catalog_v, ar=b.catalog_ar) for b in EMOTION_BRANCHES
}


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def nearest_branch(user: VA) -> EmotionBranch:
    best = EMOTION_BRANCHES[0]
    best_d = 1e9
    for branch in EMOTION_BRANCHES:
        d = (user.v - branch.pad_v) ** 2 + (user.ar - branch.pad_ar) ** 2
        if d < best_d:
            best_d = d
            best = branch
    return best


def branch_target_va(intent: int, *, current_va: VA | None = None) -> VA:
    if intent == SAME_MOOD_INTENT and current_va is not None:
        return current_va
    for branch in EMOTION_BRANCHES:
        if branch.intent == intent:
            return VA(v=branch.catalog_v, ar=branch.catalog_ar)
    return VA(v=0.0, ar=0.0)


def intent_target_va(intent: int, *, current_va: VA | None = None) -> VA:
    return branch_target_va(intent, current_va=current_va)


def resolve_search_target(user: VA) -> tuple[VA, EmotionBranch]:
    """
    Map pad coordinates to a catalog-search target.
    Keeps user offset from nearest pad zone, scaled into catalog mood space.
    """
    branch = nearest_branch(user)
    offset_v = user.v - branch.pad_v
    offset_ar = user.ar - branch.pad_ar
    # Arousal in catalog is narrower than pad labels suggest (especially Calm).
    arousal_scale = 0.45 if branch.name == "Calm" else 0.75
    search = VA(
        v=_clamp(branch.catalog_v + offset_v * 0.85),
        ar=_clamp(branch.catalog_ar + offset_ar * arousal_scale),
    )
    return search, branch
