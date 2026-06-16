import { EMOTION_ZONES, moodColorForName } from "./emotions";

export type CatalogMoodSlice = {
  label: string;
  /** Normalized share in [0, 1]; slices sum to 1. */
  share: number;
  /** Pad polar angle for this mood anchor (radians). */
  angle: number;
  color: string;
};

export function moodPadAngle(label: string): number {
  const zone = EMOTION_ZONES.find((z) => z.name.toLowerCase() === label.trim().toLowerCase());
  if (!zone) return 0;
  return Math.atan2(-zone.ar, zone.v);
}

export function normalizeMoodShares(shares: readonly number[]): number[] {
  const total = shares.reduce((sum, s) => sum + Math.max(0, s ?? 0), 0);
  if (total <= 0) return shares.map(() => 0);
  return shares.map((s) => Math.max(0, s ?? 0) / total);
}

/** Mood slices sorted by pad angle; shares normalized to sum to 1. */
export function buildCatalogMoodSlices(
  labels: readonly string[],
  shares: readonly number[],
): CatalogMoodSlice[] {
  const normalized = normalizeMoodShares(shares);
  const slices = labels
    .map((label, i) => ({
      label,
      share: normalized[i] ?? 0,
      angle: moodPadAngle(label),
      color: moodColorForName(label),
    }))
    .filter((s) => s.share > 0)
    .sort((a, b) => a.angle - b.angle);

  return slices;
}

/** CSS conic-gradient with wedge sizes = catalog mood shares. */
export function moodPieGradientFromSlices(slices: readonly CatalogMoodSlice[]): string {
  if (!slices.length) return "conic-gradient(#334155 0% 100%)";

  let acc = 0;
  const stops: string[] = [];
  for (const slice of slices) {
    const pct = slice.share * 100;
    const next = acc + pct;
    stops.push(`${slice.color} ${acc.toFixed(4)}% ${next.toFixed(4)}%`);
    acc = next;
  }

  if (acc < 99.99) {
    const last = slices[slices.length - 1]!;
    stops.push(`${last.color} ${acc.toFixed(4)}% 100%`);
  }

  return `conic-gradient(from -90deg, ${stops.join(", ")})`;
}

export function moodPieGradient(labels: readonly string[], shares: readonly number[]): string {
  return moodPieGradientFromSlices(buildCatalogMoodSlices(labels, shares));
}

/** Map pad V/A to the mood slice covering this angle (pie starts at top). */
export function catalogMoodSliceAtVa(
  v: number,
  ar: number,
  slices: readonly CatalogMoodSlice[],
): CatalogMoodSlice | null {
  if (!slices.length) return null;

  const theta = Math.atan2(-ar, v);
  let t = theta + Math.PI / 2;
  t = ((t % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
  const frac = t / (2 * Math.PI);

  let acc = 0;
  for (const slice of slices) {
    acc += slice.share;
    if (frac <= acc || slice === slices[slices.length - 1]) return slice;
  }
  return slices[slices.length - 1] ?? null;
}
