/** External store for playback position — consumed via useSyncExternalStore (karaoke sync). */

export type PlaybackStore = {
  subscribe: (onStoreChange: () => void) => () => void;
  getSnapshot: () => number;
};

export function createPlaybackStore(): PlaybackStore & {
  setSnapshot: (ms: number) => void;
  forceSnapshot: (ms: number) => void;
} {
  let snapshot = 0;
  const listeners = new Set<() => void>();

  const notify = () => listeners.forEach((listener) => listener());

  return {
    getSnapshot: () => snapshot,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setSnapshot: (ms: number) => {
      if (snapshot === ms) return;
      snapshot = ms;
      notify();
    },
    forceSnapshot: (ms: number) => {
      snapshot = ms;
      notify();
    },
  };
}
