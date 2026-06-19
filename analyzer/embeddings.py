"""Text embeddings for MOSS section descriptions (V17)."""

from __future__ import annotations

import hashlib

import numpy as np

STUB_EMBEDDING_MODEL = "stub-hash-v1"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MINILM_ALIAS = "all-MiniLM-L6-v2"
DEFAULT_TEXT_DIM = 384


def resolve_embedding_model(model: str) -> str:
    normalized = (model or "").strip()
    if normalized in ("minilm", MINILM_ALIAS):
        return DEFAULT_EMBEDDING_MODEL
    return normalized or DEFAULT_EMBEDDING_MODEL


def build_description_embedding(
    *,
    description: str,
    model: str = STUB_EMBEDDING_MODEL,
) -> tuple[list[float], str]:
    """Return L2-normalized embedding of the MOSS section description."""
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


def _stub_text_embedding(text: str, *, dim: int = DEFAULT_TEXT_DIM) -> np.ndarray:
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    rng = np.random.default_rng(int.from_bytes(seed[:8], "little"))
    vec = rng.standard_normal(dim).astype(np.float32)
    norm = float(np.linalg.norm(vec))
    if norm > 1e-9:
        vec /= norm
    return vec


_encoder_cache: dict[str, object] = {}


class _TransformersTextEncoder:
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
