"""MOSS section draft — boundaries + structure label + description (pre-catalog)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MossSegmentDraft:
    start_sec: float
    end_sec: float
    structure_label: str = ""
    description: str = ""
