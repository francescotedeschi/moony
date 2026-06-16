export type LyricLine = { t_ms: number; text: string; line_index: number };

export type PreparedLyricLine = LyricLine & { end_ms: number };

/** Small lead so the highlighted line feels aligned with the vocal. */
export const LYRICS_SYNC_LEAD_MS = 150;

export function prepareLyricLines(lines: LyricLine[]): PreparedLyricLine[] {
  const sorted = [...lines].sort((a, b) => a.t_ms - b.t_ms || a.line_index - b.line_index);
  return sorted.map((line, index) => ({
    ...line,
    end_ms:
      index + 1 < sorted.length
        ? sorted[index + 1].t_ms
        : line.t_ms + 12_000,
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
