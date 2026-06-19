export type LyricLine = {
  t_ms: number;
  text: string;
  line_index: number;
  end_ms?: number | null;
};

export type PreparedLyricLine = LyricLine & { end_ms: number };

/** Small lead so the highlighted line feels aligned with the vocal. */
export const LYRICS_SYNC_LEAD_MS = 150;

/** Hide synced lyrics when motion vocal presence falls below this level. */
export const LYRICS_VOCAL_MIN = 0.34;

export type LyricAtTimeOpts = {
  vocalLevel?: number | null;
  vocalMin?: number;
};

export function prepareLyricLines(lines: LyricLine[]): PreparedLyricLine[] {
  const sorted = [...lines].sort((a, b) => a.t_ms - b.t_ms || a.line_index - b.line_index);
  return sorted.map((line, index) => ({
    ...line,
    end_ms:
      line.end_ms ??
      (index + 1 < sorted.length
        ? sorted[index + 1].t_ms
        : line.t_ms + 12_000),
  }));
}

/** Binary search: last line whose start time is <= playback time (standard LRC karaoke). */
export function activeLineIndex(
  lines: PreparedLyricLine[],
  currentMs: number,
  leadMs = LYRICS_SYNC_LEAD_MS,
): number {
  if (!lines.length) return -1;
  const t = currentMs + leadMs;

  let lo = 0;
  let hi = lines.length - 1;
  let result = -1;

  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (lines[mid].t_ms <= t) {
      result = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }

  return result;
}

/**
 * Pad overlay line: follow activeLineIndex (karaoke hold) instead of hiding at end_ms
 * while the next line is still upcoming. Still honors empty-marker gaps when end_ms
 * ends before the next lyric timestamp.
 */
export function padLyricLineAtTime(
  lines: PreparedLyricLine[],
  currentMs: number,
  leadMs = LYRICS_SYNC_LEAD_MS,
): PreparedLyricLine | null {
  if (!lines.length) return null;
  if (currentMs + leadMs < lines[0]!.t_ms) return null;

  let idx = activeLineIndex(lines, currentMs, leadMs);
  while (idx >= 0 && !lines[idx]!.text.trim()) {
    idx -= 1;
  }
  if (idx < 0) return null;

  const line = lines[idx]!;
  if (
    currentMs >= line.end_ms &&
    (idx + 1 >= lines.length || line.end_ms < lines[idx + 1]!.t_ms)
  ) {
    return null;
  }
  return line;
}

/** Line to show at playback time, or null when no timed text should appear. */
export function lyricAtTime(
  lines: LyricLine[] | PreparedLyricLine[],
  currentMs: number,
  leadMs = LYRICS_SYNC_LEAD_MS,
  opts?: LyricAtTimeOpts,
): PreparedLyricLine | null {
  if (!lines.length) return null;
  const prepared =
    "end_ms" in lines[0] ? (lines as PreparedLyricLine[]) : prepareLyricLines(lines);
  const activeIdx = activeLineIndex(prepared, currentMs, leadMs);
  if (activeIdx < 0) return null;
  const line = prepared[activeIdx]!;
  const t = currentMs + leadMs;
  if (t < line.t_ms) return null;
  if (currentMs >= line.end_ms) return null;
  if (!line.text.trim()) return null;
  const vocalMin = opts?.vocalMin ?? LYRICS_VOCAL_MIN;
  if (opts?.vocalLevel != null && opts.vocalLevel < vocalMin) return null;
  return line;
}

/** True when playback time falls inside a timed lyric line with non-empty text. */
export function hasLyricsAtTime(
  lines: LyricLine[] | PreparedLyricLine[],
  currentMs: number,
  leadMs = LYRICS_SYNC_LEAD_MS,
  opts?: LyricAtTimeOpts,
): boolean {
  return lyricAtTime(lines, currentMs, leadMs, opts) !== null;
}

/** True when Musixmatch returned timed LRC subtitles (not snippet / static text). */
export function hasSyncedLyrics(source: string | undefined, lines: LyricLine[]): boolean {
  if (source === "snippet") return false;
  if (lines.length <= 1) return false;
  const uniqueTimes = new Set(lines.map((line) => line.t_ms));
  return uniqueTimes.size > 1;
}

export function lyricWindow(
  lines: PreparedLyricLine[],
  currentMs: number,
): {
  prev: PreparedLyricLine | null;
  active: PreparedLyricLine | null;
  next: PreparedLyricLine | null;
  activeIdx: number;
} {
  const activeIdx = activeLineIndex(lines, currentMs);
  if (activeIdx < 0) {
    return {
      prev: null,
      active: null,
      next: lines[0] ?? null,
      activeIdx: -1,
    };
  }
  return {
    prev: activeIdx > 0 ? lines[activeIdx - 1] : null,
    active: lines[activeIdx],
    next: activeIdx + 1 < lines.length ? lines[activeIdx + 1] : null,
    activeIdx,
  };
}
