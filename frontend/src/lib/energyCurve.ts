/** Linear sample of Cyanite energy_curve at playback time (values in [0, 1]). */
export function energyAtTimeMs(
  values: readonly number[],
  timestampsMs: readonly number[],
  tMs: number,
): number | null {
  if (values.length < 2 || values.length !== timestampsMs.length) return null;

  if (tMs <= timestampsMs[0]!) return values[0]!;
  const last = values.length - 1;
  if (tMs >= timestampsMs[last]!) return values[last]!;

  for (let i = 0; i < last; i++) {
    const t0 = timestampsMs[i]!;
    const t1 = timestampsMs[i + 1]!;
    if (tMs < t0 || tMs > t1) continue;
    const span = t1 - t0;
    if (span <= 0) return values[i]!;
    const u = (tMs - t0) / span;
    return values[i]! + (values[i + 1]! - values[i]!) * u;
  }

  return values[last]!;
}

const BLOOM_INTENSITY_MIN = 0.1;
const BLOOM_INTENSITY_MAX = 0.82;

/** Map Cyanite energy [0, 1] to fluid bloom intensity. */
export function bloomIntensityForEnergy(energy: number): number {
  const e = Math.max(0, Math.min(1, energy));
  return BLOOM_INTENSITY_MIN + e * (BLOOM_INTENSITY_MAX - BLOOM_INTENSITY_MIN);
}

export const FLUID_BLOOM_INTENSITY_IDLE = 0.08;

const FLOW_INTENSITY_MIN = 0.4;
const FLOW_INTENSITY_MAX = 1.5;

/** Map Cyanite energy [0, 1] to envelope flow / splat quantity scale. */
export function flowIntensityScaleForEnergy(energy: number): number {
  const e = Math.max(0, Math.min(1, energy));
  return FLOW_INTENSITY_MIN + e * (FLOW_INTENSITY_MAX - FLOW_INTENSITY_MIN);
}
