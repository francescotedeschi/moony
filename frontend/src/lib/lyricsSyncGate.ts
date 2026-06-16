/** How long after entry we accept playback ms as belonging to the new track. */
export const LYRICS_TRUST_WINDOW_MS = 30_000;
export const LYRICS_ENTRY_TOLERANCE_MS = 500;

/** Frames to reject a far-ahead clock right after handoff (outgoing track residue). */
export const LYRICS_HANDOFF_HOLD_READS = 12;

export type LyricsSyncGate = {
  trackId: string;
  entryMs: number;
  trustClock: boolean;
  holdFarAheadReads: number;
};

export function createLyricsSyncGate(): LyricsSyncGate {
  return { trackId: "", entryMs: 0, trustClock: false, holdFarAheadReads: 0 };
}

/**
 * After a track or entry change, ignore stale playback time from the outgoing
 * song until the audio clock lands near the new entry point.
 */
export function resolveLyricsSyncMs(
  gate: LyricsSyncGate,
  currentMs: number,
  trackId: string,
  entryMs?: number,
): number {
  const entry = entryMs ?? 0;

  if (gate.trackId !== trackId || gate.entryMs !== entry) {
    gate.trackId = trackId;
    gate.entryMs = entry;
    gate.trustClock = false;
    gate.holdFarAheadReads = LYRICS_HANDOFF_HOLD_READS;
  }

  if (!gate.trustClock) {
    const farAhead = entry > 0 && currentMs > entry + LYRICS_TRUST_WINDOW_MS;

    const alignedToEntry =
      entry <= 0
        ? currentMs <= LYRICS_TRUST_WINDOW_MS
        : Math.abs(currentMs - entry) <= LYRICS_ENTRY_TOLERANCE_MS;

    const advancingFromEntry =
      entry > 0 &&
      currentMs >= entry - LYRICS_ENTRY_TOLERANCE_MS &&
      currentMs <= entry + LYRICS_TRUST_WINDOW_MS;

    if (alignedToEntry || advancingFromEntry) {
      gate.trustClock = true;
      gate.holdFarAheadReads = 0;
      return currentMs;
    }

    if (farAhead) {
      if (gate.holdFarAheadReads > 0) {
        gate.holdFarAheadReads -= 1;
        return entry;
      }
      gate.trustClock = true;
      return currentMs;
    }

    return entry > 0 ? entry : 0;
  }

  return currentMs;
}
