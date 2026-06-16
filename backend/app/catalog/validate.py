"""Validate MoodPad / MOSS catalog JSON before deploy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.catalog.motion import MOOD_TOLERANCE, expected_motion_length
from app.catalog.sections import raw_section_label, raw_track_sections

VA_MIN = -1.0
VA_MAX = 1.0
VA_EPS = 1e-6
UNIT_MIN = 0.0
UNIT_MAX = 1.0
MOOD_MIN = 0.0
MOOD_MAX = 100.0
MOTION_LENGTH_TOLERANCE = 1


@dataclass
class Issue:
    level: str  # "error" | "warn"
    code: str
    track_id: str
    message: str
    detail: str = ""


@dataclass
class ValidationReport:
    track_count: int = 0
    segment_count: int = 0
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warn"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _segment_va(raw: dict[str, Any]) -> tuple[float | None, float | None]:
    v_key = "valence" if "valence" in raw else "v" if "v" in raw else None
    ar_key = "arousal" if "arousal" in raw else "ar" if "ar" in raw else None
    v = float(raw[v_key]) if v_key is not None else None
    ar = float(raw[ar_key]) if ar_key is not None else None
    return v, ar


def _segment_sort_key(raw: dict[str, Any]) -> float:
    return float(raw.get("end_sec", raw.get("t_end", 0) / 1000.0))


def _in_range(value: float) -> bool:
    return VA_MIN <= value <= VA_MAX


def _validate_motion_block(
    report: ValidationReport,
    track_id: str,
    motion: dict[str, Any],
    duration_sec: float,
) -> None:
    hop = float(motion.get("hop_sec", 0))
    if hop <= 0:
        report.issues.append(
            Issue("error", "motion_invalid_hop", track_id, f"motion.hop_sec must be > 0 (got {hop}).")
        )
        return

    arrays = {
        "energy": motion.get("energy"),
        "vocal": motion.get("vocal"),
        "valence_smooth": motion.get("valence_smooth"),
        "arousal_smooth": motion.get("arousal_smooth"),
        "mood": motion.get("mood"),
    }
    for name, arr in arrays.items():
        if not isinstance(arr, list):
            report.issues.append(
                Issue("error", "motion_missing_array", track_id, f"motion.{name} must be a list.")
            )
            return

    n = len(arrays["energy"])
    if n == 0:
        report.issues.append(Issue("warn", "motion_empty", track_id, "motion arrays are empty."))
        return

    for name, arr in arrays.items():
        if len(arr) != n:
            report.issues.append(
                Issue(
                    "error",
                    "motion_length_mismatch",
                    track_id,
                    f"motion.{name} length {len(arr)} != {n}.",
                )
            )

    expected = expected_motion_length(duration_sec, hop)
    if abs(n - expected) > MOTION_LENGTH_TOLERANCE:
        report.issues.append(
            Issue(
                "warn",
                "motion_length_mismatch_duration",
                track_id,
                f"motion sample count {n} differs from expected ~{expected} "
                f"(duration_sec={duration_sec}, hop_sec={hop}).",
                detail=f"tolerance ±{MOTION_LENGTH_TOLERANCE}",
            )
        )

    for i, val in enumerate(arrays["energy"]):
        if not UNIT_MIN <= float(val) <= UNIT_MAX:
            report.issues.append(
                Issue(
                    "error",
                    "motion_energy_out_of_range",
                    track_id,
                    f"motion.energy[{i}]={val} outside [0, 1].",
                )
            )
            break

    for i, val in enumerate(arrays["vocal"]):
        if not UNIT_MIN <= float(val) <= UNIT_MAX:
            report.issues.append(
                Issue(
                    "error",
                    "motion_vocal_out_of_range",
                    track_id,
                    f"motion.vocal[{i}]={val} outside [0, 1].",
                )
            )
            break

    for i, val in enumerate(arrays["valence_smooth"]):
        if not VA_MIN <= float(val) <= VA_MAX:
            report.issues.append(
                Issue(
                    "error",
                    "motion_va_out_of_range",
                    track_id,
                    f"motion.valence_smooth[{i}]={val} outside [-1, 1].",
                )
            )
            break

    for i, val in enumerate(arrays["arousal_smooth"]):
        if not VA_MIN <= float(val) <= VA_MAX:
            report.issues.append(
                Issue(
                    "error",
                    "motion_va_out_of_range",
                    track_id,
                    f"motion.arousal_smooth[{i}]={val} outside [-1, 1].",
                )
            )
            break

    for i in range(n):
        v = float(arrays["valence_smooth"][i])
        ar = float(arrays["arousal_smooth"][i])
        mood = float(arrays["mood"][i])
        if not MOOD_MIN <= mood <= MOOD_MAX:
            report.issues.append(
                Issue(
                    "error",
                    "motion_mood_out_of_range",
                    track_id,
                    f"motion.mood[{i}]={mood} outside [0, 100].",
                )
            )
            break
        expected_mood = 50.0 + 25.0 * v + 25.0 * ar
        if abs(mood - expected_mood) > MOOD_TOLERANCE:
            report.issues.append(
                Issue(
                    "error",
                    "motion_mood_inconsistent",
                    track_id,
                    f"motion.mood[{i}]={mood} != 50+25*V+25*A ({expected_mood:.3f}).",
                )
            )
            break


def validate_catalog(data: dict[str, Any]) -> ValidationReport:
    """Scan catalog JSON for V/A range issues and placeholder segments."""
    report = ValidationReport()
    tracks = data.get("tracks")
    if not isinstance(tracks, list):
        report.issues.append(
            Issue("error", "missing_tracks", "", "Top-level `tracks` array is missing or invalid.")
        )
        return report

    report.track_count = len(tracks)
    version = str(data.get("version", "1.2"))

    for raw in tracks:
        track_id = str(raw.get("id", "<unknown>"))
        duration_sec = float(raw.get("duration_sec", 0) or 0)
        motion = raw.get("motion")
        if motion is not None and isinstance(motion, dict):
            _validate_motion_block(report, track_id, motion, duration_sec)
        elif version >= "1.3" and motion is None:
            report.issues.append(
                Issue(
                    "warn",
                    "missing_motion",
                    track_id,
                    "Catalog 1.3 track has no motion — runtime will use segment fallback.",
                )
            )

        jamendo = raw.get("jamendo") or {}
        if isinstance(jamendo, dict) and jamendo.get("local_audio_path"):
            report.issues.append(
                Issue(
                    "warn",
                    "local_audio_path_present",
                    track_id,
                    "jamendo.local_audio_path must not be relied on by the API (offline builder only).",
                )
            )

        segments = raw_track_sections(raw)
        if not segments:
            report.issues.append(
                Issue("warn", "no_segments", track_id, "Track has no sections/segments.")
            )
            continue

        report.segment_count += len(segments)
        sorted_segs = sorted(segments, key=_segment_sort_key)
        prev_v: float | None = None
        prev_ar: float | None = None
        prev_label = ""

        for idx, seg in enumerate(sorted_segs):
            label = raw_section_label(seg, fallback=f"seg_{idx}")
            v, ar = _segment_va(seg)

            if v is None or ar is None:
                report.issues.append(
                    Issue(
                        "warn",
                        "missing_va",
                        track_id,
                        f"Segment `{label}` is missing valence/arousal (or v/ar).",
                    )
                )
            else:
                if not _in_range(v):
                    report.issues.append(
                        Issue(
                            "error",
                            "va_out_of_range",
                            track_id,
                            f"Segment `{label}` valence={v} is outside [{VA_MIN}, {VA_MAX}].",
                        )
                    )
                if not _in_range(ar):
                    report.issues.append(
                        Issue(
                            "error",
                            "va_out_of_range",
                            track_id,
                            f"Segment `{label}` arousal={ar} is outside [{VA_MIN}, {VA_MAX}].",
                        )
                    )
                if abs(v) < VA_EPS and abs(ar) < VA_EPS:
                    report.issues.append(
                        Issue(
                            "warn",
                            "zero_va",
                            track_id,
                            f"Segment `{label}` has placeholder V/A (0, 0) — MOSS may not have returned coordinates.",
                        )
                    )

                if prev_v is not None and prev_ar is not None:
                    dv = v - prev_v
                    dar = ar - prev_ar
                    if not _in_range(dv) or not _in_range(dar):
                        report.issues.append(
                            Issue(
                                "error",
                                "delta_out_of_range",
                                track_id,
                                f"Transition `{prev_label}` → `{label}` has dv={dv:.3f}, dar={dar:.3f} outside [{VA_MIN}, {VA_MAX}].",
                                detail="Clamp dv/dar when writing transitions, or reduce segment extremes.",
                            )
                        )
                prev_v, prev_ar, prev_label = v, ar, label

        for tr in raw.get("transitions") or []:
            dv = tr.get("dv")
            dar = tr.get("dar")
            from_seg = tr.get("from_seg", "?")
            to_seg = tr.get("to_seg", "?")
            if dv is not None and not _in_range(float(dv)):
                report.issues.append(
                    Issue(
                        "error",
                        "transition_out_of_range",
                        track_id,
                        f"Stored transition {from_seg}→{to_seg} dv={dv} is outside [{VA_MIN}, {VA_MAX}].",
                    )
                )
            if dar is not None and not _in_range(float(dar)):
                report.issues.append(
                    Issue(
                        "error",
                        "transition_out_of_range",
                        track_id,
                        f"Stored transition {from_seg}→{to_seg} dar={dar} is outside [{VA_MIN}, {VA_MAX}].",
                    )
                )

    return report
