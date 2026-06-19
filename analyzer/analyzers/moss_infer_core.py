"""Shared MOSS-Music model load and inference helpers."""

from __future__ import annotations

from pathlib import Path


def load_moss_model(repo: Path, model_path: Path):
    """Load processor + model once (Transformers path)."""
    import sys

    import torch
    from transformers.utils import logging as hf_logging

    hf_logging.set_verbosity_error()
    if str(repo.resolve()) not in sys.path:
        sys.path.insert(0, str(repo.resolve()))

    from src.modeling_moss_music import MossMusicModel
    from src.processing_moss_music import MossMusicProcessor

    processor = MossMusicProcessor.from_pretrained(
        str(model_path),
        trust_remote_code=True,
        enable_time_marker=True,
    )

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    model = MossMusicModel.from_pretrained(
        str(model_path),
        trust_remote_code=True,
        torch_dtype="auto",
        device_map={"": device},
    )
    model.eval()
    return processor, model


def load_audio_numpy(path: str, sample_rate: int):
    """Load mono audio as numpy float32; bypass torchcodec (broken on Windows)."""
    import soundfile as sf
    import torch
    import torchaudio

    data, original_sample_rate = sf.read(path, always_2d=True)
    waveform = torch.from_numpy(data.T).float()
    if waveform.size(0) > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if original_sample_rate != sample_rate:
        waveform = torchaudio.functional.resample(
            waveform, orig_freq=original_sample_rate, new_freq=sample_rate
        )
    return waveform.squeeze(0).cpu().numpy()


def infer_moss(
    processor,
    model,
    *,
    audio_path: str,
    prompt: str,
    max_new_tokens: int = 1024,
    temperature: float = 0.0,
    top_p: float = 1.0,
    top_k: int = 50,
) -> str:
    """Run one MOSS inference on a loaded model."""
    import torch

    raw_audio = load_audio_numpy(audio_path, sample_rate=processor.config.mel_sr)
    inputs = processor(text=prompt, audios=[raw_audio], return_tensors="pt")
    inputs = inputs.to(model.device)
    if inputs.get("audio_data") is not None:
        inputs["audio_data"] = inputs["audio_data"].to(model.dtype)

    audio_input_mask = inputs["input_ids"] == processor.audio_token_id
    inputs["audio_input_mask"] = audio_input_mask

    do_sample = temperature > 0.0
    gen_kwargs: dict = {
        "max_new_tokens": max_new_tokens,
        "num_beams": 1,
        "use_cache": True,
        "do_sample": do_sample,
    }
    if do_sample:
        gen_kwargs.update(
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )

    with torch.no_grad():
        generated_ids = model.generate(**inputs, **gen_kwargs)

    input_len = inputs["input_ids"].shape[1]
    return processor.decode(generated_ids[0, input_len:], skip_special_tokens=True).strip()


def clean_model_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("Loading checkpoint") or "%|" in s or s.startswith("Setting `"):
            continue
        lines.append(s)
    return "\n".join(lines).strip()
