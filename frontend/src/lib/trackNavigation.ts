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

import type { MatchResponse, PrefetchCandidate, PrefetchResponse } from "./api";
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
