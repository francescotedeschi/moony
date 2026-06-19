"""Assemble v1.7 catalog sections from MOSS drafts (description + embedding only)."""

from __future__ import annotations

from analyzer.embeddings import STUB_EMBEDDING_MODEL, build_description_embedding
from analyzer.models import CatalogSection
from analyzer.segment_build import MossSegmentDraft


def build_sections(
    drafts: list[MossSegmentDraft],
    *,
    embedding_model: str = STUB_EMBEDDING_MODEL,
) -> list[CatalogSection]:
    if not drafts:
        return []

    sections: list[CatalogSection] = []
    for draft in drafts:
        description = draft.description.strip()
        if not description and draft.structure_label:
            description = f"{draft.structure_label} section"

        embedding, model_id = build_description_embedding(
            description=description,
            model=embedding_model,
        )
        sections.append(
            CatalogSection(
                start_sec=round(float(draft.start_sec), 3),
                end_sec=round(float(draft.end_sec), 3),
                structure_label=draft.structure_label or "section",
                description=description,
                embedding_model=model_id,
                embedding=embedding,
            )
        )
    return sections
