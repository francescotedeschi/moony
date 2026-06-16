/** Timers that keep working when the tab is in the background (RAF is throttled). */

export const BACKGROUND_INTERVAL_MS = 50;

/** Poll playback / wait loops — reliable under Page Visibility throttling. */
export const PLAYBACK_POLL_MS = 200;

export function schedulePlaybackPoll(
  onTick: () => void,
  intervalMs = PLAYBACK_POLL_MS,
): () => void {
  const id = window.setInterval(onTick, intervalMs);
  return () => window.clearInterval(id);
}

export function waitUntil(
  predicate: () => boolean,
  opts?: { intervalMs?: number; maxWaitMs?: number; isCancelled?: () => boolean },
): Promise<void> {
  if (predicate()) return Promise.resolve();

  const intervalMs = opts?.intervalMs ?? PLAYBACK_POLL_MS;
  const maxWait = opts?.maxWaitMs ?? 120_000;
  const isCancelled = opts?.isCancelled ?? (() => false);
  const started = performance.now();

  return new Promise((resolve) => {
    const id = window.setInterval(() => {
      if (isCancelled()) {
        window.clearInterval(id);
        resolve();
        return;
      }
      if (predicate()) {
        window.clearInterval(id);
        resolve();
        return;
      }
      if (performance.now() - started > maxWait) {
        window.clearInterval(id);
        resolve();
      }
    }, intervalMs);
  });
}
