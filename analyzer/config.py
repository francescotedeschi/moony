from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from analyzer.embeddings import DEFAULT_EMBEDDING_MODEL, STUB_EMBEDDING_MODEL, resolve_embedding_model

load_dotenv()


@dataclass(frozen=True)
class Settings:
    jamendo_client_id: str
    jamendo_tags: list[str]
    jamendo_sleep_sec: float
    max_tracks: int
    catalog_output: Path
    temp_audio_dir: Path
    moss_music_repo: Path | None
    moss_model_path: Path | None
    moss_python: str
    moss_cuda_device: int | None
    segment_window_sec: float
    emotion_fetch: bool
    candidates_per_emotion: int
    duration_min_sec: int
    duration_max_sec: int
    keep_downloaded_audio: bool
    embedding_model: str
    essentia_enabled: bool
    essentia_cache_dir: Path | None
    moss_backend: str
    moss_sglang_base_url: str
    moss_sglang_api_key: str
    moss_max_new_tokens: int
    moss_temperature: float
    moss_top_p: float
    moss_top_k: int
    moss_request_timeout_sec: float
    moss_segment_caption: str
    moss_persistent: bool
    source_catalog: Path | None
    local_build_limit: int
    musixmatch_api_key: str
    musixmatch_sleep_sec: float
    all_audio_dir: Path
    v17_structure_source: str
    cyanite_access_token: str
    cyanite_api_url: str
    cyanite_cache_dir: Path
    cyanite_sleep_sec: float
    cyanite_poll_interval_sec: float
    cyanite_poll_timeout_sec: float
    cyanite_release_library_slot: bool

    @classmethod
    def from_env(cls) -> Settings:
        tags_raw = os.getenv("JAMENDO_TAGS", "chill,electronic,ambient")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        repo = os.getenv("MOSS_MUSIC_REPO", "").strip()
        model = os.getenv("MOSS_MODEL_PATH", "").strip()
        cuda_raw = os.getenv("MOSS_CUDA_DEVICE", "").strip()
        cuda_device = int(cuda_raw) if cuda_raw != "" else None
        emotion_fetch = os.getenv("EMOTION_FETCH", "1").strip().lower() in ("1", "true", "yes")
        keep_audio = os.getenv("KEEP_DOWNLOADED_AUDIO", "1").strip().lower() in ("1", "true", "yes")
        essentia_enabled = os.getenv("ESSENTIA_ENABLED", "1").strip().lower() in ("1", "true", "yes")
        essentia_cache = os.getenv("ESSENTIA_CACHE_DIR", "").strip()
        embedding_model = resolve_embedding_model(
            os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL
        )
        moss_backend = os.getenv("MOSS_BACKEND", "transformers").strip().lower() or "transformers"
        moss_segment_caption = os.getenv("MOSS_SEGMENT_CAPTION", "all").strip().lower() or "all"
        moss_persistent = os.getenv("MOSS_PERSISTENT", "1").strip().lower() in ("1", "true", "yes")
        source_catalog_raw = os.getenv("SOURCE_CATALOG", "").strip()
        source_catalog = Path(source_catalog_raw) if source_catalog_raw else None
        musixmatch_key = os.getenv("MUSIXMATCH_API_KEY", "").strip()
        v17_structure = os.getenv("V17_STRUCTURE_SOURCE", "hybrid").strip().lower() or "hybrid"
        cyanite_token = os.getenv("CYANITE_ACCESS_TOKEN", "").strip()
        cyanite_cache = os.getenv("CYANITE_CACHE_DIR", "data/cyanite_cache").strip()
        return cls(
            jamendo_client_id=os.getenv("JAMENDO_CLIENT_ID", "").strip(),
            jamendo_tags=tags,
            jamendo_sleep_sec=float(os.getenv("JAMENDO_SLEEP_SEC", "0.3")),
            max_tracks=int(os.getenv("MAX_TRACKS", "120")),
            catalog_output=Path(os.getenv("CATALOG_OUTPUT", "data/catalog_v15.json")),
            temp_audio_dir=Path(os.getenv("TEMP_AUDIO_DIR", "data/temp_audio")),
            moss_music_repo=Path(repo) if repo else None,
            moss_model_path=Path(model) if model else None,
            moss_python=os.getenv("MOSS_PYTHON", "").strip() or "python",
            moss_cuda_device=cuda_device,
            segment_window_sec=float(os.getenv("SEGMENT_WINDOW_SEC", "15")),
            emotion_fetch=emotion_fetch,
            candidates_per_emotion=int(os.getenv("CANDIDATES_PER_EMOTION", "15")),
            duration_min_sec=int(os.getenv("DURATION_MIN_SEC", "90")),
            duration_max_sec=int(os.getenv("DURATION_MAX_SEC", "360")),
            keep_downloaded_audio=keep_audio,
            embedding_model=embedding_model,
            essentia_enabled=essentia_enabled,
            essentia_cache_dir=Path(essentia_cache) if essentia_cache else None,
            moss_backend=moss_backend,
            moss_sglang_base_url=os.getenv("MOSS_SGLANG_BASE_URL", "http://127.0.0.1:30000").strip(),
            moss_sglang_api_key=os.getenv("MOSS_SGLANG_API_KEY", "").strip(),
            moss_max_new_tokens=int(os.getenv("MOSS_MAX_NEW_TOKENS", "1024")),
            moss_temperature=float(os.getenv("MOSS_TEMPERATURE", "0.0")),
            moss_top_p=float(os.getenv("MOSS_TOP_P", "1.0")),
            moss_top_k=int(os.getenv("MOSS_TOP_K", "50")),
            moss_request_timeout_sec=float(os.getenv("MOSS_REQUEST_TIMEOUT_SEC", "600")),
            moss_segment_caption=moss_segment_caption,
            moss_persistent=moss_persistent,
            source_catalog=source_catalog,
            local_build_limit=int(os.getenv("LOCAL_BUILD_LIMIT", "30")),
            musixmatch_api_key=musixmatch_key,
            musixmatch_sleep_sec=float(os.getenv("MUSIXMATCH_SLEEP_SEC", "0.2")),
            all_audio_dir=Path(os.getenv("ALL_AUDIO_DIR", "data/all_audio")),
            v17_structure_source=v17_structure,
            cyanite_access_token=cyanite_token,
            cyanite_api_url=os.getenv("CYANITE_API_URL", "https://api.cyanite.ai/graphql").strip(),
            cyanite_cache_dir=Path(cyanite_cache),
            cyanite_sleep_sec=float(os.getenv("CYANITE_SLEEP_SEC", "0.3")),
            cyanite_poll_interval_sec=float(os.getenv("CYANITE_POLL_INTERVAL_SEC", "5")),
            cyanite_poll_timeout_sec=float(os.getenv("CYANITE_POLL_TIMEOUT_SEC", "900")),
            cyanite_release_library_slot=os.getenv("CYANITE_RELEASE_LIBRARY_SLOT", "1").strip().lower()
            in ("1", "true", "yes"),
        )

    def moss_enabled(self) -> bool:
        """True when MOSS analyzer should run (SGLang server or local Transformers weights)."""
        if self.moss_backend == "sglang":
            return True
        return self.moss_music_repo is not None and self.moss_model_path is not None

    def validate_for_v17_build(self) -> None:
        if not self.all_audio_dir.is_dir():
            raise ValueError(f"ALL_AUDIO_DIR not found: {self.all_audio_dir}")
        if self.v17_structure_source not in ("moss", "lyrics-llm", "hybrid"):
            raise ValueError(
                "V17_STRUCTURE_SOURCE must be 'moss', 'lyrics-llm', or 'hybrid' "
                f"(got {self.v17_structure_source!r})"
            )
        if self.v17_structure_source in ("lyrics-llm", "hybrid"):
            from analyzer.section_from_lyrics import LyricsLlmConfig

            if not LyricsLlmConfig.from_env().api_key:
                raise ValueError(
                    f"V17_STRUCTURE_SOURCE={self.v17_structure_source} requires "
                    "OPENAI_API_KEY or LYRICS_LLM_API_KEY in .env"
                )
        if not self.moss_enabled():
            raise ValueError(
                "MOSS not configured for v1.7 build. Set MOSS_BACKEND=sglang (+ MOSS_SGLANG_BASE_URL) "
                "or MOSS_MUSIC_REPO + MOSS_MODEL_PATH for Transformers."
            )

    def validate_for_cyanite(self) -> None:
        if not self.cyanite_access_token:
            raise ValueError(
                "CYANITE_ACCESS_TOKEN is required. Create an integration at "
                "https://app.cyanite.ai/ (Settings → Integrations) and copy the access token."
            )
        if not self.all_audio_dir.is_dir():
            raise ValueError(f"ALL_AUDIO_DIR not found: {self.all_audio_dir}")
        self.cyanite_cache_dir.mkdir(parents=True, exist_ok=True)
