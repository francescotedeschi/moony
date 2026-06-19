"""MOSS-Music analyzer configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from analyzer.analyzers.moss_prompts import (
    DEFAULT_MAX_NEW_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    DEFAULT_TOP_P,
    SEGMENT_CAPTION_ALL,
)


@dataclass(frozen=True)
class MossInferenceConfig:
    repo: Path
    model_path: Path
    python: str = "python"
    cuda_device: int | None = None
    window_sec: float = 15.0
    backend: str = "transformers"  # transformers | sglang
    sglang_base_url: str = "http://127.0.0.1:30000"
    sglang_api_key: str = ""
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    top_k: int = DEFAULT_TOP_K
    request_timeout_sec: float = 600.0
    segment_caption: str = SEGMENT_CAPTION_ALL
    persistent: bool = True
