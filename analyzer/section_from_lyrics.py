"""Derive song sections from synced lyrics using an LLM (text only, no audio)."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from analyzer.analyzers.moss_parse import parse_moss_structure
from analyzer.musixmatch import TimestampedLyrics
from analyzer.section_gap import fill_coverage_gaps
from analyzer.segment_build import MossSegmentDraft

SYSTEM_PROMPT = (
    "You are a music structure analyst. You segment songs using synced lyrics and timestamps only. "
    "Identify intro, verse, chorus, bridge, and outro from semantic themes and repeated lyric blocks. "
    "Never quote or transcribe lyrics in your output."
)


def _format_duration_mmss(duration_sec: float) -> str:
    total = max(0, int(duration_sec))
    mm, ss = divmod(total, 60)
    return f"{mm:02d}:{ss:02d}"


def _target_section_range(duration_sec: float) -> tuple[int, int] | None:
    """Suggest finer LLM segmentation for tracks longer than 3 minutes."""
    if duration_sec <= 180:
        return None
    low = max(8, int(duration_sec // 45))
    high = min(14, max(low + 2, int(duration_sec // 28)))
    return low, high


def build_lyrics_structure_prompt(
    lyrics: TimestampedLyrics,
    duration_sec: float,
    *,
    title: str = "",
    artist: str = "",
) -> str:
    parts: list[str] = []
    if artist or title:
        parts.append(f"Track: {artist} - {title}".strip(" -"))
    rules = [
        f"Duration: {_format_duration_mmss(duration_sec)}",
        "",
        "Segment this song into structural sections using ONLY the synced lyrics and timestamps below.",
        "Use semantic analysis: repeated blocks are likely chorus; unique narrative blocks are verses.",
        "Align section boundaries with lyric timestamps or natural gaps between lines.",
        "",
        "Output ONLY one line per section in this exact format:",
        "[MM:SS-MM:SS] intro: short structural note",
        "",
        "Example:",
        "[0:00-0:13] intro: instrumental opening before vocals",
        "[0:13-0:45] verse: narrative theme established",
        "",
        "Rules:",
        f"- Cover the full track duration (0:00 to {_format_duration_mmss(duration_sec)}).",
        "- Use lowercase labels: intro, verse, chorus, bridge, outro (or pre-chorus when obvious).",
        "- Do NOT quote or copy lyric text in descriptions.",
        "- Sections must be contiguous with no gaps or overlaps.",
    ]
    section_range = _target_section_range(duration_sec)
    if section_range is not None:
        lo, hi = section_range
        rules.extend(
            [
                f"- Long track ({_format_duration_mmss(duration_sec)}): use about {lo}-{hi} sections.",
                "- Split distinct verses and repeated choruses separately; do not collapse the whole song into fewer than 6 sections.",
            ]
        )
    rules.extend(
        [
            "",
            "Synced lyrics:",
            lyrics.format_for_prompt(),
        ]
    )
    parts.extend(rules)
    return "\n".join(parts)


@dataclass(frozen=True)
class LyricsLlmConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout_sec: float = 120.0
    temperature: float = 0.0

    @classmethod
    def from_env(cls) -> LyricsLlmConfig:
        api_key = os.getenv("LYRICS_LLM_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        return cls(
            api_key=api_key,
            base_url=os.getenv("LYRICS_LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
            model=os.getenv("LYRICS_LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            timeout_sec=float(os.getenv("LYRICS_LLM_TIMEOUT_SEC", "120")),
            temperature=float(os.getenv("LYRICS_LLM_TEMPERATURE", "0")),
        )


class LyricsLlmClient:
    """OpenAI-compatible chat completions client."""

    def __init__(self, config: LyricsLlmConfig) -> None:
        if not config.api_key:
            raise ValueError("LLM API key missing. Set OPENAI_API_KEY or LYRICS_LLM_API_KEY in .env")
        self._config = config
        self._http = httpx.Client(timeout=config.timeout_sec)

    def close(self) -> None:
        self._http.close()

    def complete(self, *, system: str, user: str) -> str:
        url = f"{self._config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._config.model,
            "temperature": self._config.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = self._http.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM response contained no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM response contained no text")
        return content.strip()


def section_from_lyrics(
    lyrics: TimestampedLyrics | None,
    duration_sec: float,
    *,
    title: str = "",
    artist: str = "",
    client: LyricsLlmClient | None = None,
    config: LyricsLlmConfig | None = None,
) -> list[MossSegmentDraft]:
    """
    Infer structural sections from timestamped lyrics via LLM (no audio).

    Returns segment drafts with intro/outro gap filling applied.
    """
    end_total = max(float(duration_sec), 1.0)
    if not lyrics or not lyrics.lines:
        return fill_coverage_gaps([], end_total)

    cfg = config or LyricsLlmConfig.from_env()
    owned_client = client is None
    llm = client or LyricsLlmClient(cfg)
    try:
        user_prompt = build_lyrics_structure_prompt(
            lyrics,
            end_total,
            title=title,
            artist=artist,
        )
        raw = llm.complete(system=SYSTEM_PROMPT, user=user_prompt)
        drafts = parse_moss_structure(raw, end_total)
        if not drafts:
            raise RuntimeError(
                "LLM output could not be parsed into sections. "
                f"Raw response starts with: {raw[:240]!r}"
            )
        return fill_coverage_gaps(drafts, end_total)
    finally:
        if owned_client:
            llm.close()
