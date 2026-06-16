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
    if (lyricsMode !== "musixmatch" || !nowPlaying?.musixmatch) {
      setDisplay(null);
      return;
    }

    const ready =
      !trackLyrics.loading &&
      trackLyrics.lines.length > 0 &&
      hasSyncedLyrics(trackLyrics.source, trackLyrics.lines);

    if (!ready) return;

    setDisplay({
      trackId: nowPlaying.track_id,
      entryMs: nowPlaying.start_ms,
      lines: trackLyrics.lines,
      source: trackLyrics.source,
      pixelUrl: trackLyrics.pixelUrl,
    });
  }, [
    lyricsMode,
    nowPlaying?.track_id,
    nowPlaying?.start_ms,
    nowPlaying?.musixmatch,
    trackLyrics.loading,
    trackLyrics.lines,
    trackLyrics.source,
    trackLyrics.pixelUrl,
  ]);

  return display;
}
