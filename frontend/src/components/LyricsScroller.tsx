import { useEffect, useMemo, useRef, useState } from "react";
import { useLyricsSyncMs } from "../hooks/useLyricsSyncMs";
import { usePlaybackSnapshot } from "../hooks/usePlaybackSnapshot";
import type { PlaybackStore } from "../lib/playbackStore";
import {
  activeLineIndex,
  hasSyncedLyrics,
  prepareLyricLines,
  type LyricLine,
} from "../lib/lyricsSync";

type Props = {
  trackId: string;
  lines: LyricLine[];
  playbackStore: PlaybackStore;
  entryMs?: number;
  pixelUrl?: string;
  source?: string;
  loading?: boolean;
  enabled?: boolean;
  /** When false, freeze on the last synced line (e.g. while the next track loads). */
  syncPlayback?: boolean;
  /** Pad overlay: single active line, full wrap, no scroll trail. */
  variant?: "trail" | "pad";
};

function lineStateClass(idx: number, activeIdx: number): string {
  if (activeIdx < 0) {
    return idx === 0 ? "moony-lyrics-trail__line--waiting" : "moony-lyrics-trail__line--upcoming";
  }
  const rel = idx - activeIdx;
  if (rel === 0) return "moony-lyrics-trail__line--active";
  if (rel < 0) return "moony-lyrics-trail__line--past";
  return "moony-lyrics-trail__line--upcoming";
}

export function LyricsScroller({
  trackId,
  lines,
  playbackStore,
  entryMs,
  pixelUrl,
  source,
  loading,
  enabled = true,
  syncPlayback = true,
  variant = "trail",
}: Props) {
  const synced = useMemo(() => hasSyncedLyrics(source, lines), [source, lines]);
  const currentMs = usePlaybackSnapshot(playbackStore, enabled);
  const syncMs = useLyricsSyncMs(currentMs, trackId, entryMs);
  const prepared = useMemo(() => prepareLyricLines(lines), [lines]);
  const computedActiveIdx = useMemo(
    () => activeLineIndex(prepared, syncMs),
    [prepared, syncMs],
  );
  const frozenActiveIdxRef = useRef(computedActiveIdx);
  useEffect(() => {
    if (syncPlayback) {
      frozenActiveIdxRef.current = computedActiveIdx;
    }
  }, [syncPlayback, computedActiveIdx]);
  const activeIdx = syncPlayback ? computedActiveIdx : frozenActiveIdxRef.current;

  const scrollIndex = activeIdx < 0 ? 0 : activeIdx;
  const linesKey = useMemo(
    () => `${trackId}:${lines.length}:${lines[0]?.line_index ?? 0}`,
    [trackId, lines],
  );
  const prevLinesKeyRef = useRef(linesKey);
  const prevTrackIdRef = useRef(trackId);
  const [scrollTransition, setScrollTransition] = useState(true);
  const [isEntering, setIsEntering] = useState(false);

  useEffect(() => {
    if (prevTrackIdRef.current === trackId) return;
    prevTrackIdRef.current = trackId;
    setIsEntering(true);
    const done = window.setTimeout(() => setIsEntering(false), 780);
    return () => window.clearTimeout(done);
  }, [trackId]);

  useEffect(() => {
    if (prevLinesKeyRef.current === linesKey) return;
    prevLinesKeyRef.current = linesKey;
    setScrollTransition(false);
    const id = requestAnimationFrame(() => setScrollTransition(true));
    return () => cancelAnimationFrame(id);
  }, [linesKey]);

  if (loading || !synced || !lines.length) return null;

  const displayIdx = activeIdx < 0 ? 0 : activeIdx;
  const activeLine = prepared[displayIdx];

  if (variant === "pad") {
    return (
      <div
        className={`moony-lyrics-trail moony-lyrics-trail--pad-single${
          isEntering ? " moony-lyrics-trail--entering" : ""
        }`}
        data-testid="lyrics-trail"
        aria-label="Synced lyrics"
      >
        {pixelUrl ? (
          <img src={pixelUrl} alt="" className="hidden" width={1} height={1} />
        ) : null}
        <div className="moony-lyrics-trail__viewport moony-lyrics-trail__viewport--single" aria-live="polite">
          <p
            key={`${trackId}-${activeLine.line_index}-${activeLine.t_ms}`}
            className="moony-lyrics-trail__line moony-lyrics-trail__line--active"
            aria-current="true"
            data-testid="lyrics-active-line"
          >
            {activeLine.text}
          </p>
        </div>
      </div>
    );
  }

  const scrollAnimate = scrollTransition && !isEntering;

  return (
    <div
      className={`moony-lyrics-trail${isEntering ? " moony-lyrics-trail--entering" : ""}`}
      data-testid="lyrics-trail"
      aria-label="Synced lyrics"
    >
      {pixelUrl ? (
        <img src={pixelUrl} alt="" className="hidden" width={1} height={1} />
      ) : null}
      <div className="moony-lyrics-trail__viewport" aria-live="polite">
        <div className="moony-lyrics-trail__enter-wrap">
          <div
            key={linesKey}
            className={`moony-lyrics-trail__list${scrollAnimate ? " moony-lyrics-trail__list--animate" : ""}`}
            style={{ "--active-index": scrollIndex } as React.CSSProperties}
          >
          {prepared.map((line, idx) => (
            <p
              key={`${line.line_index}-${line.t_ms}`}
              className={`moony-lyrics-trail__line ${lineStateClass(idx, activeIdx)}`}
              aria-current={idx === activeIdx ? "true" : undefined}
              data-testid={idx === activeIdx ? "lyrics-active-line" : undefined}
            >
              {line.text}
            </p>
          ))}
          </div>
        </div>
      </div>
    </div>
  );
}
