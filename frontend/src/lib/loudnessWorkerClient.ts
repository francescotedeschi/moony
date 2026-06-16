import LoudnessWorker from "./loudness.worker.ts?worker";
import type { LoudnessAnalysis } from "./youtubeLoudness";
import type { LoudnessWorkerRequest, LoudnessWorkerResponse } from "./loudness.worker";

type Pending = {
  url: string;
  startMs: number;
  resolve: (analysis: LoudnessAnalysis) => void;
  reject: (err: Error) => void;
};

let worker: Worker | null = null;
let workerDisabled = false;
let nextId = 1;
const pending = new Map<number, Pending>();

function rejectAllPending(reason: string): void {
  for (const [, entry] of pending) {
    entry.reject(new Error(reason));
  }
  pending.clear();
}

async function measureOnMainThread(
  url: string,
  startMs: number,
): Promise<LoudnessAnalysis> {
  const { measureLoudnessFromUrl } = await import("./measureLoudnessFromUrl");
  return measureLoudnessFromUrl(url, startMs);
}

function fallbackPending(entry: Pending): void {
  void measureOnMainThread(entry.url, entry.startMs).then(entry.resolve, entry.reject);
}

function ensureWorker(): Worker | null {
  if (workerDisabled || typeof Worker === "undefined") return null;
  if (worker) return worker;

  try {
    const instance = new LoudnessWorker();
    instance.onmessage = (event: MessageEvent<LoudnessWorkerResponse>) => {
      const msg = event.data;
      const entry = pending.get(msg.id);
      if (!entry) return;
      pending.delete(msg.id);
      if (msg.ok) {
        entry.resolve(msg.analysis);
        return;
      }
      fallbackPending(entry);
    };
    instance.onerror = () => {
      workerDisabled = true;
      instance.terminate();
      worker = null;
      const queued = [...pending.values()];
      pending.clear();
      for (const entry of queued) fallbackPending(entry);
    };
    worker = instance;
    return worker;
  } catch {
    workerDisabled = true;
    return null;
  }
}

/** Measure loudness off the main thread when a worker is available. */
export function measureLoudnessOffMainThread(
  url: string,
  startMs = 0,
): Promise<LoudnessAnalysis> {
  const instance = ensureWorker();
  if (!instance) return measureOnMainThread(url, startMs);

  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { url, startMs, resolve, reject });
    const req: LoudnessWorkerRequest = { id, url, startMs };
    instance.postMessage(req);
  });
}

export function terminateLoudnessWorker(): void {
  if (worker) {
    worker.terminate();
    worker = null;
  }
  rejectAllPending("Loudness worker terminated");
}
