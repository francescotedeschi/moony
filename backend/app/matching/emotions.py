"""Pad emotion zones and catalog-aligned search targets."""

from __future__ import annotations

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


# Pad label positions (UI) — 7 Cyanite zones.
# Coordinates are centroids from cyanite_valence/arousal in catalog_V17.
EMOTION_BRANCHES: tuple[EmotionBranch, ...] = (
    EmotionBranch("Energetic", 3,  0.24,  0.67,  0.24,  0.67),
    EmotionBranch("Happy",     2,  0.65,  0.25,  0.65,  0.25),
    EmotionBranch("Chilled",   8,  0.29, -0.18,  0.29, -0.18),
    EmotionBranch("Romantic",  9,  0.10, -0.10,  0.10, -0.10),
    EmotionBranch("Sad",       6, -0.27, -0.14, -0.27, -0.14),
    EmotionBranch("Dark",      4, -0.28,  0.13, -0.28,  0.13),
    EmotionBranch("Tense",    10, -0.50,  0.70, -0.50,  0.70),
)

EMOTION_INTENT_IDS: list[int] = [b.intent for b in EMOTION_BRANCHES]

# Catalog segment emotion_label (7 zones) per pad branch
BRANCH_EMOTION_LABEL: dict[str, str] = {
    "Energetic": "energetic",
    "Happy":     "happy",
    "Chilled":   "chilled",
    "Romantic":  "romantic",
    "Sad":       "sad",
    "Dark":      "dark",
    "Tense":     "tense",
}


# Legacy 5-zone MOSS labels → canonical 7-zone labels (used at matching entry points).
LEGACY_LABEL_REMAP: dict[str, str] = {
    "calm":    "chilled",
    "joy":     "happy",
    "energy":  "energetic",
    "tension": "tense",
    # "sad" unchanged
}


def normalize_emotion_label(label: str) -> str:
    """Remap legacy 5-zone labels to their 7-zone equivalents; pass through others."""
    lab = (label or "").strip().lower()
    return LEGACY_LABEL_REMAP.get(lab, lab)


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
    # Low-arousal zones (Chilled, Romantic) use a tighter arousal scale to avoid
    # overshooting into adjacent zones; all others use the standard scale.
    _LOW_AROUSAL = {"Chilled", "Romantic"}
    arousal_scale = 0.45 if branch.name in _LOW_AROUSAL else 0.75
    search = VA(
        v=_clamp(branch.catalog_v + offset_v * 0.85),
        ar=_clamp(branch.catalog_ar + offset_ar * arousal_scale),
    )
    return search, branch
