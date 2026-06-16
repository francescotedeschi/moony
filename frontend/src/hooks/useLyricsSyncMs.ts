import { useRef } from "react";
import { createLyricsSyncGate, resolveLyricsSyncMs } from "../lib/lyricsSyncGate";

export function useLyricsSyncMs(
  currentMs: number,
  trackId: string,
  entryMs?: number,
  syncPlayback = true,
): number {
  const gateRef = useRef(createLyricsSyncGate());
  const wasSyncingRef = useRef(syncPlayback);

  if (syncPlayback && !wasSyncingRef.current) {
    gateRef.current = createLyricsSyncGate();
  }
  wasSyncingRef.current = syncPlayback;

  return resolveLyricsSyncMs(gateRef.current, currentMs, trackId, entryMs);
}
