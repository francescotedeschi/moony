import { useRef } from "react";

/** How long after entry we accept playback ms as belonging to the new track. */
const TRUST_WINDOW_MS = 30_000;

/**
 * After a track change, ignore stale playback time from the outgoing song until
 * the audio clock lands near the new track's entry point.
 */
export function useLyricsSyncMs(
  currentMs: number,
  trackId: string,
  entryMs?: number,
): number {
  const gateRef = useRef<{ trackId: string; entryMs: number; trustClock: boolean }>({
    trackId: "",
    entryMs: 0,
    trustClock: false,
  });

  const gate = gateRef.current;
  const entry = entryMs ?? 0;

  if (gate.trackId !== trackId || gate.entryMs !== entry) {
    gate.trackId = trackId;
    gate.entryMs = entry;
    gate.trustClock = false;
  }

  const withinTrustWindow =
    entry <= 0
      ? currentMs <= TRUST_WINDOW_MS
      : currentMs >= entry - 500 && currentMs <= entry + TRUST_WINDOW_MS;

  if (!gate.trustClock) {
    if (withinTrustWindow) {
      gate.trustClock = true;
      return currentMs;
    }
    return entry > 0 ? entry : 0;
  }

  return currentMs;
}
