import { waitUntil } from "./backgroundTick";

/** Wait until playback position reaches target (e.g. beat-aligned crossfade start). */
export function waitUntilPlaybackMs(
  getMs: () => number,
  targetMs: number,
  opts?: { maxWaitMs?: number; isCancelled?: () => boolean },
): Promise<void> {
  return waitUntil(() => getMs() >= targetMs, {
    maxWaitMs: opts?.maxWaitMs,
    isCancelled: opts?.isCancelled,
  });
}
