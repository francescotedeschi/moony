import { measureLoudnessOffMainThread } from "./loudnessWorkerClient";
import {
  computeYoutubePlaybackGain,
  isPlausibleLufs,
  loudnessCacheKey,
  type LoudnessAnalysis,
} from "./youtubeLoudness";

const analysisCache = new Map<string, Promise<LoudnessAnalysis>>();
const gainCache = new Map<string, number>();
/** Per-track gain from catalog (independent of MOSS entry / startMs). */
const trackGainCache = new Map<string, number>();

/** Until EBU analysis completes, duck slightly (many streams are hot). */
const GAIN_BEFORE_ANALYSIS = 0.88;

/** If decode/measure fails, safer than unity. */
const GAIN_ON_ANALYSIS_FAILURE = 0.8;

function getAnalysis(url: string, startMs: number): Promise<LoudnessAnalysis> {
  const key = loudnessCacheKey(url, startMs);
  let pending = analysisCache.get(key);
  if (!pending) {
    pending = measureLoudnessOffMainThread(url, startMs)
      .then((analysis) => {
        if (!isPlausibleLufs(analysis.integratedLufs)) {
          throw new Error(`Invalid LUFS measurement (${analysis.integratedLufs})`);
        }
        return analysis;
      })
      .catch((err) => {
        analysisCache.delete(key);
        throw err;
      });
    analysisCache.set(key, pending);
  }
  return pending;
}

export function getCachedYoutubeGain(url: string, startMs = 0): number | undefined {
  return gainCache.get(loudnessCacheKey(url, startMs));
}

/** Apply catalog gain before decode/analysis (match / prefetch). */
export function seedCatalogYoutubeGain(url: string, gain: number): void {
  if (!Number.isFinite(gain) || gain <= 0 || gain > 1) return;
  trackGainCache.set(url, gain);
}

export function hasCatalogYoutubeGain(url: string): boolean {
  return trackGainCache.has(url);
}

/** Cached YouTube-style playback gain (linear, ≤ 1). */
export async function youtubePlaybackGainForUrl(
  url: string,
  startMs = 0,
): Promise<number> {
  const key = loudnessCacheKey(url, startMs);
  const cached = gainCache.get(key);
  if (cached != null) return cached;

  try {
    const analysis = await getAnalysis(url, startMs);
    const gain = computeYoutubePlaybackGain(analysis);
    gainCache.set(key, gain);
    return gain;
  } catch {
    gainCache.set(key, GAIN_ON_ANALYSIS_FAILURE);
    return GAIN_ON_ANALYSIS_FAILURE;
  }
}

/** Start analysis early (e.g. on prefetch warm). */
export function prefetchYoutubeLoudness(url: string, startMs = 0): void {
  void youtubePlaybackGainForUrl(url, startMs);
}

export function initialYoutubeGain(url: string, startMs = 0): number {
  return (
    trackGainCache.get(url) ??
    getCachedYoutubeGain(url, startMs) ??
    GAIN_BEFORE_ANALYSIS
  );
}
