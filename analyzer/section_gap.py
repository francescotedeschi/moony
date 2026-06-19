"""Ensure MOSS section drafts cover the full track duration."""

from __future__ import annotations

from analyzer.segment_build import MossSegmentDraft


def fill_coverage_gaps(
    drafts: list[MossSegmentDraft],
    duration_sec: float,
    *,
    epsilon: float = 0.25,
) -> list[MossSegmentDraft]:
    end_total = max(float(duration_sec), 1.0)
    if not drafts:
        return [
            MossSegmentDraft(
                start_sec=0.0,
                end_sec=round(end_total, 3),
                structure_label="full",
                description="",
            )
        ]

    ordered = sorted(drafts, key=lambda d: d.start_sec)
    out: list[MossSegmentDraft] = []
    cursor = 0.0

    for draft in ordered:
        start = max(0.0, float(draft.start_sec))
        end = min(end_total, max(float(draft.end_sec), start + epsilon))

        if start > cursor + epsilon:
            gap_label = "intro" if cursor < epsilon else "section"
            out.append(
                MossSegmentDraft(
                    start_sec=round(cursor, 3),
                    end_sec=round(start, 3),
                    structure_label=gap_label,
                    description="",
                )
            )

        clipped_start = max(start, cursor)
        if end > clipped_start + epsilon:
            out.append(
                MossSegmentDraft(
                    start_sec=round(clipped_start, 3),
                    end_sec=round(end, 3),
                    structure_label=draft.structure_label or "section",
                    description=draft.description,
                )
            )
            cursor = end

    if cursor < end_total - epsilon:
        out.append(
            MossSegmentDraft(
                start_sec=round(cursor, 3),
                end_sec=round(end_total, 3),
                structure_label="outro",
                description="",
            )
        )

    return out or [
        MossSegmentDraft(
            start_sec=0.0,
            end_sec=round(end_total, 3),
            structure_label="full",
            description="",
        )
    ]
