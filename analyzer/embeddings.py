"""Build segment profile embeddings (text mood + description + numeric BPM)."""

from __future__ import annotations

import hashlib
import math
from typing import Iterable

import numpy as np

STUB_EMBEDDING_MODEL = "stub-hash-v1"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# Short alias kept for .env / CLI convenience.
MINILM_ALIAS = "all-MiniLM-L6-v2"
DEFAULT_TEXT_DIM = 384


def resolve_embedding_model(model: str) -> str:
    """Map legacy short names to Hugging Face repo ids."""
    normalized = (model or "").strip()
    if normalized in ("minilm", MINILM_ALIAS):
        return DEFAULT_EMBEDDING_MODEL
    return normalized or DEFAULT_EMBEDDING_MODEL


def format_segment_profile(
    *,
    emotion_label: str,
    structure_label: str,
    description: str,
    bpm: int,
    essentia_emotion_label: str = "",
    moss_emotion_label: str = "",
    emotion_source: str = "",
) -> str:
    parts = [f"mood: {emotion_label or 'neutral'}"]
    if essentia_emotion_label and essentia_emotion_label != emotion_label:
        parts.append(f"essentia: {essentia_emotion_label}")
    if moss_emotion_label and moss_emotion_label != emotion_label:
        parts.append(f"moss_mood: {moss_emotion_label}")
    if emotion_source:
        parts.append(f"source: {emotion_source}")
    parts.extend(
        [
            f"structure: {structure_label or 'section'}",
            f"bpm: {bpm}",
            f"description: {description.strip() or 'instrumental section'}",
        ]
    )
    return " | ".join(parts)


def normalize_bpm(bpm: int, *, min_bpm: int = 60, max_bpm: int = 180) -> float:
    if bpm <= 0:
        return 0.5
    clamped = float(np.clip(bpm, min_bpm, max_bpm))
    return (clamped - min_bpm) / float(max_bpm - min_bpm)


def build_description_embedding(
    *,
    description: str,
    model: str = STUB_EMBEDDING_MODEL,
) -> tuple[list[float], str]:
    """Return L2-normalized embedding of the MOSS section description only."""
    text = description.strip() or "instrumental section"

    if model in (STUB_EMBEDDING_MODEL, "stub"):
        vec = _stub_text_embedding(text, dim=DEFAULT_TEXT_DIM)
        model_id = STUB_EMBEDDING_MODEL
    else:
        resolved = resolve_embedding_model(model)
        vec = _sentence_transformer_embedding(text, resolved)
        model_id = resolved

    norm = float(np.linalg.norm(vec))
    if norm > 1e-9:
        vec = vec / norm
    return [round(float(x), 6) for x in vec.tolist()], model_id


def build_segment_embedding(
    *,
    emotion_label: str,
    structure_label: str,
    description: str,
    bpm: int,
    mood_confidence: float = 0.0,
    model: str = STUB_EMBEDDING_MODEL,
    essentia_emotion_label: str = "",
    moss_emotion_label: str = "",
    emotion_source: str = "",
) -> tuple[list[float], str]:
    """
    Return (embedding vector, embedding_model id).

    Final vector = L2-normalized concat(text_embedding, bpm_norm, mood_confidence).
    """
    profile = format_segment_profile(
        emotion_label=emotion_label,
        structure_label=structure_label,
        description=description,
        bpm=bpm,
        essentia_emotion_label=essentia_emotion_label,
        moss_emotion_label=moss_emotion_label,
        emotion_source=emotion_source,
    )
    bpm_norm = normalize_bpm(bpm)
    conf = float(np.clip(mood_confidence, 0.0, 1.0))

    if model == STUB_EMBEDDING_MODEL or model == "stub":
        text_vec = _stub_text_embedding(profile, dim=DEFAULT_TEXT_DIM)
        model_id = STUB_EMBEDDING_MODEL
    else:
        resolved = resolve_embedding_model(model)
        text_vec = _sentence_transformer_embedding(profile, resolved)
        model_id = resolved

    vec = np.concatenate(
        [np.asarray(text_vec, dtype=np.float32), np.asarray([bpm_norm, conf], dtype=np.float32)]
    )
    norm = float(np.linalg.norm(vec))
    if norm > 1e-9:
        vec = vec / norm
    return [round(float(x), 6) for x in vec.tolist()], model_id


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    va = np.asarray(list(a), dtype=np.float32)
    vb = np.asarray(list(b), dtype=np.float32)
    if va.size == 0 or vb.size == 0 or va.shape != vb.shape:
        return 0.0
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom <= 1e-9:
        return 0.0
    return float(np.dot(va, vb) / denom)


def _stub_text_embedding(text: str, *, dim: int = DEFAULT_TEXT_DIM) -> np.ndarray:
    """Deterministic pseudo-embedding for tests without sentence-transformers."""
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    rng = np.random.default_rng(int.from_bytes(seed[:8], "little"))
    vec = rng.standard_normal(dim).astype(np.float32)
    norm = float(np.linalg.norm(vec))
    if norm > 1e-9:
        vec /= norm
    return vec


_encoder_cache: dict[str, object] = {}


class _TransformersTextEncoder:
    """MiniLM (or any HF encoder) via transformers — avoids torchcodec on Windows."""

    def __init__(self, model_name: str) -> None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModel.from_pretrained(model_name)
        self._model.eval()
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)

    def encode(self, text: str) -> np.ndarray:
        import torch

        with torch.no_grad():
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )
            inputs = {key: value.to(self._device) for key, value in inputs.items()}
            outputs = self._model(**inputs)
            token_embeddings = outputs.last_hidden_state
            mask = inputs["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
            summed = torch.sum(token_embeddings * mask, dim=1)
            counts = torch.clamp(mask.sum(dim=1), min=1e-9)
            pooled = summed / counts
            vec = pooled.squeeze(0).cpu().numpy().astype(np.float32)

        norm = float(np.linalg.norm(vec))
        if norm > 1e-9:
            vec /= norm
        return vec


def _sentence_transformer_embedding(text: str, model_name: str) -> np.ndarray:
    model_name = resolve_embedding_model(model_name)
    if model_name not in _encoder_cache:
        _encoder_cache[model_name] = _TransformersTextEncoder(model_name)

    arr = _encoder_cache[model_name].encode(text)  # type: ignore[union-attr]
    if arr.size == 0:
        raise RuntimeError(f"Empty embedding from model {model_name!r}")
    return arr


def embedding_dim_for_model(model: str) -> int:
    if model in (STUB_EMBEDDING_MODEL, "stub"):
        return DEFAULT_TEXT_DIM
    if resolve_embedding_model(model) == DEFAULT_EMBEDDING_MODEL:
        return DEFAULT_TEXT_DIM
    return DEFAULT_TEXT_DIM
