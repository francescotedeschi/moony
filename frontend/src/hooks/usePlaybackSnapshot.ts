import { useSyncExternalStore } from "react";
import type { PlaybackStore } from "../lib/playbackStore";

export function usePlaybackSnapshot(
  store: PlaybackStore | null | undefined,
  enabled = true,
): number {
  return useSyncExternalStore(
    (onStoreChange) => {
      if (!enabled || !store) return () => {};
      return store.subscribe(onStoreChange);
    },
    () => (enabled && store ? store.getSnapshot() : 0),
    () => 0,
  );
}
