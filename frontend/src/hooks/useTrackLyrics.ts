import { useEffect, useState } from "react";
import type { LyricsResponse } from "../lib/api";
import { isAbortError } from "../lib/abortError";
import { fetchLyrics, getCachedLyrics, type CachedLyrics } from "../lib/lyricsCache";
import { hasSyncedLyrics } from "../lib/lyricsSync";

export type TrackLyricsState = {
  lines: LyricsResponse["lines"];
  copyright: string;
  pixelUrl?: string;
  source: string;
  loading: boolean;
  available: boolean;
};

const EMPTY: TrackLyricsState = {
  lines: [],
  copyright: "",
  source: "",
  loading: false,
  available: false,
};

function fromCache(cached: CachedLyrics): TrackLyricsState {
  const lines = cached.lines ?? [];
  return {
    lines,
    copyright: cached.lyrics_copyright ?? "",
    pixelUrl: cached.pixel_tracking_url,
    source: cached.source ?? "subtitle",
    loading: false,
    available: hasSyncedLyrics(cached.source, lines),
  };
}

function initialState(trackId: string | null | undefined, enabled: boolean): TrackLyricsState {
  if (!trackId || !enabled) return EMPTY;
  const cached = getCachedLyrics(trackId);
  if (cached) return fromCache(cached);
  return { ...EMPTY, loading: true };
}

export function useTrackLyrics(
  trackId: string | null | undefined,
  enabled: boolean,
): TrackLyricsState {
  const [state, setState] = useState<TrackLyricsState>(() => initialState(trackId, enabled));

  useEffect(() => {
    if (!trackId || !enabled) {
      setState(EMPTY);
      return;
    }

    const cached = getCachedLyrics(trackId);
    if (cached) {
      setState(fromCache(cached));
    } else {
      setState({ ...EMPTY, loading: true });
    }

    const controller = new AbortController();

    void fetchLyrics(trackId, controller.signal)
      .then((data) => {
        if (controller.signal.aborted || !data) return;
        setState(fromCache(data));
      })
      .catch((err) => {
        if (isAbortError(err) || controller.signal.aborted) return;
        setState((prev) => (prev.lines.length ? { ...prev, loading: false } : EMPTY));
      });

    return () => controller.abort("track-changed");
  }, [trackId, enabled]);

  return state;
}
