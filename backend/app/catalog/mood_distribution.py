"""Per-track mood mix over the five pad zones (segment counts / total segments)."""

from __future__ import annotations

from app.matching.emotions import emotion_label_for_va
from app.matching.motion_match import effective_segment_emotion_label
from app.models.catalog import Segment, Track, VA

# Fixed axis order — index matches pad branches Calm → Sad.
MOOD_DISTRIBUTION_LABELS: tuple[str, ...] = ("calm", "joy", "energy", "tension", "sad")
MOOD_DISTRIBUTION_SIZE = len(MOOD_DISTRIBUTION_LABELS)
_PAD_MOOD_SET = frozenset(MOOD_DISTRIBUTION_LABELS)


def segment_pad_mood(seg: Segment) -> str:
    """Map a segment to one of the five pad mood labels."""
    label = effective_segment_emotion_label(seg)
    if label in _PAD_MOOD_SET:
        return label
    return emotion_label_for_va(VA(v=seg.v, ar=seg.ar))


def compute_mood_distribution(segments: list[Segment]) -> list[float]:
    """
    Return mood percentages in ``MOOD_DISTRIBUTION_LABELS`` order.
    Each value is in [0, 1] and the vector sums to 1 when segments exist.
    """
    if not segments:
        return [0.0] * MOOD_DISTRIBUTION_SIZE

    counts = {label: 0 for label in MOOD_DISTRIBUTION_LABELS}
    for seg in segments:
        counts[segment_pad_mood(seg)] += 1

    total = float(len(segments))
    return [counts[label] / total for label in MOOD_DISTRIBUTION_LABELS]


def mood_share_for_label(track: Track, emotion_label: str) -> float:
    """O(1) mood mix share when ``track.mood_distribution`` is populated."""
    label = emotion_label.strip().lower()
    if label not in _PAD_MOOD_SET:
        return 0.0
    idx = MOOD_DISTRIBUTION_LABELS.index(label)
    if len(track.mood_distribution) == MOOD_DISTRIBUTION_SIZE:
        return float(track.mood_distribution[idx])
    return compute_mood_distribution(track.segments)[idx]


def track_has_dominant_mood_share(track: Track, emotion_label: str, *, minimum: float = 0.5) -> bool:
    return mood_share_for_label(track, emotion_label) >= minimum


def dominant_mood(mood_distribution: list[float]) -> str:
    """Mood label with the highest share (ties → earliest in axis order)."""
    if len(mood_distribution) != MOOD_DISTRIBUTION_SIZE:
        raise ValueError(f"expected {MOOD_DISTRIBUTION_SIZE} mood shares")
    best_idx = max(range(MOOD_DISTRIBUTION_SIZE), key=lambda i: mood_distribution[i])
    return MOOD_DISTRIBUTION_LABELS[best_idx]
