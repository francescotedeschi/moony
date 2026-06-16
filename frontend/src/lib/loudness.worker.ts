import { measureLoudnessFromUrl } from "./measureLoudnessFromUrl";
import type { LoudnessAnalysis } from "./youtubeLoudness";

export type LoudnessWorkerRequest = {
  id: number;
  url: string;
  startMs: number;
};

export type LoudnessWorkerResponse =
  | { id: number; ok: true; analysis: LoudnessAnalysis }
  | { id: number; ok: false; error?: string };

self.onmessage = (event: MessageEvent<LoudnessWorkerRequest>) => {
  const { id, url, startMs } = event.data;
  void measureLoudnessFromUrl(url, startMs)
    .then((analysis) => {
      const msg: LoudnessWorkerResponse = { id, ok: true, analysis };
      self.postMessage(msg);
    })
    .catch((err: unknown) => {
      const msg: LoudnessWorkerResponse = {
        id,
        ok: false,
        error: err instanceof Error ? err.message : "Loudness worker failed",
      };
      self.postMessage(msg);
    });
};
