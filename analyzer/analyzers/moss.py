"""MOSS-Music segment analysis using official prompts and parsers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import httpx

from analyzer.analyzers.base import SegmentAnalyzer
from analyzer.analyzers.moss_audio import write_segment_clip
from analyzer.analyzers.moss_config import MossInferenceConfig
from analyzer.analyzers.moss_infer_core import clean_model_text
from analyzer.analyzers.moss_parse import parse_moss_structure
from analyzer.analyzers.moss_persistent import MossPersistentSession
from analyzer.analyzers.moss_prompts import (
    CATALOG_CAPTION_PROMPT,
    CATALOG_STRUCTURE_PROMPT,
    SEGMENT_CAPTION_ALL,
    SEGMENT_CAPTION_MISSING,
    SEGMENT_CAPTION_OFF,
)
from analyzer.section_gap import fill_coverage_gaps
from analyzer.segment_build import MossSegmentDraft


class MossMusicAnalyzer(SegmentAnalyzer):
    name = "moss-music"

    def __init__(self, config: MossInferenceConfig) -> None:
        self.config = config
        self._runner = Path(__file__).resolve().parent / "moss_infer_runner.py"
        self._persistent: MossPersistentSession | None = None
        if config.backend == "transformers" and config.persistent:
            self._persistent = MossPersistentSession(config)

    def close(self) -> None:
        if self._persistent is not None:
            self._persistent.close()
            self._persistent = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def analyze(self, audio_path: Path, duration_sec: float) -> list[MossSegmentDraft]:
        # Pass 1 — full track: official structural segmentation prompt.
        structure_text = self._infer(CATALOG_STRUCTURE_PROMPT, audio_path)

        drafts = parse_moss_structure(structure_text, duration_sec)
        if not drafts:
            drafts = _fallback_window_segments(duration_sec, self.config.window_sec)

        # Pass 2 — per segment: official clip caption on cropped audio.
        if self.config.segment_caption != SEGMENT_CAPTION_OFF:
            drafts = self._caption_segments(audio_path, drafts)

        return drafts

    def analyze_structure_only(self, audio_path: Path, duration_sec: float) -> list[MossSegmentDraft]:
        """Audio-only structural segmentation (no lyrics, no per-section captions)."""
        structure_text = self._infer(CATALOG_STRUCTURE_PROMPT, audio_path)
        drafts = parse_moss_structure(structure_text, duration_sec)
        if not drafts:
            drafts = _fallback_window_segments(duration_sec, self.config.window_sec)
        return fill_coverage_gaps(drafts, duration_sec)

    def _caption_segments(
        self,
        audio_path: Path,
        drafts: list[MossSegmentDraft],
    ) -> list[MossSegmentDraft]:
        mode = self.config.segment_caption
        captioned: list[MossSegmentDraft] = []

        for draft in drafts:
            inline = draft.description.strip()
            if mode == SEGMENT_CAPTION_MISSING and inline:
                captioned.append(draft)
                continue

            clip_path: Path | None = None
            try:
                clip_path = write_segment_clip(audio_path, draft.start_sec, draft.end_sec)
                text = self._infer(CATALOG_CAPTION_PROMPT, clip_path)
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

    def _infer(self, prompt: str, audio_path: Path) -> str:
        if self.config.backend == "sglang":
            return self._run_sglang(prompt, audio_path)
        if self._persistent is not None:
            return self._persistent.infer(prompt, audio_path)
        return self._run_transformers(prompt, audio_path)

    def _run_transformers(self, prompt: str, audio_path: Path) -> str:
        cfg = self.config
        if not cfg.repo.is_dir():
            raise FileNotFoundError(f"MOSS_MUSIC_REPO not found: {cfg.repo}")
        if not cfg.model_path.is_dir():
            raise FileNotFoundError(f"MOSS_MODEL_PATH not found: {cfg.model_path}")

        cmd = [
            cfg.python,
            str(self._runner),
            "--repo",
            str(cfg.repo),
            "--model",
            str(cfg.model_path),
            "--audio",
            str(audio_path.resolve()),
            "--prompt",
            prompt,
            "--max-new-tokens",
            str(cfg.max_new_tokens),
            "--temperature",
            str(cfg.temperature),
            "--top-p",
            str(cfg.top_p),
            "--top-k",
            str(cfg.top_k),
        ]
        env = os.environ.copy()
        if cfg.cuda_device is not None:
            env["CUDA_VISIBLE_DEVICES"] = str(cfg.cuda_device)
        ffmpeg_bin = Path(r"C:\ffmpeg\bin")
        if ffmpeg_bin.is_dir():
            env["PATH"] = str(ffmpeg_bin) + os.pathsep + env.get("PATH", "")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        env.setdefault("TQDM_DISABLE", "1")
        env.setdefault("TRANSFORMERS_VERBOSITY", "error")
        src_root = Path(__file__).resolve().parents[2]
        env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cfg.repo),
            env=env,
            timeout=int(cfg.request_timeout_sec),
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"MOSS inference failed (code {proc.returncode}):\n{proc.stderr[-2000:]}"
            )
        return clean_model_text(proc.stdout) or clean_model_text(proc.stderr)

    def _run_sglang(self, prompt: str, audio_path: Path) -> str:
        """Official SGLang /generate API (moss_music_usage_guide.md)."""
        cfg = self.config
        base = cfg.sglang_base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if cfg.sglang_api_key.strip():
            headers["Authorization"] = f"Bearer {cfg.sglang_api_key.strip()}"

        payload = {
            "text": prompt,
            "audio_data": str(audio_path.resolve()),
            "sampling_params": {
                "max_new_tokens": cfg.max_new_tokens,
                "temperature": cfg.temperature,
                "top_p": cfg.top_p,
                "top_k": cfg.top_k,
            },
        }
        with httpx.Client(timeout=cfg.request_timeout_sec) as client:
            response = client.post(f"{base}/generate", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return _extract_sglang_text(data)


def _caption_from_response(text: str) -> str:
    """Normalize MOSS caption output for catalog segment description."""
    cleaned = text.strip()
    if not cleaned:
        return ""

    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    if not lines:
        return cleaned[:2000]

    import re

    labeled = [ln for ln in lines if re.match(r"^(Voice|Mood|Instruments|Lyrics topic):", ln, re.I)]
    if labeled:
        return "\n".join(labeled)[:2000]

    time_re = re.compile(r"\d{1,2}:\d{2}")
    prose = [ln for ln in lines if not time_re.search(ln) or len(ln) > 40]
    if prose:
        return "\n".join(prose)[:2000]
    return cleaned[:2000]


def _extract_sglang_text(payload: dict) -> str:
    if isinstance(payload.get("text"), str):
        return payload["text"].strip()
    if isinstance(payload.get("generated_text"), str):
        return payload["generated_text"].strip()

    choices = payload.get("choices") or []
    if choices and isinstance(choices[0], dict):
        first = choices[0]
        if isinstance(first.get("text"), str):
            return first["text"].strip()
        message = first.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()

    raise ValueError("SGLang response did not contain text output")


def _fallback_window_segments(duration_sec: float, window_sec: float) -> list[MossSegmentDraft]:
    """Fixed windows when MOSS structure output is not parseable."""
    end_total = max(duration_sec, 1.0)
    drafts: list[MossSegmentDraft] = []
    t = 0.0
    idx = 0
    labels = ("intro", "verse", "chorus", "bridge", "outro")
    while t < end_total:
        end_t = min(t + window_sec, end_total)
        drafts.append(
            MossSegmentDraft(
                start_sec=round(t, 3),
                end_sec=round(end_t, 3),
                structure_label=labels[idx % len(labels)],
                description="",
            )
        )
        t = end_t
        idx += 1
    return drafts or [
        MossSegmentDraft(start_sec=0.0, end_sec=round(end_total, 3), structure_label="full", description="")
    ]
