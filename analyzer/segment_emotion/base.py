"""Shared types: audio path + MX/catalog segments → emotion per segment."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# Allineato a Moony frontend EMOTION_ZONES (+ neutral per fallback)
PAD_EMOTIONS: list[dict[str, Any]] = [
    {"name": "Calm", "emotion_label": "calm", "v": 0.0, "ar": -0.8},
    {"name": "Joy", "emotion_label": "joy", "v": 0.8, "ar": 0.6},
    {"name": "Energy", "emotion_label": "energy", "v": 0.2, "ar": 0.9},
    {"name": "Tension", "emotion_label": "tension", "v": -0.5, "ar": 0.7},
    {"name": "Sad", "emotion_label": "sad", "v": -0.7, "ar": -0.5},
    {"name": "Neutral", "emotion_label": "neutral", "v": 0.0, "ar": 0.0},
]

PAD_NAMES: tuple[str, ...] = tuple(e["name"] for e in PAD_EMOTIONS)
PAD_EMOTION_LABELS: tuple[str, ...] = tuple(e["emotion_label"] for e in PAD_EMOTIONS)

# 8 catalog fetch buckets → 5 Moony pad zones
CATALOG_EMOTION_TO_PAD: dict[str, str] = {
    "calm": "Calm",
    "melancholic": "Sad",
    "hopeful": "Joy",
    "energetic": "Energy",
    "tense": "Tension",
    "warm": "Joy",
    "dreamy": "Calm",
    "playful": "Joy",
}

# MTG-Jamendo moodtheme tags → Moony pad (subset; unmapped tags ignored)
JAMENDO_TAG_TO_PAD: dict[str, str] = {
    "happy": "Joy",
    "positive": "Joy",
    "upbeat": "Joy",
    "fun": "Joy",
    "funny": "Joy",
    "party": "Joy",
    "groovy": "Joy",
    "hopeful": "Joy",
    "inspiring": "Joy",
    "uplifting": "Joy",
    "summer": "Joy",
    "children": "Joy",
    "sad": "Sad",
    "melancholic": "Sad",
    "emotional": "Sad",
    "deep": "Sad",
    "ballad": "Sad",
    "drama": "Sad",
    "dramatic": "Sad",
    "calm": "Calm",
    "relaxing": "Calm",
    "meditative": "Calm",
    "soft": "Calm",
    "slow": "Calm",
    "background": "Calm",
    "soundscape": "Calm",
    "nature": "Calm",
    "dream": "Calm",
    "energetic": "Energy",
    "epic": "Energy",
    "powerful": "Energy",
    "fast": "Energy",
    "sport": "Energy",
    "motivational": "Energy",
    "action": "Energy",
    "adventure": "Energy",
    "game": "Energy",
    "trailer": "Energy",
    "dark": "Tension",
    "heavy": "Tension",
    "documentary": "Tension",
    "film": "Tension",
    "movie": "Tension",
}

VA_SOURCE_EMOTION_TABLE = "emotion_table"


@dataclass
class SegmentInput:
    start_sec: float
    end_sec: float
    structure_label: str = ""


@dataclass
class SegmentEmotionOutput:
    start_sec: float
    end_sec: float
    structure_label: str
    emotion_label: str
    pad_name: str
    v: float
    ar: float
    confidence: float
    method: str
    va_source: str = VA_SOURCE_EMOTION_TABLE
    scores: dict[str, float] = field(default_factory=dict)


def load_segment_waveform(
    audio_path: Path,
    start_sec: float,
    end_sec: float,
    *,
    sample_rate: int = 16_000,
    min_duration_sec: float = 3.0,
) -> np.ndarray:
    """Load mono float32 waveform for [start_sec, end_sec], pad if too short."""
    import librosa

    duration = max(0.0, end_sec - start_sec)
    if duration <= 0:
        duration = min_duration_sec

    y, _ = librosa.load(
        str(audio_path),
        sr=sample_rate,
        mono=True,
        offset=start_sec,
        duration=duration,
    )
    min_samples = int(min_duration_sec * sample_rate)
    if y.size < min_samples:
        pad = min_samples - y.size
        y = np.pad(y, (0, pad), mode="constant")
    return y.astype(np.float32)


def slice_segments_from_catalog_track(
    track: dict[str, Any],
    *,
    use_mx_structure: bool = True,
) -> list[SegmentInput]:
    """
    Build segment list from catalog JSON.

    use_mx_structure: if segments have structure_label (future v1.4), keep it;
    otherwise uses label field (may be intro/verse from old MOSS).
    """
    out: list[SegmentInput] = []
    for raw in track.get("segments") or []:
        start = float(raw.get("start_sec", raw.get("t_start", 0) / 1000.0))
        end = float(raw.get("end_sec", raw.get("t_end", 0) / 1000.0))
        if end <= start:
            continue
        structure = ""
        if use_mx_structure:
            structure = str(raw.get("structure_label") or raw.get("label") or "")
        else:
            structure = str(raw.get("label") or "")
        out.append(SegmentInput(start_sec=start, end_sec=end, structure_label=structure))
    return out


def va_for_pad_name(pad_name: str) -> tuple[float, float]:
    for e in PAD_EMOTIONS:
        if e["name"] == pad_name:
            return float(e["v"]), float(e["ar"])
    return 0.0, 0.0


def va_for_emotion_label(label: str) -> tuple[float, float]:
    for e in PAD_EMOTIONS:
        if e["emotion_label"] == label:
            return float(e["v"]), float(e["ar"])
    return 0.0, 0.0


def emotion_label_for_pad_name(pad_name: str) -> str:
    for e in PAD_EMOTIONS:
        if e["name"] == pad_name:
            return str(e["emotion_label"])
    return "neutral"


def pad_name_for_catalog_emotion(catalog_id: str) -> str:
    return CATALOG_EMOTION_TO_PAD.get(catalog_id.strip().lower(), "Neutral")


def aggregate_tag_probs_to_pad(
    tag_probs: dict[str, float],
    *,
    neutral_threshold: float = 0.15,
) -> tuple[str, str, float, dict[str, float]]:
    """
    Aggregate Jamendo tag probabilities into pad scores.

    Returns (pad_name, emotion_label, confidence, pad_scores).
    """
    pad_scores = {e["name"]: 0.0 for e in PAD_EMOTIONS if e["name"] != "Neutral"}
    for tag, prob in tag_probs.items():
        pad = JAMENDO_TAG_TO_PAD.get(tag.lower())
        if pad:
            pad_scores[pad] = pad_scores.get(pad, 0.0) + float(prob)

    if not pad_scores or max(pad_scores.values()) < neutral_threshold:
        return "Neutral", "neutral", max(pad_scores.values(), default=0.0), pad_scores

    best_pad = max(pad_scores, key=pad_scores.get)
    total = sum(pad_scores.values()) or 1.0
    confidence = pad_scores[best_pad] / total
    emotion_label = emotion_label_for_pad_name(best_pad)
    return best_pad, emotion_label, confidence, pad_scores


def segment_outputs_to_emotion_segments(outputs: list[SegmentEmotionOutput]):
    """Convert SegmentEmotionOutput list to catalog CatalogSegment models (legacy helper)."""
    from analyzer.models import CatalogSegment

    segments: list[CatalogSegment] = []
    for out in outputs:
        segments.append(
            CatalogSegment(
                start_sec=out.start_sec,
                end_sec=out.end_sec,
                structure_label=out.structure_label,
                emotion_label=out.emotion_label,
                description="",
                emotion_method=out.method,
                emotion_confidence=out.confidence,
                embedding_model="",
                embedding=[],
            )
        )
    return segments
