"""Hybrid sections: MOSS audio granularity + LLM lyrics labels/timestamps."""

from __future__ import annotations

from analyzer.section_compare import extract_internal_boundaries
from analyzer.section_gap import fill_coverage_gaps
from analyzer.segment_build import MossSegmentDraft


def is_moss_fallback_windows(
    sections: list[MossSegmentDraft],
    duration_sec: float,
    analyzer,
) -> bool:
    """True when MOSS structure looks like fixed-window fallback (unparseable output)."""
    window = getattr(getattr(analyzer, "config", None), "window_sec", None) or getattr(
        analyzer, "window_sec", 15.0
    )
    if len(sections) < 2:
        return True
    durations = [round(float(s.end_sec) - float(s.start_sec), 1) for s in sections[:-1]]
    if not durations:
        return True
    windowish = sum(1 for d in durations if abs(d - float(window)) <= 1.0)
    return windowish / len(durations) >= 0.8


def merge_lyrics_labels_with_moss_granularity(
    lyrics_sections: list[MossSegmentDraft],
    moss_sections: list[MossSegmentDraft],
    duration_sec: float,
    *,
    moss_is_fallback: bool,
    min_segment_sec: float = 1.0,
) -> list[MossSegmentDraft]:
    """
    Keep MOSS fine-grained cut points, assign labels/descriptions from LLM sections.

    If MOSS fell back to fixed windows, return the LLM division unchanged.
    """
    end_total = max(float(duration_sec), 1.0)
    if moss_is_fallback or not moss_sections:
        return list(lyrics_sections)
    if not lyrics_sections:
        return fill_coverage_gaps(moss_sections, end_total)

    boundary_points: set[float] = {0.0, round(end_total, 3)}
    for source in (lyrics_sections, moss_sections):
        for point in extract_internal_boundaries(source, end_total):
            boundary_points.add(round(float(point), 3))

    ordered = _collapse_boundaries(sorted(boundary_points))
    merged: list[MossSegmentDraft] = []
    for idx in range(len(ordered) - 1):
        start = ordered[idx]
        end = ordered[idx + 1]
        if end <= start + 0.05:
            continue
        parent = _best_lyrics_parent(start, end, lyrics_sections)
        merged.append(
            MossSegmentDraft(
                start_sec=round(start, 3),
                end_sec=round(end, 3),
                structure_label=parent.structure_label if parent else "section",
                description=parent.description if parent else "",
            )
        )

    merged = _finalize_hybrid_sections(merged, min_segment_sec=min_segment_sec)

    if not merged:
        return list(lyrics_sections)
    if _covers_full_track(merged, end_total):
        return merged
    return _finalize_hybrid_sections(
        fill_coverage_gaps(merged, end_total),
        min_segment_sec=min_segment_sec,
    )


def _collapse_boundaries(points: list[float], *, epsilon: float = 0.25) -> list[float]:
    if not points:
        return points
    out = [float(points[0])]
    for point in points[1:]:
        if float(point) - out[-1] > epsilon:
            out.append(float(point))
    if out[-1] != float(points[-1]):
        out.append(float(points[-1]))
    return out


def _covers_full_track(sections: list[MossSegmentDraft], duration_sec: float, *, epsilon: float = 0.25) -> bool:
    if not sections:
        return False
    ordered = sorted(sections, key=lambda s: s.start_sec)
    if float(ordered[0].start_sec) > epsilon:
        return False
    if abs(float(ordered[-1].end_sec) - duration_sec) > epsilon:
        return False
    cursor = float(ordered[0].end_sec)
    for section in ordered[1:]:
        if float(section.start_sec) - cursor > epsilon:
            return False
        cursor = float(section.end_sec)
    return True


_GENERIC_LABELS = frozenset({"section", "full", ""})


def _finalize_hybrid_sections(
    sections: list[MossSegmentDraft],
    *,
    min_segment_sec: float = 1.0,
) -> list[MossSegmentDraft]:
    """Merge sub-second / generic gap segments into neighbors."""
    if not sections:
        return sections

    normalized = list(sections)
    changed = True
    while changed and len(normalized) > 1:
        changed = False
        next_pass: list[MossSegmentDraft] = []
        for section in normalized:
            if not next_pass:
                next_pass.append(section)
                continue

            prev = next_pass[-1]
            prev_dur = float(prev.end_sec) - float(prev.start_sec)
            cur_dur = float(section.end_sec) - float(section.start_sec)
            prev_generic = (prev.structure_label or "").strip().lower() in _GENERIC_LABELS
            cur_generic = (section.structure_label or "").strip().lower() in _GENERIC_LABELS

            if cur_dur < min_segment_sec or cur_generic:
                next_pass[-1] = _join_segments(prev, section, prefer=prev if not prev_generic else section)
                changed = True
            elif prev_dur < min_segment_sec or prev_generic:
                next_pass[-1] = _join_segments(prev, section, prefer=section if not cur_generic else prev)
                changed = True
            else:
                next_pass.append(section)
        normalized = next_pass

    return normalized


def _join_segments(
    left: MossSegmentDraft,
    right: MossSegmentDraft,
    *,
    prefer: MossSegmentDraft,
) -> MossSegmentDraft:
    label = prefer.structure_label or left.structure_label or right.structure_label or "section"
    if (label or "").strip().lower() in _GENERIC_LABELS:
        for candidate in (left, right):
            cand = (candidate.structure_label or "").strip().lower()
            if cand and cand not in _GENERIC_LABELS:
                label = candidate.structure_label
                break
    description = prefer.description or left.description or right.description
    return MossSegmentDraft(
        start_sec=round(float(left.start_sec), 3),
        end_sec=round(float(right.end_sec), 3),
        structure_label=label,
        description=description,
    )


def _best_lyrics_parent(
    start: float,
    end: float,
    lyrics_sections: list[MossSegmentDraft],
) -> MossSegmentDraft | None:
    best: MossSegmentDraft | None = None
    best_overlap = 0.0
    for section in lyrics_sections:
        overlap_start = max(start, float(section.start_sec))
        overlap_end = min(end, float(section.end_sec))
        overlap = max(0.0, overlap_end - overlap_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best = section
    if best is not None:
        return best

    mid = (start + end) / 2.0
    for section in lyrics_sections:
        if float(section.start_sec) <= mid < float(section.end_sec):
            return section
    return lyrics_sections[-1] if lyrics_sections else None