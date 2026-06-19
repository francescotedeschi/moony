import { formatCatalogMood, moodColorForName, moodColorForVa, nearestEmotionZone } from "./emotions";
import type { MossSegment, TrackTimeline } from "../lib/api";

export function segmentHasInspectData(seg: MossSegment): boolean {
  return Boolean(seg.description?.trim() || seg.cyanite_mood_tag?.trim());
}

export function segmentCyaniteMoodLabel(seg: MossSegment): string | null {
  const tag = seg.cyanite_mood_tag?.trim();
  if (!tag) return null;
  return formatSegmentMoodLabel(tag);
}

export function segmentCyaniteMoodColor(seg: MossSegment): string {
  const tag = seg.cyanite_mood_tag?.trim();
  if (!tag) return moodColorForName("neutral");
  return moodColorForName(tag);
}

export function formatSegmentMoodLabel(label: string | undefined): string {
  const trimmed = label?.trim();
  if (!trimmed) return "—";
  return formatCatalogMood(trimmed);
}

const BOLD_SEGMENT_DESCRIPTION_LINE =
  /^(Voice|Mood|Instruments|Lyrics topic):/i;

export function segmentDescriptionLines(
  description: string,
): { text: string; bold: boolean }[] {
  return description
    .trim()
    .split("\n")
    .map((line) => ({
      text: line,
      bold: BOLD_SEGMENT_DESCRIPTION_LINE.test(line.trim()),
    }));
}

/** Mirrors backend ``MAX_ENTRY_POSITION_FRACTION`` — entry segment start within first 40% of track. */
export const MAX_ENTRY_POSITION_FRACTION = 0.4;

export function isOutroSegment(
  seg: MossSegment | null | undefined,
  index?: number,
  segmentCount?: number,
): boolean {
  if (!seg) return false;
  if ((seg.label ?? "").trim().toLowerCase() === "outro") return true;
  if (
    index != null &&
    segmentCount != null &&
    segmentCount > 1 &&
    index === segmentCount - 1
  ) {
    return true;
  }
  return false;
}

/** Display label: force «outro» on the last segment when unlabeled. */
export function effectiveSegmentLabel(
  seg: MossSegment,
  index: number,
  segmentCount: number,
): string {
  if (isOutroSegment(seg, index, segmentCount)) return "outro";
  return seg.label;
}

/** True when playback is in the final MOSS segment (crossfade handoff zone). */
export function isOnLastSegment(segments: MossSegment[], playbackMs: number): boolean {
  if (segments.length < 2) return false;
  return segmentIndexAtTime(segments, playbackMs) === segments.length - 1;
}

/** Prep + fade must fit inside the outro; otherwise handoff starts in the penultimate segment. */
export const SAME_MOOD_HANDOFF_PREP_MS = 2_000;

export function lastSegmentDurationMs(segments: MossSegment[]): number {
  if (!segments.length) return 0;
  const last = segments[segments.length - 1];
  return Math.max(0, last.t_end - last.t_start);
}

/** True when the tagged outro is shorter than the incoming crossfade needs. */
export function needsEarlySameMoodHandoff(
  segments: MossSegment[],
  fadeMs: number,
  prepMs = SAME_MOOD_HANDOFF_PREP_MS,
): boolean {
  if (segments.length < 2) return false;
  const safeFadeMs = Math.max(600, fadeMs);
  return lastSegmentDurationMs(segments) < safeFadeMs + prepMs;
}

/** Playhead threshold to start same-mood handoff before a short outro. */
export function earlySameMoodHandoffMs(
  segments: MossSegment[],
  fadeMs: number,
  prepMs = SAME_MOOD_HANDOFF_PREP_MS,
): number | null {
  if (!needsEarlySameMoodHandoff(segments, fadeMs, prepMs)) return null;
  const last = segments[segments.length - 1];
  const outroMs = last.t_end - last.t_start;
  const safeFadeMs = Math.max(600, fadeMs);
  const lead = Math.max(0, safeFadeMs + prepMs - outroMs);
  return Math.max(0, last.t_start - lead);
}

export function isInSameMoodHandoffZone(
  segments: MossSegment[],
  playbackMs: number,
  fadeMs: number,
  prepMs = SAME_MOOD_HANDOFF_PREP_MS,
): boolean {
  if (segments.length < 2) return false;
  if (isOnLastSegment(segments, playbackMs)) return true;
  const earlyAt = earlySameMoodHandoffMs(segments, fadeMs, prepMs);
  return earlyAt != null && playbackMs >= earlyAt;
}

/** True when playback actually moved into a different MOSS segment (ignores timeline-only updates). */
export function segmentCrossedBetween(
  segments: MossSegment[],
  prevMs: number | null,
  currentMs: number,
): { crossed: boolean; prevIdx: number; currentIdx: number } {
  const currentIdx = segmentIndexAtTime(segments, currentMs);
  if (prevMs == null) {
    return { crossed: false, prevIdx: currentIdx, currentIdx };
  }
  const prevIdx = segmentIndexAtTime(segments, prevMs);
  return { crossed: prevIdx !== currentIdx, prevIdx, currentIdx };
}

export function segmentAtTime(segments: MossSegment[], ms: number): MossSegment | null {
  for (const seg of segments) {
    if (ms >= seg.t_start && ms < seg.t_end) return seg;
  }
  return segments.length > 0 ? segments[segments.length - 1] : null;
}

export function segmentIndexAtTime(segments: MossSegment[], ms: number): number {
  const idx = segments.findIndex((seg) => ms >= seg.t_start && ms < seg.t_end);
  return idx >= 0 ? idx : Math.max(0, segments.length - 1);
}

export function trackDurationMs(timeline: TrackTimeline): number {
  if (timeline.duration_ms > 0) return timeline.duration_ms;
  return timeline.segments.reduce((max, s) => Math.max(max, s.t_end), 0);
}

export function needsHandoffTimeline(timeline: TrackTimeline | null | undefined): boolean {
  if (!timeline) return true;
  return timeline.segments.length <= 1;
}

/** Prefetch placeholder before /tracks/.../timeline returns full MOSS sections. */
export function isPrefetchTimelineStub(timeline: TrackTimeline): boolean {
  if (timeline.segments.length !== 1) return false;
  const seg = timeline.segments[0];
  const dur = trackDurationMs(timeline);
  return dur > 0 && seg.t_end < dur * 0.9;
}

/** Match row bar can render once full MOSS segments are available (motion curve optional). */
export function isTimelineBarReady(timeline: TrackTimeline | null | undefined): boolean {
  if (!timeline || timeline.segments.length === 0) return false;
  if (timeline.segments.length > 1) return true;
  return !isPrefetchTimelineStub(timeline);
}

/** Background enrich: wait until full MOSS segments replace prefetch stubs. */
export function needsTimelineEnrich(timeline: TrackTimeline | null | undefined): boolean {
  return !isTimelineBarReady(timeline);
}

/** Same rules as backend ``segment_entry_eligible`` (not first segment; start ≤ 40% duration). */
export function segmentEntryEligible(
  segments: MossSegment[],
  segIdx: number,
  durationMs: number,
): boolean {
  if (segIdx <= 0 || segIdx >= segments.length || durationMs <= 0) return false;
  return segments[segIdx].t_start <= durationMs * MAX_ENTRY_POSITION_FRACTION;
}

export function eligibleEntrySegmentIndices(timeline: TrackTimeline): number[] {
  const durationMs = trackDurationMs(timeline);
  const n = timeline.segments.length;
  const out: number[] = [];
  for (let i = 1; i < n; i++) {
    if (!segmentEntryEligible(timeline.segments, i, durationMs)) continue;
    if (isOutroSegment(timeline.segments[i], i, n)) continue;
    out.push(i);
  }
  return out;
}

export function vaAtTimelineMs(
  timeline: TrackTimeline,
  ms: number,
): { v: number; ar: number } {
  const seg = segmentAtTime(timeline.segments, ms);
  if (seg) return { v: seg.v, ar: seg.ar };
  const idx = segmentIndexAtTime(timeline.segments, ms);
  const fallback = timeline.segments[idx];
  return { v: fallback?.v ?? 0, ar: fallback?.ar ?? 0 };
}

export function vaAtSegmentIndex(
  timeline: TrackTimeline,
  segIdx: number,
): { v: number; ar: number } {
  const seg = timeline.segments[segIdx];
  if (seg) return { v: seg.v, ar: seg.ar };
  return { v: 0, ar: 0 };
}

/**
 * Match-row highlight: closest V/A among target early segments (≤40%, no intro/outro)
 * to the active segment V/A on the current track (``sourceSegIdx``).
 * Target candidates never extend past 40% — highlight cannot slide into the late song.
 */
export function syncedSegmentIndexByMotion(
  source: TrackTimeline,
  sourceSegIdx: number,
  target: TrackTimeline,
  fallbackEntryMs: number,
): number {
  const eligible = eligibleEntrySegmentIndices(target);
  if (!eligible.length) {
    return segmentIndexAtTime(target.segments, fallbackEntryMs);
  }

  const sourceVa = vaAtSegmentIndex(source, sourceSegIdx);
  let bestIdx = eligible[0];
  let bestDist = Infinity;
  for (const i of eligible) {
    const seg = target.segments[i];
    const dist = Math.hypot(sourceVa.v - seg.v, sourceVa.ar - seg.ar);
    if (dist < bestDist) {
      bestDist = dist;
      bestIdx = i;
    }
  }
  return bestIdx;
}

const MOOD_LABEL: Record<string, string> = {
  // 7 canonical Cyanite zones
  energetic: "Energetic",
  happy:     "Happy",
  chilled:   "Chilled",
  romantic:  "Romantic",
  sad:       "Sad",
  dark:      "Dark",
  tense:     "Tense",
  // Cyanite tags merged into primary zones
  uplifting:  "Happy",
  sexy:       "Romantic",
  aggressive: "Tense",
  scary:      "Tense",
  epic:       "Happy",
  ethereal:   "Chilled",
  // Legacy MOSS labels → nearest new zone
  calm:       "Chilled",
  joy:        "Happy",
  energy:     "Energetic",
  tension:    "Tense",
  // Additional MOSS synonyms
  melancholic: "Sad",
  hopeful:     "Happy",
  warm:        "Happy",
  dreamy:      "Chilled",
  playful:     "Happy",
};

/** Human-readable mood for a MOSS segment (catalog label or V/A zone). */
export function segmentMoodLabel(seg: MossSegment): string {
  const raw = (seg.emotion_label ?? "").trim().toLowerCase();
  if (raw) {
    return MOOD_LABEL[raw] ?? raw.charAt(0).toUpperCase() + raw.slice(1);
  }
  return nearestEmotionZone(seg.v, seg.ar).name;
}

/** Solid mood color from segment label or nearest pad zone. */
export function segmentMoodColor(seg: MossSegment, fallbackEmotion?: string): string {
  const label = (seg.emotion_label ?? "").trim().toLowerCase();
  if (label) return moodColorForName(label);
  if (fallbackEmotion) return moodColorForName(fallbackEmotion);
  return moodColorForVa(seg.v, seg.ar);
}

export function formatMs(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export type MatchTimelineRow = TrackTimeline & {
  emotion: string;
  entryMs: number;
};

export type TimelineView = {
  current: TrackTimeline;
  matches: MatchTimelineRow[];
};
