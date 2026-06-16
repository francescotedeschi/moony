import { useEffect, useState } from "react";
import type { MatchResponse } from "../lib/api";
import { hasSyncedLyrics, type LyricLine } from "../lib/lyricsSync";
import type { TrackLyricsState } from "./useTrackLyrics";

export type PadLyricsDisplay = {
  trackId: string;
  entryMs: number;
  lines: LyricLine[];
  source: string;
  pixelUrl?: string;
};

/** Keep the last synced lyrics visible until the next track's lyrics are ready. */
export function usePadLyricsDisplay(
  nowPlaying: MatchResponse | null,
  trackLyrics: TrackLyricsState,
  lyricsMode: string,
): PadLyricsDisplay | null {
  const [display, setDisplay] = useState<PadLyricsDisplay | null>(null);

  useEffect(() => {
    if (lyricsMode !== "musixmatch" || !nowPlaying?.track_id) {
      setDisplay(null);
      return;
    }

    const ready =
      !trackLyrics.loading &&
      trackLyrics.lines.length > 0 &&
      hasSyncedLyrics(trackLyrics.source, trackLyrics.lines);

    setDisplay((prev) => {
      if (ready) {
        return {
          trackId: nowPlaying.track_id,
          entryMs: nowPlaying.start_ms,
          lines: trackLyrics.lines,
          source: trackLyrics.source,
          pixelUrl: trackLyrics.pixelUrl,
        };
      }

      if (prev && prev.trackId === nowPlaying.track_id) {
        if (prev.entryMs !== nowPlaying.start_ms) {
          return { ...prev, entryMs: nowPlaying.start_ms };
        }
        return prev;
      }

      if (prev && prev.trackId !== nowPlaying.track_id && !trackLyrics.loading && !ready) {
        return null;
      }

      return prev;
    });
  }, [
    lyricsMode,
    nowPlaying?.track_id,
    nowPlaying?.start_ms,
    trackLyrics.loading,
    trackLyrics.lines,
    trackLyrics.source,
    trackLyrics.pixelUrl,
  ]);

  return display;
}
