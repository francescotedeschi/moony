import {
  ebur128_integrated_mono,
  ebur128_true_peak_mono,
} from "ebur128-wasm";
import { mixDownMono, type LoudnessAnalysis } from "./youtubeLoudness";

const DECODE_TIMEOUT_MS = 45_000;

function decodeTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => {
      setTimeout(() => reject(new Error("Loudness analysis timeout")), ms);
    }),
  ]);
}

async function decodeAudioFromUrl(url: string): Promise<AudioBuffer> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch audio for loudness analysis (${response.status})`);
  }
  const arrayBuffer = await response.arrayBuffer();
  const offline = new OfflineAudioContext(2, 2, 44_100);
  return decodeTimeout(offline.decodeAudioData(arrayBuffer), DECODE_TIMEOUT_MS);
}

/** Fetch, decode, and EBU R128 measure — safe to run off the main thread. */
export async function measureLoudnessFromUrl(
  url: string,
  startMs = 0,
): Promise<LoudnessAnalysis> {
  const buffer = await decodeAudioFromUrl(url);
  const { samples, sampleRate } = mixDownMono(buffer, undefined, startMs / 1000);
  const integratedLufs = ebur128_integrated_mono(sampleRate, samples);
  const truePeakDbfs = ebur128_true_peak_mono(sampleRate, samples);
  return { integratedLufs, truePeakDbfs };
}
