import { describe, expect, it } from "vitest";
import { resolvePadLyricsDisplay, type PadLyricsDisplay } from "./usePadLyricsDisplay";
import type { TrackLyricsState } from "./useTrackLyrics";

const syncedLines = [
  { t_ms: 0, text: "Line one", line_index: 0 },
  { t_ms: 2_000, text: "Line two", line_index: 1 },
];

const syncedTrackLyrics: TrackLyricsState = {
  lines: syncedLines,
  copyright: "",
  source: "subtitle",
  loading: false,
  available: true,
};

const emptyTrackLyrics: TrackLyricsState = {
  lines: [],
  copyright: "",
  source: "",
  loading: false,
  available: false,
};

const loadingTrackLyrics: TrackLyricsState = {
  ...emptyTrackLyrics,
  loading: true,
};

const prevDisplay: PadLyricsDisplay = {
  trackId: "track-a",
  entryMs: 10_000,
  lines: syncedLines,
  source: "subtitle",
};

describe("resolvePadLyricsDisplay", () => {
  it("shows synced lyrics when the current track is ready", () => {
    const result = resolvePadLyricsDisplay(
      prevDisplay,
      { track_id: "track-b", start_ms: 45_000 },
      syncedTrackLyrics,
    );

    expect(result).toEqual({
      trackId: "track-b",
      entryMs: 45_000,
      lines: syncedLines,
      source: "subtitle",
      pixelUrl: undefined,
    });
  });

  it("keeps previous lyrics while the next track is loading", () => {
    const result = resolvePadLyricsDisplay(
      prevDisplay,
      { track_id: "track-b", start_ms: 45_000 },
      loadingTrackLyrics,
    );

    expect(result).toEqual(prevDisplay);
  });

  it("clears lyrics when the current track finished loading without synced subtitles", () => {
    const staleSameTrack: PadLyricsDisplay = {
      ...prevDisplay,
      trackId: "track-b",
    };

    const result = resolvePadLyricsDisplay(
      staleSameTrack,
      { track_id: "track-b", start_ms: 45_000 },
      emptyTrackLyrics,
    );

    expect(result).toBeNull();
  });

  it("clears previous-track lyrics once a no-lyrics track finishes loading", () => {
    const result = resolvePadLyricsDisplay(
      prevDisplay,
      { track_id: "track-b", start_ms: 45_000 },
      emptyTrackLyrics,
    );

    expect(result).toBeNull();
  });
});
