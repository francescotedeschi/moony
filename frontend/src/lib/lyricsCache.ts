import { api, type LyricsResponse, type PrefetchResponse } from "./api";
import { isAbortError } from "./abortError";

export type CachedLyrics = LyricsResponse & { fetchedAt: number };

const cache = new Map<string, CachedLyrics>();
const inflight = new Map<string, Promise<CachedLyrics | null>>();

function toCached(data: LyricsResponse): CachedLyrics {
  return { ...data, fetchedAt: Date.now() };
}

export function getCachedLyrics(trackId: string): CachedLyrics | null {
  return cache.get(trackId) ?? null;
}

export function cacheLyrics(data: LyricsResponse): CachedLyrics {
  const entry = toCached(data);
  cache.set(data.track_id, entry);
  return entry;
}

export async function fetchLyrics(
  trackId: string,
  signal?: AbortSignal,
): Promise<CachedLyrics | null> {
  const hit = getCachedLyrics(trackId);
  if (hit) return hit;

  let pending = inflight.get(trackId);
  if (!pending) {
    pending = api
      .lyrics(trackId, signal)
      .then((data) => {
        const entry = cacheLyrics(data);
        inflight.delete(trackId);
        return entry;
      })
      .catch((err) => {
        inflight.delete(trackId);
        if (isAbortError(err)) return null;
        return null;
      });
    inflight.set(trackId, pending);
  }

  if (signal) {
    if (signal.aborted) return null;
    return Promise.race([
      pending,
      new Promise<null>((resolve) => {
        const onAbort = () => resolve(null);
        signal.addEventListener("abort", onAbort, { once: true });
      }),
    ]);
  }

  return pending;
}

export function collectLyricsPrefetchIds(
  intents: PrefetchResponse["intents"] | null | undefined,
  l2?: PrefetchResponse["l2"],
  extra: string[] = [],
): string[] {
  const ids = new Set(extra.filter(Boolean));

  const addCandidate = (c: { track_id: string; musixmatch?: unknown | null }) => {
    if (c.musixmatch) ids.add(c.track_id);
  };

  if (intents) {
    for (const list of Object.values(intents)) {
      for (const c of list ?? []) addCandidate(c);
    }
  }

  if (l2) {
    for (const branch of Object.values(l2)) {
      for (const list of Object.values(branch.intents ?? {})) {
        for (const c of list ?? []) addCandidate(c);
      }
    }
  }

  return [...ids];
}

export function prefetchLyricsForTrackIds(trackIds: string[], signal?: AbortSignal): void {
  for (const trackId of new Set(trackIds.filter(Boolean))) {
    if (getCachedLyrics(trackId)) continue;
    void fetchLyrics(trackId, signal);
  }
}

export function prefetchLyricsFromPrefetchResponse(
  result: { intents?: PrefetchResponse["intents"]; l2?: PrefetchResponse["l2"] },
  extraTrackIds: string[] = [],
  signal?: AbortSignal,
): void {
  const ids = collectLyricsPrefetchIds(result.intents, result.l2, extraTrackIds);
  prefetchLyricsForTrackIds(ids, signal);
}
