"""Parse free-text MOSS-Music outputs into segment drafts."""

from __future__ import annotations

import json
import re

from analyzer.segment_build import MossSegmentDraft

_STRUCTURE_LABELS = (
    "intro",
    "outro",
    "pre-chorus",
    "pre_chorus",
    "prechorus",
    "chorus",
    "verse",
    "bridge",
    "hook",
    "instrumental",
    "interlude",
    "solo",
    "break",
    "drop",
    "build",
    "section",
)

_TIME_RANGE_RE = re.compile(
    r"""
    (?P<start>\d{1,2}:\d{2}(?::\d{2})?)       # 0:00 or 1:02:03
    \s*[-–—~to]+\s*
    (?P<end>\d{1,2}:\d{2}(?::\d{2})?)         # 0:30
    """,
    re.VERBOSE | re.IGNORECASE,
)

_PAREN_TIME_RE = re.compile(
    r"""
    \(
    \s*(?P<start>\d{1,2}:\d{2}(?::\d{2})?)
    \s*[-–—~to]+\s*
    (?P<end>\d{1,2}:\d{2}(?::\d{2})?)
    \s*\)
    """,
    re.VERBOSE | re.IGNORECASE,
)

_SEC_BRACKET_BLOCK_RE = re.compile(
    r"""
    \[
    \s*(?P<start>\d+(?:\.\d+)?)\s*s
    \s*[-–—~to]+\s*
    (?P<end>\d+(?:\.\d+)?)\s*s
    \s*    \]
    \s*
    (?P<label>[^\n:\[]+)
    \s*:\s*
    (?P<desc>[^\[\n]*)
    """,
    re.VERBOSE | re.IGNORECASE,
)

_BRACKET_BLOCK_RE = re.compile(
    r"""
    \[
    \s*(?P<start>\d{1,2}:\d{2}(?::\d{2})?)
    \s*[-–—~to]+\s*
    (?P<end>\d{1,2}:\d{2}(?::\d{2})?)
    \s*\]
    \s*
    (?P<label>[A-Za-z][A-Za-z0-9 _-]{0,40})?
    \s*[:\-–—]?\s*
    (?P<desc>[^\[\n]+)
    """,
    re.VERBOSE,
)


def parse_moss_segments(text: str, duration_sec: float) -> list[MossSegmentDraft]:
    """
    Parse MOSS free-text (or embedded JSON) into segment drafts.

    Supports official-style outputs with timestamps from time-marker models.
    """
    return parse_moss_structure(text, duration_sec, allow_full_track_fallback=True)


def parse_moss_structure(
    text: str,
    duration_sec: float,
    *,
    allow_full_track_fallback: bool = False,
) -> list[MossSegmentDraft]:
    """
    Parse MOSS structure-pass output into segment drafts.

    When ``allow_full_track_fallback`` is False (recommended for pass 1),
    prose without timestamps returns [] so the caller can use fixed windows.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    json_drafts = _try_parse_json_segments(cleaned, duration_sec)
    if json_drafts:
        return json_drafts

    line_drafts = _parse_line_segments(cleaned, duration_sec)
    if line_drafts:
        return line_drafts

    prose_drafts = _parse_prose_timestamps(cleaned, duration_sec)
    if prose_drafts:
        return prose_drafts

    if allow_full_track_fallback:
        caption = _extract_track_caption(cleaned)
        if caption:
            return [
                MossSegmentDraft(
                    start_sec=0.0,
                    end_sec=round(max(duration_sec, 1.0), 3),
                    structure_label="full",
                    description=caption,
                )
            ]

    return []


def _try_parse_json_segments(text: str, duration_sec: float) -> list[MossSegmentDraft]:
    for blob in _json_blobs(text):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        raw: list | None = None
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict):
            raw = data.get("segments") or data.get("sections") or data.get("structure")
        if not isinstance(raw, list) or not raw:
            continue
        drafts = _dicts_to_drafts(raw, duration_sec)
        if drafts:
            return drafts
    return []


def _json_blobs(text: str):
    yield text
    for match in re.finditer(r"\{[\s\S]*\}|\[[\s\S]*\]", text):
        yield match.group()


def _dicts_to_drafts(raw: list, duration_sec: float) -> list[MossSegmentDraft]:
    drafts: list[MossSegmentDraft] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        norm = {k.replace(" ", "_").lower(): v for k, v in item.items()}
        start = _coerce_seconds(norm.get("start_sec", norm.get("start", norm.get("start_time"))))
        end = _coerce_seconds(norm.get("end_sec", norm.get("end", norm.get("end_time"))))
        if start is None:
            start = 0.0
        if end is None:
            if i + 1 < len(raw) and isinstance(raw[i + 1], dict):
                nxt = {k.replace(" ", "_").lower(): v for k, v in raw[i + 1].items()}
                end = _coerce_seconds(nxt.get("start_sec", nxt.get("start", nxt.get("start_time"))))
            if end is None:
                end = duration_sec
        if end <= start:
            end = min(duration_sec, start + 15.0)

        structure = str(
            norm.get("label")
            or norm.get("structure_label")
            or norm.get("section")
            or norm.get("name")
            or ""
        ).strip()
        description = str(
            norm.get("description") or norm.get("caption") or norm.get("text") or ""
        ).strip()
        if not description:
            description = str(norm.get("mood") or norm.get("emotion") or "").strip()

        drafts.append(
            MossSegmentDraft(
                start_sec=round(float(start), 3),
                end_sec=round(min(float(end), duration_sec), 3),
                structure_label=_normalize_structure_label(structure),
                description=description,
            )
        )

    if drafts:
        last = drafts[-1]
        new_end = round(max(last.end_sec, min(duration_sec, last.start_sec + 1)), 3)
        drafts[-1] = MossSegmentDraft(
            start_sec=last.start_sec,
            end_sec=new_end,
            structure_label=last.structure_label,
            description=last.description,
        )
    return [d for d in drafts if d.end_sec > d.start_sec]


def _parse_line_segments(text: str, duration_sec: float) -> list[MossSegmentDraft]:
    drafts: list[MossSegmentDraft] = []

    for match in _SEC_BRACKET_BLOCK_RE.finditer(text):
        drafts.append(_draft_from_sec_match(match, duration_sec))

    if drafts:
        return _finalize_drafts(drafts, duration_sec)

    for match in _BRACKET_BLOCK_RE.finditer(text):
        drafts.append(_draft_from_match(match, duration_sec))

    if drafts:
        return _finalize_drafts(drafts, duration_sec)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in lines:
        draft = _parse_single_line(line, duration_sec)
        if draft:
            drafts.append(draft)

    if len(drafts) >= 2:
        return _finalize_drafts(drafts, duration_sec)

    # Paragraph style: "Intro (0:00-0:15): soft pads..."
    for chunk in re.split(r"\n\s*\n", text):
        draft = _parse_single_line(chunk.replace("\n", " ").strip(), duration_sec)
        if draft:
            drafts.append(draft)

    finalized = _finalize_drafts(drafts, duration_sec)
    return finalized if len(finalized) >= 2 else []


def _parse_prose_timestamps(text: str, duration_sec: float) -> list[MossSegmentDraft]:
    """Split narrative MOSS output at embedded timestamps (e.g. 'At 0:36')."""
    end_total = max(duration_sec, 1.0)
    boundaries: list[tuple[float, str, int]] = [(0.0, "intro", 0)]

    intro_match = re.search(
        r"(\d+)\s*-?\s*seconds?\s+(?:[\w-]+\s+){0,4}intro",
        text,
        re.IGNORECASE,
    )
    if intro_match:
        intro_end = float(intro_match.group(1))
        if 0 < intro_end < end_total:
            boundaries.append((intro_end, "intro", intro_match.start()))

    for match in re.finditer(r"\bAt\s+(\d{1,2}:\d{2}(?::\d{2})?)\b", text, re.IGNORECASE):
        start = _timestamp_to_seconds(match.group(1))
        if 0 < start < end_total:
            label = _label_near_position(text, match.start())
            boundaries.append((start, label, match.start()))

    for match in _TIME_RANGE_RE.finditer(text):
        start = _timestamp_to_seconds(match.group("start"))
        end = _timestamp_to_seconds(match.group("end"))
        if 0 <= start < end_total:
            remainder = text[match.end() : match.end() + 80]
            structure, _ = _split_label_description(remainder.strip(" :–—-\t"))
            boundaries.append((start, structure, match.start()))
        if 0 < end <= end_total and end < end_total:
            boundaries.append((end, "", match.end()))

    boundaries = _dedupe_boundaries(boundaries, end_total)
    if len(boundaries) < 2:
        return []

    drafts: list[MossSegmentDraft] = []
    for i, (start, label, pos) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else end_total
        if end <= start:
            continue
        snippet = _snippet_for_boundary(text, pos, boundaries, i)
        structure = label or _label_from_snippet(snippet)
        drafts.append(
            MossSegmentDraft(
                start_sec=round(start, 3),
                end_sec=round(min(end, end_total), 3),
                structure_label=structure,
                description=snippet[:500],
            )
        )

    return _finalize_drafts(drafts, end_total) if len(drafts) >= 2 else []


def _dedupe_boundaries(
    boundaries: list[tuple[float, str, int]],
    duration_sec: float,
) -> list[tuple[float, str, int]]:
    ordered = sorted(boundaries, key=lambda item: item[0])
    out: list[tuple[float, str, int]] = []
    for start, label, pos in ordered:
        if start < 0 or start > duration_sec:
            continue
        if out and abs(start - out[-1][0]) < 1.0:
            if label and not out[-1][1]:
                out[-1] = (out[-1][0], label, out[-1][2])
            continue
        out.append((start, label, pos))
    if not out or out[0][0] > 0.0:
        out.insert(0, (0.0, out[0][1] if out else "intro", 0))
    if out[-1][0] < duration_sec - 0.5:
        out.append((duration_sec, "outro", len(out)))
    return out


def _label_near_position(text: str, index: int) -> str:
    window = text[max(0, index - 40) : index + 120]
    lowered = window.lower()
    for label in _STRUCTURE_LABELS:
        if label in lowered:
            return label.replace("_", "-")
    return ""


def _label_from_snippet(snippet: str) -> str:
    structure, _ = _split_label_description(snippet[:120])
    return structure or "section"


def _snippet_for_boundary(
    text: str,
    pos: int,
    boundaries: list[tuple[float, str, int]],
    index: int,
) -> str:
    start_pos = max(0, pos - 20)
    end_pos = boundaries[index + 1][2] if index + 1 < len(boundaries) else len(text)
    end_pos = min(len(text), max(end_pos, pos + 80))
    return text[start_pos:end_pos].strip()


def _parse_single_line(line: str, duration_sec: float) -> MossSegmentDraft | None:
    time_match = _TIME_RANGE_RE.search(line) or _PAREN_TIME_RE.search(line)
    if not time_match:
        return None

    start = _timestamp_to_seconds(time_match.group("start"))
    end = _timestamp_to_seconds(time_match.group("end"))
    if end <= start:
        end = min(duration_sec, start + 15.0)

    remainder = line[time_match.end() :].strip(" :–—-\t")
    structure, description = _split_label_description(remainder)
    if not structure and not description:
        return None

    return MossSegmentDraft(
        start_sec=round(start, 3),
        end_sec=round(min(end, duration_sec), 3),
        structure_label=structure,
        description=description or structure,
    )


def _draft_from_sec_match(match: re.Match, duration_sec: float) -> MossSegmentDraft:
    start = float(match.group("start"))
    end = float(match.group("end"))
    label = (match.group("label") or "").strip()
    desc = (match.group("desc") or "").strip()
    structure = _normalize_moss_label(label) if label else ""
    description = desc or label
    if not structure:
        structure, description = _split_label_description(f"{label} {desc}".strip())
    if end <= start:
        end = min(duration_sec, start + 15.0)
    return MossSegmentDraft(
        start_sec=round(start, 3),
        end_sec=round(min(end, duration_sec), 3),
        structure_label=structure,
        description=description or desc or label,
    )


def _normalize_moss_label(label: str) -> str:
    """Map MOSS labels like intro1 / inst2 / chorus3 to canonical structure names."""
    key = label.strip().lower()
    key = re.sub(r"\d+$", "", key)
    key = key.replace("_", "-")
    aliases = {
        "inst": "instrumental",
        "introduction": "intro",
        "prechorus": "pre-chorus",
    }
    key = aliases.get(key, key)
    if key.startswith("verse"):
        return "verse"
    if key.startswith("chorus"):
        return "chorus"
    if key.startswith("intro"):
        return "intro"
    if key.startswith("outro"):
        return "outro"
    if key.startswith("bridge"):
        return "bridge"
    return _normalize_structure_label(key)


def _draft_from_match(match: re.Match, duration_sec: float) -> MossSegmentDraft:
    start = _timestamp_to_seconds(match.group("start"))
    end = _timestamp_to_seconds(match.group("end"))
    label = (match.group("label") or "").strip()
    desc = (match.group("desc") or "").strip()
    structure, description = _split_label_description(f"{label} {desc}".strip())
    if end <= start:
        end = min(duration_sec, start + 15.0)
    return MossSegmentDraft(
        start_sec=round(start, 3),
        end_sec=round(min(end, duration_sec), 3),
        structure_label=structure,
        description=description or desc or label,
    )


def _split_label_description(text: str) -> tuple[str, str]:
    cleaned = text.strip().strip("*_#")
    if not cleaned:
        return "", ""

    # "Intro: soft piano opening"
    if ":" in cleaned:
        head, tail = cleaned.split(":", 1)
        structure = _normalize_structure_label(head)
        if structure:
            return structure, tail.strip()

    # "Intro soft piano"
    lowered = cleaned.lower()
    for label in _STRUCTURE_LABELS:
        if lowered == label or lowered.startswith(f"{label} ") or lowered.startswith(f"{label}:"):
            rest = cleaned[len(label) :].strip(" :-–—")
            return label.replace("_", "-"), rest

    # First token as label if it looks structural
    first = cleaned.split()[0].lower().strip("*_#:,")
    if first.replace("-", "") in {l.replace("-", "") for l in _STRUCTURE_LABELS}:
        rest = cleaned[len(first) :].strip(" :-–—")
        return _normalize_structure_label(first), rest

    return "", cleaned


def _normalize_structure_label(label: str) -> str:
    key = label.strip().lower().replace("_", "-")
    key = re.sub(r"\s+", "-", key)
    key = key.strip("*_#:,")
    if key in _STRUCTURE_LABELS or key.replace("-", "") in {l.replace("-", "") for l in _STRUCTURE_LABELS}:
        return key
    return key


def _extract_track_caption(text: str) -> str:
    # Drop obvious markdown headings, keep prose.
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if _TIME_RANGE_RE.search(s) or _PAREN_TIME_RE.search(s):
            continue
        if s.startswith("#"):
            s = s.lstrip("#").strip()
        lines.append(s)
    caption = " ".join(lines).strip()
    return caption[:2000]


def _timestamp_to_seconds(value: str) -> float:
    parts = value.strip().split(":")
    nums = [int(p) for p in parts]
    if len(nums) == 2:
        mm, ss = nums
        return float(mm * 60 + ss)
    if len(nums) == 3:
        hh, mm, ss = nums
        return float(hh * 3600 + mm * 60 + ss)
    return 0.0


def _coerce_seconds(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        return _timestamp_to_seconds(text)
    try:
        return float(text)
    except ValueError:
        return None


def _finalize_drafts(drafts: list[MossSegmentDraft], duration_sec: float) -> list[MossSegmentDraft]:
    if not drafts:
        return []

    ordered = sorted(drafts, key=lambda d: d.start_sec)
    out: list[MossSegmentDraft] = []
    for i, draft in enumerate(ordered):
        start = max(0.0, draft.start_sec)
        end = draft.end_sec
        if end <= start:
            end = min(duration_sec, start + 15.0)
        if i + 1 < len(ordered):
            end = min(end, ordered[i + 1].start_sec)
        end = min(end, duration_sec)
        if end <= start:
            continue
        out.append(
            MossSegmentDraft(
                start_sec=round(start, 3),
                end_sec=round(end, 3),
                structure_label=draft.structure_label,
                description=draft.description,
            )
        )

    if out:
        last = out[-1]
        new_end = round(max(last.end_sec, min(duration_sec, last.start_sec + 1)), 3)
        out[-1] = MossSegmentDraft(
            start_sec=last.start_sec,
            end_sec=new_end,
            structure_label=last.structure_label,
            description=last.description,
        )
    return out
