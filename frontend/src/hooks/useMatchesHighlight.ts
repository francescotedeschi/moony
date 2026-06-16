import { useCallback, useEffect, useState } from "react";

const DISCOVERED_KEY = "moony-matches-discovered";

export function useMatchesHighlight(nowPlaying: boolean, showSyncedMatches: boolean) {
  const [highlight, setHighlight] = useState(false);

  useEffect(() => {
    if (!nowPlaying) {
      setHighlight(false);
      return;
    }
    try {
      setHighlight(localStorage.getItem(DISCOVERED_KEY) !== "1");
    } catch {
      setHighlight(true);
    }
  }, [nowPlaying]);

  const markDiscovered = useCallback(() => {
    setHighlight(false);
    try {
      localStorage.setItem(DISCOVERED_KEY, "1");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (showSyncedMatches) markDiscovered();
  }, [showSyncedMatches, markDiscovered]);

  return { highlight, markDiscovered };
}
