"""Lightweight segment drafts from audio features (no GPU). For pipeline testing."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

from analyzer.analyzers.base import SegmentAnalyzer
from analyzer.segment_build import MossSegmentDraft

STRUCTURE_LABELS = ("intro", "verse", "chorus", "bridge", "outro")


class StubAnalyzer(SegmentAnalyzer):
    name = "stub"

    def __init__(self, *, window_sec: float = 15.0) -> None:
        self.window_sec = window_sec

    def analyze(self, audio_path: Path, duration_sec: float) -> list[MossSegmentDraft]:
        y, sr = librosa.load(str(audio_path), sr=22_050, mono=True)
        if duration_sec <= 0:
            duration_sec = float(librosa.get_duration(y=y, sr=sr))

        segments: list[MossSegmentDraft] = []
        t = 0.0
        idx = 0

        while t < duration_sec:
            end_t = min(t + self.window_sec, duration_sec)
            i0 = int(t * sr)
            i1 = int(end_t * sr)
            chunk = y[i0:i1]
            if chunk.size == 0:
                break

            rms = float(np.sqrt(np.mean(chunk**2) + 1e-9))
            centroid = float(np.mean(librosa.feature.spectral_centroid(y=chunk, sr=sr)))
            energy = "high" if rms > 0.08 else "low"
            brightness = "bright" if centroid > 2200 else "warm"
            structure = STRUCTURE_LABELS[idx % len(STRUCTURE_LABELS)]
            description = (
                f"{energy.capitalize()}-energy {structure} with {brightness} spectral tone"
            )

            segments.append(
                MossSegmentDraft(
                    start_sec=round(t, 2),
                    end_sec=round(end_t, 2),
                    structure_label=structure,
                    description=description,
                )
            )
            t = end_t
            idx += 1

        return segments or [
            MossSegmentDraft(
                start_sec=0.0,
                end_sec=round(max(duration_sec, 1.0), 2),
                structure_label="full",
                description="Full track section",
            )
        ]

    def analyze_structure_only(self, audio_path: Path, duration_sec: float) -> list[MossSegmentDraft]:
        return self.analyze(audio_path, duration_sec)
