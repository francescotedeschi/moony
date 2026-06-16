"""Lyric-aware transition anchors (runtime Musixmatch timestamps)."""

from app.models.api import LyricLine


def pick_exit_anchor(
    lines: list[LyricLine],
    t_ms: int,
    min_lead_ms: int = 2000,
) -> dict | None:
    """Next line boundary after t_ms + min_lead."""
    for i, line in enumerate(lines):
        if line.t_ms < t_ms + min_lead_ms:
            continue
        prev = lines[i - 1] if i > 0 else None
        return {
            "line_index": prev.line_index if prev else line.line_index,
            "t_ms": line.t_ms,
            "text": prev.text if prev else line.text,
        }
    if lines:
        last = lines[-1]
        return {"line_index": last.line_index, "t_ms": last.t_ms, "text": last.text}
    return None


def pick_entry_anchor(
    lines: list[LyricLine],
    window_start_ms: int,
    window_end_ms: int,
) -> dict | None:
    """First lyric line inside segment window."""
    in_window = [ln for ln in lines if window_start_ms <= ln.t_ms <= window_end_ms]
    if in_window:
        first = in_window[0]
        return {"line_index": first.line_index, "t_ms": first.t_ms, "text": first.text}

    after = [ln for ln in lines if ln.t_ms >= window_start_ms]
    if after:
        first = after[0]
        return {"line_index": first.line_index, "t_ms": first.t_ms, "text": first.text}
    return None


def align_crossfade_to_line(
    exit_t_ms: int,
    entry_t_ms: int,
    audio_start_ms: int,
    crossfade_bars: int = 4,
    bar_ms: int = 2000,
) -> dict:
    duration_ms = crossfade_bars * bar_ms
    return {
        "crossfade_start_ms": max(0, exit_t_ms - duration_ms // 2),
        "crossfade_duration_ms": duration_ms,
        "audio_start_ms": max(0, entry_t_ms - 100),
        "entry_t_ms": entry_t_ms,
        "exit_t_ms": exit_t_ms,
    }
