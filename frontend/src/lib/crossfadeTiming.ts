/** Client-side crossfade start — mirrors backend ``compute_crossfade_start_ms`` (no beat grid). */

export function barMsForBpm(bpm: number): number {
  return Math.round((60_000 / Math.max(40, bpm)) * 4);
}

/** Pad fluid flow intensity keyed to track BPM (piecewise linear). */
const BPM_FLOW_INTENSITY_GRID = [
  { bpm: 80, scale: 0.2 },
  { bpm: 120, scale: 0.67 },
  { bpm: 160, scale: 1 },
  { bpm: 180, scale: 1.33 },
] as const;

export function bpmFlowIntensityScale(bpm: number): number {
  const grid = BPM_FLOW_INTENSITY_GRID;
  if (bpm <= grid[0].bpm) return grid[0].scale;
  if (bpm >= grid[grid.length - 1].bpm) return grid[grid.length - 1].scale;
  for (let i = 0; i < grid.length - 1; i++) {
    const lo = grid[i];
    const hi = grid[i + 1];
    if (bpm > hi.bpm) continue;
    const t = (bpm - lo.bpm) / (hi.bpm - lo.bpm);
    return lo.scale + t * (hi.scale - lo.scale);
  }
  return grid[grid.length - 1].scale;
}

function snapMsToBar(
  ms: number,
  barMs: number,
  prefer: "forward" | "backward" | "nearest",
): number {
  if (barMs <= 0) return Math.max(0, ms);
  const rel = ms / barMs;
  let idx: number;
  if (prefer === "forward") idx = Math.ceil(rel - 1e-9);
  else if (prefer === "backward") idx = Math.floor(rel + 1e-9);
  else idx = Math.round(rel);
  return Math.max(0, idx * barMs);
}

/** When to start the outgoing fade from the current playhead (ms from track start). */
export function computeCrossfadeStartMs(
  fromMs: number,
  fadeMs: number,
  bpm: number,
): number {
  const barMs = barMsForBpm(bpm);
  const runway = Math.max(Math.floor(barMs / 2), 300);
  let fadeEnd = snapMsToBar(fromMs + runway, barMs, "forward");
  if (fadeEnd <= fromMs) fadeEnd = fromMs + barMs;
  let start = Math.max(fromMs, fadeEnd - fadeMs);
  let snapped = snapMsToBar(start, barMs, "backward");
  if (snapped < fromMs) snapped = snapMsToBar(fromMs, barMs, "forward");
  return Math.max(fromMs, snapped);
}

/**
 * Resolve beat-aligned fade start at transition time.
 * Returns ``null`` → crossfade immediately (last segment, near track end, or beat unreachable).
 */
export function resolveCrossfadeStartForHandoff(opts: {
  nowMs: number;
  fadeMs: number;
  bpm: number;
  durationMs: number;
  onLastSegment: boolean;
}): number | null {
  const { nowMs, fadeMs, bpm, durationMs, onLastSegment } = opts;
  const safeFadeMs = Math.max(600, fadeMs);
  const nearEndSlack = Math.max(1500, safeFadeMs + 400);

  if (onLastSegment) return null;
  if (durationMs > 0 && nowMs >= durationMs - nearEndSlack) return null;

  const start = computeCrossfadeStartMs(nowMs, safeFadeMs, bpm);
  if (start <= nowMs + 50) return null;
  if (durationMs > 0 && start + safeFadeMs > durationMs + 400) return null;

  return start;
}
