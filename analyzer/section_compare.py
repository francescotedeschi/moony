"""Compare section divisions from lyrics-LLM vs MOSS audio-only."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from analyzer.segment_build import MossSegmentDraft


def format_mmss(sec: float) -> str:
    total = max(0, int(sec))
    mm, ss = divmod(total, 60)
    return f"{mm:02d}:{ss:02d}"


def normalize_structure_label(label: str) -> str:
    raw = (label or "section").strip().lower().replace("_", "-")
    aliases = {
        "prechorus": "pre-chorus",
        "pre-chorus": "pre-chorus",
        "hook": "chorus",
    }
    return aliases.get(raw, raw or "section")


def section_to_dict(section: MossSegmentDraft) -> dict[str, Any]:
    return {
        "start_sec": round(float(section.start_sec), 3),
        "end_sec": round(float(section.end_sec), 3),
        "structure_label": section.structure_label or "section",
        "description": section.description or "",
    }


def extract_internal_boundaries(sections: list[MossSegmentDraft], duration_sec: float) -> list[float]:
    eps = 0.25
    end_total = max(float(duration_sec), 1.0)
    points: set[float] = set()
    for section in sections:
        start = float(section.start_sec)
        end = float(section.end_sec)
        if start > eps:
            points.add(round(start, 1))
        if end < end_total - eps:
            points.add(round(end, 1))
    return sorted(points)


def segment_iou(a: MossSegmentDraft, b: MossSegmentDraft) -> float:
    start = max(float(a.start_sec), float(b.start_sec))
    end = min(float(a.end_sec), float(b.end_sec))
    overlap = max(0.0, end - start)
    if overlap <= 0:
        return 0.0
    union = max(float(a.end_sec), float(b.end_sec)) - min(float(a.start_sec), float(b.start_sec))
    return overlap / union if union > 0 else 0.0


@dataclass(frozen=True)
class SectionPairMatch:
    lyrics_index: int
    moss_index: int
    iou: float
    label_match: bool
    lyrics_label: str
    moss_label: str
    lyrics_range: str
    moss_range: str


@dataclass(frozen=True)
class SectionComparison:
    lyrics_section_count: int
    moss_section_count: int
    boundary_tolerance_sec: float
    lyrics_boundaries: list[float]
    moss_boundaries: list[float]
    boundary_matches: int
    boundary_match_rate: float
    mean_boundary_distance_sec: float | None
    label_agreement_rate: float
    pair_matches: tuple[SectionPairMatch, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pair_matches"] = [asdict(p) for p in self.pair_matches]
        return payload


def compare_sections(
    lyrics_sections: list[MossSegmentDraft],
    moss_sections: list[MossSegmentDraft],
    duration_sec: float,
    *,
    boundary_tolerance_sec: float = 5.0,
) -> SectionComparison:
    lyrics_boundaries = extract_internal_boundaries(lyrics_sections, duration_sec)
    moss_boundaries = extract_internal_boundaries(moss_sections, duration_sec)

    matched = 0
    distances: list[float] = []
    for point in lyrics_boundaries:
        if not moss_boundaries:
            continue
        nearest = min(abs(point - other) for other in moss_boundaries)
        if nearest <= boundary_tolerance_sec:
            matched += 1
            distances.append(nearest)

    denom = max(len(lyrics_boundaries), 1)
    boundary_match_rate = matched / denom
    mean_distance = round(sum(distances) / len(distances), 2) if distances else None

    pairs = _best_section_pairs(lyrics_sections, moss_sections)
    label_agreement = (
        sum(1 for pair in pairs if pair.label_match) / len(pairs) if pairs else 0.0
    )

    return SectionComparison(
        lyrics_section_count=len(lyrics_sections),
        moss_section_count=len(moss_sections),
        boundary_tolerance_sec=boundary_tolerance_sec,
        lyrics_boundaries=lyrics_boundaries,
        moss_boundaries=moss_boundaries,
        boundary_matches=matched,
        boundary_match_rate=round(boundary_match_rate, 3),
        mean_boundary_distance_sec=mean_distance,
        label_agreement_rate=round(label_agreement, 3),
        pair_matches=tuple(pairs),
    )


def _best_section_pairs(
    lyrics_sections: list[MossSegmentDraft],
    moss_sections: list[MossSegmentDraft],
    *,
    min_iou: float = 0.1,
) -> list[SectionPairMatch]:
    candidates: list[tuple[float, int, int, bool]] = []
    for li, left in enumerate(lyrics_sections):
        for mi, right in enumerate(moss_sections):
            iou = segment_iou(left, right)
            if iou >= min_iou:
                label_match = normalize_structure_label(left.structure_label) == normalize_structure_label(
                    right.structure_label
                )
                candidates.append((iou, li, mi, label_match))

    candidates.sort(reverse=True)
    used_lyrics: set[int] = set()
    used_moss: set[int] = set()
    pairs: list[SectionPairMatch] = []

    for iou, li, mi, label_match in candidates:
        if li in used_lyrics or mi in used_moss:
            continue
        used_lyrics.add(li)
        used_moss.add(mi)
        left = lyrics_sections[li]
        right = moss_sections[mi]
        pairs.append(
            SectionPairMatch(
                lyrics_index=li,
                moss_index=mi,
                iou=round(iou, 3),
                label_match=label_match,
                lyrics_label=left.structure_label or "section",
                moss_label=right.structure_label or "section",
                lyrics_range=f"{format_mmss(left.start_sec)}-{format_mmss(left.end_sec)}",
                moss_range=f"{format_mmss(right.start_sec)}-{format_mmss(right.end_sec)}",
            )
        )

    pairs.sort(key=lambda item: item.lyrics_index)
    return pairs


def build_timeline_markers(
    lyrics_sections: list[MossSegmentDraft],
    moss_sections: list[MossSegmentDraft],
    duration_sec: float,
    *,
    step_sec: float = 5.0,
) -> list[dict[str, Any]]:
    end_total = max(float(duration_sec), 1.0)
    rows: list[dict[str, Any]] = []
    t = 0.0
    while t <= end_total + 0.01:
        lyrics_label = _label_at_time(lyrics_sections, t)
        moss_label = _label_at_time(moss_sections, t)
        rows.append(
            {
                "time_sec": round(t, 1),
                "time": format_mmss(t),
                "lyrics_label": lyrics_label,
                "moss_label": moss_label,
                "match": normalize_structure_label(lyrics_label) == normalize_structure_label(moss_label),
            }
        )
        t += step_sec
    return rows


def _label_at_time(sections: list[MossSegmentDraft], time_sec: float) -> str:
    for section in sections:
        if float(section.start_sec) <= time_sec < float(section.end_sec):
            return section.structure_label or "section"
    return ""


def format_side_by_side_report(
    *,
    artist: str,
    title: str,
    duration_sec: float,
    lyrics_sections: list[MossSegmentDraft],
    moss_sections: list[MossSegmentDraft],
    comparison: SectionComparison,
) -> str:
    lines: list[str] = []
    width = 78
    lines.append("=" * width)
    lines.append(f"{artist} - {title}  ({format_mmss(duration_sec)})")
    lines.append("=" * width)
    lines.append("")
    lines.append("LYRICS-LLM (text)                    MOSS (audio-only)")
    lines.append("-" * width)
    max_rows = max(len(lyrics_sections), len(moss_sections))
    for idx in range(max_rows):
        left = lyrics_sections[idx] if idx < len(lyrics_sections) else None
        right = moss_sections[idx] if idx < len(moss_sections) else None
        left_txt = (
            f"[{format_mmss(left.start_sec)}-{format_mmss(left.end_sec)}] {left.structure_label}"
            if left
            else ""
        )
        right_txt = (
            f"[{format_mmss(right.start_sec)}-{format_mmss(right.end_sec)}] {right.structure_label}"
            if right
            else ""
        )
        lines.append(f"{left_txt:<36} | {right_txt}")

    lines.append("")
    lines.append("METRICHE")
    lines.append("-" * width)
    lines.append(
        f"  sezioni: lyrics={comparison.lyrics_section_count}  moss={comparison.moss_section_count}"
    )
    lines.append(
        f"  confini lyrics: {[format_mmss(b) for b in comparison.lyrics_boundaries]}"
    )
    lines.append(
        f"  confini moss:   {[format_mmss(b) for b in comparison.moss_boundaries]}"
    )
    lines.append(
        f"  confini allineati (tol {comparison.boundary_tolerance_sec}s): "
        f"{comparison.boundary_matches}/{max(len(comparison.lyrics_boundaries), 1)} "
        f"({comparison.boundary_match_rate:.0%})"
    )
    if comparison.mean_boundary_distance_sec is not None:
        lines.append(f"  distanza media confini: {comparison.mean_boundary_distance_sec}s")
    lines.append(f"  accordo label (coppie IoU): {comparison.label_agreement_rate:.0%}")

    if comparison.pair_matches:
        lines.append("")
        lines.append("COPPIE (lyrics -> moss, per IoU)")
        lines.append("-" * width)
        for pair in comparison.pair_matches:
            mark = "OK" if pair.label_match else "DIFF"
            lines.append(
                f"  [{mark}] IoU={pair.iou:.2f}  "
                f"{pair.lyrics_label} {pair.lyrics_range}  <->  "
                f"{pair.moss_label} {pair.moss_range}"
            )

    return "\n".join(lines)