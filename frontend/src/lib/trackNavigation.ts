/**
 * Track vs segment events (frontend contract).
 *
 * **Cambia canzone** (pipeline `changeTrack` o handoff ultimo segmento):
 * - release pointer sul mood pad, click Next, start sessione, timeline match
 * - ultimo segmento MOSS → crossfade sul target mood del pad (prefetch zona pad)
 * Nomenclatura: target mood = pad; segment mood = segmento MOSS al playhead.
 *
 * **Prefetch prossime canzoni**: quando cambia `nowPlaying.track_id` e dopo replay da timeline.
 *
 * **Segmento nella canzone corrente**: ogni cambio indice segmento → `/match` pad_only
 * (stessa traccia, nuovo `start_ms`); non ricalcola il pool prefetch.
 */

import type { MatchResponse, PrefetchCandidate, PrefetchResponse, TrackTimeline } from "./api";
import { segmentAtTime } from "./segments";
import { nearestEmotionZone } from "./emotions";
import { matchResponseFromPrefetchCandidate } from "./penultimateHandoff";

export type TrackChangeReason =
  | "start"
  | "pad-release"
  | "skip"
  | "timeline";

export function pickPrefetchForPadTarget(
  intents: PrefetchResponse["intents"] | null | undefined,
  v: number,
  ar: number,
  played: ReadonlySet<string>,
  excludeTrackId?: string,
): PrefetchCandidate | undefined {
  if (!intents) return undefined;
  const zone = nearestEmotionZone(v, ar);
  const list = intents[String(zone.intent)];
  if (!list?.length) return undefined;
  return list.find(
    (c) => !played.has(c.track_id) && (!excludeTrackId || c.track_id !== excludeTrackId),
  );
}

export function buildMatchFromPrefetch(
  candidate: PrefetchCandidate,
  bpmFrom: number,
): MatchResponse {
  return matchResponseFromPrefetchCandidate(candidate, bpmFrom);
}

/** Prefetch match replayed from the matches panel at a motion-synced entry point. */
export function buildMatchFromPrefetchAtEntry(
  candidate: PrefetchCandidate,
  entryMs: number,
  bpmFrom: number,
  segments?: TrackTimeline["segments"],
): MatchResponse {
  const match = matchResponseFromPrefetchCandidate(
    { ...candidate, audio_start_ms: entryMs },
    bpmFrom,
  );
  const seg = segments?.length ? segmentAtTime(segments, entryMs) : null;
  if (seg) {
    match.start_ms = entryMs;
    match.segment = {
      t_start: entryMs,
      t_end: seg.t_end,
      v: seg.v,
      ar: seg.ar,
      label: seg.label,
      emotion_label: seg.emotion_label,
    };
  }
  return match;
}
