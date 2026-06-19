"""Extract audio segment clips for per-segment MOSS captioning."""

from __future__ import annotations

import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

MIN_SEGMENT_SEC = 3.0
DEFAULT_SAMPLE_RATE = 24_000


def write_segment_clip(
    audio_path: Path,
    start_sec: float,
    end_sec: float,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    min_duration_sec: float = MIN_SEGMENT_SEC,
) -> Path:
    """
    Write a temporary WAV for [start_sec, end_sec].

    Pads short segments to ``min_duration_sec`` (MOSS needs enough audio context).
    Caller must delete the returned file when done.
    """
    duration = max(0.0, end_sec - start_sec)
    if duration <= 0:
        duration = min_duration_sec

    y, _ = librosa.load(
        str(audio_path),
        sr=sample_rate,
        mono=True,
        offset=max(0.0, start_sec),
        duration=duration,
    )
    min_samples = int(min_duration_sec * sample_rate)
    if y.size < min_samples:
        y = np.pad(y, (0, min_samples - y.size), mode="constant")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    sf.write(str(tmp_path), y, sample_rate)
    return tmp_path
