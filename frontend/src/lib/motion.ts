/** DJ tempo sync — mirrors backend dj_playback_rates / motion_crossfade. */

export type CrossfadeCurve = "linear" | "equal_power";

export type MotionCrossfadePlan = {
  crossfadeMs: number;
  curve: CrossfadeCurve;
  playbackRateStart: number;
  playbackRateEnd: number;
  playbackRateOutEnd: number;
  moodJump: number;
};

const BPM_RATE_MIN = 0.85;
const BPM_RATE_MAX = 1.15;
const CROSSFADE_MS_MIN = 900;
const CROSSFADE_MS_MAX = 5500;
const MOOD_JUMP_EQUAL_POWER = 0.28;
const ENERGY_JUMP_EQUAL_POWER = 0.22;

export function djPlaybackRates(bpmFrom: number, bpmTo: number): { start: number; end: number } {
  if (bpmTo <= 0) return { start: 1, end: 1 };
  const start = Math.max(BPM_RATE_MIN, Math.min(BPM_RATE_MAX, bpmFrom / bpmTo));
  return { start, end: 1 };
}

function barMs(bpm: number): number {
  return Math.round((60_000 / Math.max(40, bpm)) * 4);
}

/** Client-side fallback when API did not attach a motion crossfade plan. */
export function motionCrossfadePlan(opts: {
  bpmFrom: number;
  bpmTo: number;
  exitV?: number;
  exitAr?: number;
  entryV: number;
  entryAr: number;
  exitEnergy?: number;
  entryEnergy?: number;
}): MotionCrossfadePlan {
  const { bpmFrom, bpmTo, entryV, entryAr } = opts;
  const rates = djPlaybackRates(bpmFrom, bpmTo);
  let rateStart = rates.start;
  let outEnd = 1;
  if (bpmFrom > 0 && bpmTo > 0) {
    outEnd = Math.max(BPM_RATE_MIN, Math.min(BPM_RATE_MAX, bpmTo / bpmFrom));
  }

  let moodJump = 0.4;
  if (opts.exitV !== undefined && opts.exitAr !== undefined) {
    moodJump = Math.hypot(entryV - opts.exitV, entryAr - opts.exitAr);
  }

  let energyDelta = 0;
  if (opts.exitEnergy !== undefined && opts.entryEnergy !== undefined) {
    energyDelta = opts.entryEnergy - opts.exitEnergy;
  }

  let bars = 1 + moodJump * 2.4 + Math.abs(energyDelta) * 1.6;
  if (energyDelta < -0.18) bars += 0.35;
  bars = Math.max(1, Math.min(4.5, bars));

  let crossfadeMs = Math.round(barMs(bpmTo) * bars);
  crossfadeMs = Math.max(CROSSFADE_MS_MIN, Math.min(CROSSFADE_MS_MAX, crossfadeMs));

  let curve: CrossfadeCurve = "linear";
  if (moodJump >= MOOD_JUMP_EQUAL_POWER || Math.abs(energyDelta) >= ENERGY_JUMP_EQUAL_POWER) {
    curve = "equal_power";
  }

  if (opts.exitAr !== undefined) {
    const arDelta = entryAr - opts.exitAr;
    if (arDelta > 0.12) rateStart = Math.min(BPM_RATE_MAX, rateStart * 1.025);
    else if (arDelta < -0.12) rateStart = Math.max(BPM_RATE_MIN, rateStart * 0.975);
  }

  return {
    crossfadeMs,
    curve,
    playbackRateStart: rateStart,
    playbackRateEnd: rates.end,
    playbackRateOutEnd: outEnd,
    moodJump,
  };
}

export function crossfadeFromMatch(
  match: {
    bpm: number;
    bpm_from?: number;
    bpm_to?: number;
    segment: { v: number; ar: number };
    crossfade_ms?: number;
    crossfade_curve?: string;
    playback_rate_start?: number;
    playback_rate_end?: number;
    playback_rate_out_end?: number;
  },
  exit?: { v: number; ar: number },
): MotionCrossfadePlan {
  if (match.crossfade_ms != null && match.crossfade_curve) {
    const bpmFrom = match.bpm_from ?? match.bpm;
    const rates = djPlaybackRates(bpmFrom, match.bpm_to ?? match.bpm);
    return {
      crossfadeMs: match.crossfade_ms,
      curve: match.crossfade_curve === "equal_power" ? "equal_power" : "linear",
      playbackRateStart: match.playback_rate_start ?? rates.start,
      playbackRateEnd: match.playback_rate_end ?? rates.end,
      playbackRateOutEnd: match.playback_rate_out_end ?? 1,
      moodJump: 0,
    };
  }
  return motionCrossfadePlan({
    bpmFrom: match.bpm_from ?? match.bpm,
    bpmTo: match.bpm_to ?? match.bpm,
    exitV: exit?.v,
    exitAr: exit?.ar,
    entryV: match.segment.v,
    entryAr: match.segment.ar,
  });
}
