from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from analyzer.segment_build import MossSegmentDraft


class SegmentAnalyzer(ABC):
    name: str = "base"

    @abstractmethod
    def analyze(self, audio_path: Path, duration_sec: float) -> list[MossSegmentDraft]:
        raise NotImplementedError
