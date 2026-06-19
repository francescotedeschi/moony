"""MOSS-Music analyzer with Musixmatch synced lyrics in prompts (v1.7)."""

from __future__ import annotations

from pathlib import Path

from analyzer.analyzers.moss import (
    MossMusicAnalyzer,
    _caption_from_response,
    _fallback_window_segments,
)
from analyzer.analyzers.moss_audio import write_segment_clip
from analyzer.analyzers.moss_parse import parse_moss_structure
from analyzer.analyzers.moss_prompts import (
    CATALOG_CAPTION_PROMPT,
    CATALOG_STRUCTURE_PROMPT,
    SEGMENT_CAPTION_MISSING,
    SEGMENT_CAPTION_OFF,
    build_caption_prompt_with_lyrics,
    build_structure_prompt_with_lyrics,
)
from analyzer.musixmatch import TimestampedLyrics
from analyzer.section_gap import fill_coverage_gaps
from analyzer.segment_build import MossSegmentDraft


class MossLyricsAnalyzer(MossMusicAnalyzer):
    name = "moss-music-lyrics"

    def analyze_with_lyrics(
        self,
        audio_path: Path,
        duration_sec: float,
        lyrics: TimestampedLyrics | None,
        *,
        structure_drafts: list[MossSegmentDraft] | None = None,
    ) -> list[MossSegmentDraft]:
        if structure_drafts is not None:
            drafts = list(structure_drafts)
        else:
            if lyrics:
                structure_prompt = build_structure_prompt_with_lyrics(lyrics.format_for_prompt())
            else:
                structure_prompt = CATALOG_STRUCTURE_PROMPT

            structure_text = self._infer(structure_prompt, audio_path)
            drafts = parse_moss_structure(structure_text, duration_sec)
            if not drafts:
                drafts = _fallback_window_segments(duration_sec, self.config.window_sec)

        drafts = fill_coverage_gaps(drafts, duration_sec)

        if self.config.segment_caption != SEGMENT_CAPTION_OFF:
            drafts = self._caption_sections_with_lyrics(audio_path, drafts, lyrics)

        return drafts

    def _caption_sections_with_lyrics(
        self,
        audio_path: Path,
        drafts: list[MossSegmentDraft],
        lyrics: TimestampedLyrics | None,
    ) -> list[MossSegmentDraft]:
        mode = self.config.segment_caption
        captioned: list[MossSegmentDraft] = []

        for draft in drafts:
            inline = draft.description.strip()
            if mode == SEGMENT_CAPTION_MISSING and inline:
                captioned.append(draft)
                continue

            if lyrics:
                section_lyrics = lyrics.format_for_prompt(
                    start_sec=draft.start_sec,
                    end_sec=draft.end_sec,
                )
                prompt = build_caption_prompt_with_lyrics(section_lyrics, draft.structure_label)
            else:
                prompt = CATALOG_CAPTION_PROMPT

            clip_path: Path | None = None
            try:
                clip_path = write_segment_clip(audio_path, draft.start_sec, draft.end_sec)
                text = self._infer(prompt, clip_path)
                description = _caption_from_response(text) or inline
            except Exception:
                description = inline
            finally:
                if clip_path is not None and clip_path.exists():
                    clip_path.unlink()

            if not description and draft.structure_label:
                description = f"{draft.structure_label} section"

            captioned.append(
                MossSegmentDraft(
                    start_sec=draft.start_sec,
                    end_sec=draft.end_sec,
                    structure_label=draft.structure_label,
                    description=description,
                )
            )

        return captioned


class StubLyricsAnalyzer:
    """Offline stub for v1.7 pipeline tests (no GPU)."""

    name = "stub-lyrics"

    def __init__(self, *, window_sec: float = 15.0) -> None:
        from analyzer.analyzers.stub import StubAnalyzer

        self._stub = StubAnalyzer(window_sec=window_sec)

    def close(self) -> None:
        return None

    def analyze_with_lyrics(
        self,
        audio_path: Path,
        duration_sec: float,
        lyrics: TimestampedLyrics | None,
    ) -> list[MossSegmentDraft]:
        drafts = self._stub.analyze(audio_path, duration_sec)
        return fill_coverage_gaps(drafts, duration_sec)
