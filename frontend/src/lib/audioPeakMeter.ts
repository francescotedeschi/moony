/** Log peak-meter floor — digital silence for envelope-driven visuals. */
export const PEAK_METER_DB_MIN = -192;
export const PEAK_METER_DB_MAX = 0;

const SILENCE_LINEAR = 1e-10;

/** True-peak linear amplitude (0..1) from time-domain samples. */
export function sampleAnalyserLinearPeak(analyser: AnalyserNode, buffer?: Float32Array): number {
  const buf = buffer ?? new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(buf);
  let peak = 0;
  for (let i = 0; i < buf.length; i++) {
    const sample = Math.abs(buf[i]);
    if (sample > peak) peak = sample;
  }
  return Math.max(0, Math.min(1, peak));
}

/** True-peak level in dBFS from time-domain samples (0 at full scale, floor at silence). */
export function linearPeakToDb(peak: number, floorDb = PEAK_METER_DB_MIN): number {
  if (peak < SILENCE_LINEAR) return floorDb;
  return Math.max(floorDb, 20 * Math.log10(peak));
}

/** Sample the current true-peak level (dBFS) from an AnalyserNode. */
export function sampleAnalyserPeakDb(analyser: AnalyserNode, buffer?: Float32Array): number {
  return linearPeakToDb(sampleAnalyserLinearPeak(analyser, buffer));
}

/**
 * Map linear peak to a 0..1 meter excursion on a logarithmic dB scale (0 dB → 1, −∞ → 0).
 * Needle position follows amplitude, not a linear sweep across the dB label range.
 */
export function linearPeakToMeterT(peak: number): number {
  if (peak < SILENCE_LINEAR) return 0;
  return Math.max(0, Math.min(1, peak));
}

export function peakDbToMeterT(db: number, minDb = PEAK_METER_DB_MIN, maxDb = PEAK_METER_DB_MAX): number {
  if (db <= minDb) return 0;
  if (db >= maxDb) return 1;
  return linearPeakToMeterT(Math.pow(10, db / 20));
}

/** Peak-style ballistics: instant attack, exponential release between frames. */
export class PeakEnvelopeFollower {
  private level = 0;

  constructor(private readonly releasePerFrame = 0.76) {}

  push(linearPeak: number): number {
    const target = linearPeakToMeterT(linearPeak);
    if (target >= this.level) {
      this.level = target;
    } else {
      this.level = Math.max(target, this.level * this.releasePerFrame);
    }
    return this.level;
  }

  reset() {
    this.level = 0;
  }
}
