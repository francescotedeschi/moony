import { useRef } from "react";
import { createLyricsSyncGate, resolveLyricsSyncMs } from "../lib/lyricsSyncGate";

export function useLyricsSyncMs(
  currentMs: number,
  trackId: string,
  entryMs?: number,
): number {
  const gateRef = useRef(createLyricsSyncGate());

  return resolveLyricsSyncMs(gateRef.current, currentMs, trackId, entryMs);
}
