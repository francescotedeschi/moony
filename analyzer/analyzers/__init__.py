from pathlib import Path

from analyzer.analyzers.base import SegmentAnalyzer
from analyzer.analyzers.moss import MossMusicAnalyzer
from analyzer.analyzers.moss_config import MossInferenceConfig
from analyzer.analyzers.moss_lyrics import MossLyricsAnalyzer, StubLyricsAnalyzer
from analyzer.analyzers.stub import StubAnalyzer

__all__ = [
    "SegmentAnalyzer",
    "StubAnalyzer",
    "MossMusicAnalyzer",
    "MossLyricsAnalyzer",
    "StubLyricsAnalyzer",
    "MossInferenceConfig",
    "get_analyzer",
    "get_lyrics_analyzer",
]


def _moss_config_from_settings(settings) -> MossInferenceConfig:
    repo = settings.moss_music_repo or Path(".")
    model = settings.moss_model_path or Path(".")
    return MossInferenceConfig(
        repo=repo,
        model_path=model,
        python=settings.moss_python,
        cuda_device=settings.moss_cuda_device,
        window_sec=settings.segment_window_sec,
        backend=settings.moss_backend,
        sglang_base_url=settings.moss_sglang_base_url,
        sglang_api_key=settings.moss_sglang_api_key,
        max_new_tokens=settings.moss_max_new_tokens,
        temperature=settings.moss_temperature,
        top_p=settings.moss_top_p,
        top_k=settings.moss_top_k,
        request_timeout_sec=settings.moss_request_timeout_sec,
        segment_caption=settings.moss_segment_caption,
        persistent=settings.moss_persistent,
    )


def get_analyzer(settings) -> SegmentAnalyzer:
    if settings.moss_enabled():
        return MossMusicAnalyzer(_moss_config_from_settings(settings))
    return StubAnalyzer(window_sec=settings.segment_window_sec)


def get_lyrics_analyzer(settings) -> MossLyricsAnalyzer | StubLyricsAnalyzer:
    if settings.moss_enabled():
        return MossLyricsAnalyzer(_moss_config_from_settings(settings))
    return StubLyricsAnalyzer(window_sec=settings.segment_window_sec)
