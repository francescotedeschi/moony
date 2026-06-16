/** YouTube playback loudness (EBU R128 target used by YouTube normalization). */

/** Integrated loudness target — YouTube only turns loud tracks down, never boosts. */
export const YOUTUBE_TARGET_LUFS = -14;

/** True-peak ceiling for codec headroom after gain (dBTP / dBFS). */
export const YOUTUBE_TRUE_PEAK_DBTP = -1;

const MAX_ANALYZE_SEC = 90;

export type LoudnessAnalysis = {
  integratedLufs: number;
  truePeakDbfs: number;
};

/**
 * Playback gain for YouTube-style normalization: attenuate if louder than -14 LUFS,
 * never boost quieter content; cap true peak at -1 dBTP after gain.
 */
export function computeYoutubePlaybackGain(analysis: LoudnessAnalysis): number {
  const { integratedLufs, truePeakDbfs } = analysis;
  let gainDb = 0;
  if (integratedLufs > YOUTUBE_TARGET_LUFS) {
    gainDb = YOUTUBE_TARGET_LUFS - integratedLufs;
  }
  let linear = 10 ** (gainDb / 20);
  const peakAfterDbfs = truePeakDbfs + 20 * Math.log10(linear);
  if (peakAfterDbfs > YOUTUBE_TRUE_PEAK_DBTP) {
    linear = 10 ** ((YOUTUBE_TRUE_PEAK_DBTP - truePeakDbfs) / 20);
  }
  return Math.max(0, Math.min(1, linear));
}

export function mixDownMono(
  buffer: AudioBuffer,
  maxSeconds = MAX_ANALYZE_SEC,
  startSec = 0,
): { samples: Float32Array; sampleRate: number } {
  const sampleRate = buffer.sampleRate;
  const startSample = Math.min(
    Math.max(0, buffer.length - 1),
    Math.floor(Math.max(0, startSec) * sampleRate),
  );
  const maxSamples = Math.min(
    buffer.length - startSample,
    Math.max(1, Math.floor(sampleRate * maxSeconds)),
  );
  const left = buffer.getChannelData(0);
  const right = buffer.numberOfChannels > 1 ? buffer.getChannelData(1) : null;
  const mono = new Float32Array(maxSamples);
  for (let i = 0; i < maxSamples; i++) {
    const idx = startSample + i;
    mono[i] = right ? (left[idx] + right[idx]) * 0.5 : left[idx];
  }
  return { samples: mono, sampleRate };
}

/** Cache bucket: measure loudness near the actual playback entry (MOSS start). */
export function loudnessCacheKey(url: string, startMs = 0): string {
  const bucketSec = Math.floor(Math.max(0, startMs) / 5000) * 5;
  return `${url}@s${bucketSec}`;
}

export function isPlausibleLufs(lufs: number): boolean {
  return Number.isFinite(lufs) && lufs <= -5 && lufs >= -45;
}
