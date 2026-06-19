"""Map Cyanite V7 analysis onto V17 catalog sections."""

from __future__ import annotations

from dataclasses import dataclass

from analyzer.cyanite import CyaniteSegmentSlice, CyaniteTrackAnalysis
from analyzer.models import CatalogSection, CatalogV17Track, CyaniteStub
from analyzer.segment_emotion.base import emotion_label_for_pad_name, va_for_emotion_label

CYANITE_MOOD_TO_PAD: dict[str, str] = {
    "aggressive": "Tension",
    "calm": "Calm",
    "chilled": "Calm",
    "dark": "Tension",
    "energetic": "Energy",
    "epic": "Energy",
    "happy": "Joy",
    "romantic": "Joy",
    "sad": "Sad",
    "scary": "Tension",
    "sexy": "Joy",
    "ethereal": "Calm",
    "uplifting": "Joy",
}

CYANITE_VA_SOURCE = "cyanite_segments"
CYANITE_EMOTION_SOURCE = "cyanite"


@dataclass(frozen=True)
class SectionCyaniteMood:
    emotion_label: str
    valence: float
    arousal: float
    mood_tag: str
    mood_score: float
    mood_scores: dict[str, float]


def _overlap_sec(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _dominant_mood_tag(mood_scores: dict[str, float]) -> tuple[str, float]:
    if not mood_scores:
        return "", 0.0
    tag, score = max(mood_scores.items(), key=lambda item: item[1])
    return tag, float(score)


def _section_midpoint(start_sec: float, end_sec: float) -> float:
    return (float(start_sec) + float(end_sec)) / 2.0


def _nearest_segment(
    slices: list[CyaniteSegmentSlice],
    start_sec: float,
    end_sec: float,
) -> CyaniteSegmentSlice | None:
    if not slices:
        return None
    mid = _section_midpoint(start_sec, end_sec)
    return min(
        slices,
        key=lambda segment: abs(_section_midpoint(segment.start_sec, segment.end_sec) - mid),
    )


def _aggregate_mood_scores(
    slices: list[CyaniteSegmentSlice],
    start_sec: float,
    end_sec: float,
) -> dict[str, float]:
    totals: dict[str, float] = {}
    weights = 0.0
    for segment in slices:
        weight = _overlap_sec(start_sec, end_sec, segment.start_sec, segment.end_sec)
        if weight <= 0:
            continue
        weights += weight
        for tag, score in segment.mood_scores.items():
            totals[tag] = totals.get(tag, 0.0) + score * weight
    if weights <= 0:
        nearest = _nearest_segment(slices, start_sec, end_sec)
        if nearest is None:
            return {}
        return dict(nearest.mood_scores)
    return {tag: value / weights for tag, value in totals.items()}


def _aggregate_valence_arousal(
    slices: list[CyaniteSegmentSlice],
    start_sec: float,
    end_sec: float,
) -> tuple[float, float]:
    valence_total = 0.0
    arousal_total = 0.0
    weights = 0.0
    for segment in slices:
        weight = _overlap_sec(start_sec, end_sec, segment.start_sec, segment.end_sec)
        if weight <= 0:
            continue
        weights += weight
        valence_total += segment.valence * weight
        arousal_total += segment.arousal * weight
    if weights <= 0:
        nearest = _nearest_segment(slices, start_sec, end_sec)
        if nearest is None:
            return 0.0, 0.0
        return float(nearest.valence), float(nearest.arousal)
    return valence_total / weights, arousal_total / weights


def build_energy_curve(
    segments: list[CyaniteSegmentSlice],
) -> tuple[list[float], list[float]]:
    """Track-level energy curve from Cyanite mood.energetic segment scores."""
    timestamps = [round(segment.start_sec, 3) for segment in segments]
    energy = [round(float(segment.mood_scores.get("energetic", 0.0)), 4) for segment in segments]
    return timestamps, energy


def mood_for_section(
    analysis: CyaniteTrackAnalysis,
    start_sec: float,
    end_sec: float,
) -> SectionCyaniteMood:
    mood_scores = _aggregate_mood_scores(analysis.segments, start_sec, end_sec)
    valence, arousal = _aggregate_valence_arousal(analysis.segments, start_sec, end_sec)
    mood_tag, mood_score = _dominant_mood_tag(mood_scores)

    pad_name = CYANITE_MOOD_TO_PAD.get(mood_tag, "Neutral")
    emotion_label = emotion_label_for_pad_name(pad_name)
    if mood_tag and emotion_label == "neutral" and (valence or arousal):
        emotion_label = _emotion_from_va(valence, arousal)
    elif not mood_tag and (valence or arousal):
        emotion_label = _emotion_from_va(valence, arousal)

    return SectionCyaniteMood(
        emotion_label=emotion_label,
        valence=round(valence, 4),
        arousal=round(arousal, 4),
        mood_tag=mood_tag,
        mood_score=round(mood_score, 4),
        mood_scores={tag: round(score, 4) for tag, score in sorted(mood_scores.items())},
    )


def _emotion_from_va(valence: float, arousal: float) -> str:
    best = "neutral"
    best_dist = float("inf")
    for label in ("calm", "joy", "energy", "tension", "sad", "neutral"):
        v, a = va_for_emotion_label(label)
        dist = (valence - v) ** 2 + (arousal - a) ** 2
        if dist < best_dist:
            best_dist = dist
            best = label
    return best


def apply_cyanite_to_sections(
    sections: list[CatalogSection],
    analysis: CyaniteTrackAnalysis,
) -> list[CatalogSection]:
    if analysis.status != "done" or not analysis.segments:
        return sections

    enriched: list[CatalogSection] = []
    for section in sections:
        mood = mood_for_section(analysis, section.start_sec, section.end_sec)
        enriched.append(
            section.model_copy(
                update={
                    "cyanite_mood_tag": mood.mood_tag,
                    "cyanite_mood_score": mood.mood_score,
                    "cyanite_mood_scores": mood.mood_scores,
                    "cyanite_valence": mood.valence,
                    "cyanite_arousal": mood.arousal,
                }
            )
        )
    return enriched


def cyanite_stub_from_analysis(
    track_id: str,
    analysis: CyaniteTrackAnalysis,
) -> CyaniteStub:
    timestamps, energy = build_energy_curve(analysis.segments)
    return CyaniteStub(
        library_track_id=analysis.library_track_id,
        status=analysis.status,
        segment_timestamps_sec=timestamps,
        energy_curve=energy,
        error_message=analysis.error_message,
    )


def enrich_track_with_cyanite(
    track: CatalogV17Track,
    analysis: CyaniteTrackAnalysis,
) -> CatalogV17Track:
    sections = apply_cyanite_to_sections(track.sections, analysis)
    cyanite = cyanite_stub_from_analysis(track.id, analysis)
    return track.model_copy(update={"sections": sections, "cyanite": cyanite})
