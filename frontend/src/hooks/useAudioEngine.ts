import { useCallback, useEffect, useRef, useState } from "react";
import {
  hasCatalogYoutubeGain,
  initialYoutubeGain,
  prefetchYoutubeLoudness,
  seedCatalogYoutubeGain,
  youtubePlaybackGainForUrl,
} from "../lib/analyzeTrackLoudness";
import type { CrossfadeCurve, MotionCrossfadePlan } from "../lib/motion";
import { BACKGROUND_INTERVAL_MS, schedulePlaybackPoll } from "../lib/backgroundTick";
import { sampleAnalyserLinearPeak } from "../lib/audioPeakMeter";
import { createPlaybackStore } from "../lib/playbackStore";
import type { PlaybackStore } from "../lib/playbackStore";
import { perceptualToAmplitude } from "../lib/volume";

export type CrossfadePlayOptions = {
  url: string;
  startMs?: number;
  youtubePlaybackGain?: number;
  plan: MotionCrossfadePlan;
  /** Fired once incoming audio is playing and the volume fade loop is about to start. */
  onCrossfadeStart?: () => void;
};

type PlayOptions = {
  url: string;
  startMs?: number;
  /** Catalog precomputed gain at startMs; skips WASM analysis when set. */
  youtubePlaybackGain?: number;
  /** Fired once playback has started (after optional seek). */
  onPlayStart?: () => void;
};

type Bus = "A" | "B";

type BusGains = Record<Bus, number>;

type BusGraph = {
  source: MediaElementAudioSourceNode;
  normGain: GainNode;
  busGain: GainNode;
  limiter: DynamicsCompressorNode;
};

type PreloadedTrack = {
  url: string;
  startMs: number;
  seekAfterPlayMs: number;
  bus: Bus;
};

export type PreloadTrackOptions = {
  url: string;
  startMs?: number;
  youtubePlaybackGain?: number;
};

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, n));
}

/** True when the element finished or is within ``thresholdSec`` of duration. */
function isAudioAtEnd(el: HTMLAudioElement, thresholdSec = 0.35): boolean {
  if (el.ended) return true;
  const duration = el.duration;
  if (!Number.isFinite(duration) || duration <= 0) return false;
  return el.currentTime >= duration - thresholdSec;
}

const METADATA_TIMEOUT_MS = 25_000;
const SEEK_TIMEOUT_MS = 6_000;
const WARM_TIMEOUT_MS = 4_000;
/** Wait for LUFS gain before starting playback when analysis is still pending. */
const LOUDNESS_READY_MS = 4_000;
/** Above this, start at 0 and seek after play (avoids slow pre-play seek on MP3). */
const DEFER_SEEK_MS = 800;
const RANGE_WARM_BYTES = 131_071;

async function seekTo(el: HTMLAudioElement, startSec: number): Promise<void> {
  const duration = el.duration;
  const target =
    startSec <= 0.01
      ? 0
      : Number.isFinite(duration) && duration > 0
        ? Math.min(startSec, Math.max(0, duration - 0.05))
        : startSec;

  if (Math.abs(el.currentTime - target) < 0.35) return;

  el.currentTime = target;

  if (Math.abs(el.currentTime - target) < 0.35) return;

  await Promise.race([
    new Promise<void>((resolve) => {
      const onSeeked = () => {
        cleanup();
        resolve();
      };
      const cleanup = () => {
        el.removeEventListener("seeked", onSeeked);
      };
      el.addEventListener("seeked", onSeeked);
    }),
    new Promise<void>((resolve) => {
      window.setTimeout(resolve, SEEK_TIMEOUT_MS);
    }),
  ]);
}

function hasUsableMetadata(el: HTMLAudioElement): boolean {
  return (
    el.readyState >= HTMLMediaElement.HAVE_METADATA ||
    (Number.isFinite(el.duration) && el.duration > 0)
  );
}

const warmedUrls = new Set<string>();

async function warmAudioUrl(url: string, startMs = 0): Promise<void> {
  const warmKey = `${url}@${Math.floor(startMs / 5000)}`;
  if (warmedUrls.has(warmKey)) return;
  try {
    const resp = await Promise.race([
      fetch(url, {
        method: "GET",
        headers: { Range: `bytes=0-${RANGE_WARM_BYTES}` },
        cache: "force-cache",
      }),
      new Promise<Response>((resolve) => {
        window.setTimeout(
          () => resolve(new Response(null, { status: 408 })),
          WARM_TIMEOUT_MS,
        );
      }),
    ]);
    if (resp.ok || resp.status === 206) {
      warmedUrls.add(warmKey);
      prefetchYoutubeLoudness(url, startMs);
    }
  } catch {
    /* optional — main path still uses <audio> */
  }
}

function fadeInGain(t: number, curve: CrossfadeCurve): number {
  const p = Math.max(0, Math.min(1, t));
  return curve === "equal_power" ? Math.sin((p * Math.PI) / 2) : p;
}

function fadeOutGain(t: number, curve: CrossfadeCurve): number {
  const p = Math.max(0, Math.min(1, t));
  return curve === "equal_power" ? Math.cos((p * Math.PI) / 2) : 1 - p;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * Math.max(0, Math.min(1, t));
}

function waitForMetadata(el: HTMLAudioElement): Promise<void> {
  if (el.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA || hasUsableMetadata(el)) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      cleanup();
      if (hasUsableMetadata(el)) resolve();
      else if (el.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) resolve();
      else reject(new Error("Audio metadata timeout"));
    }, METADATA_TIMEOUT_MS);
    const onReady = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("Audio load failed"));
    };
    const cleanup = () => {
      window.clearTimeout(timer);
      el.removeEventListener("loadedmetadata", onReady);
      el.removeEventListener("loadeddata", onReady);
      el.removeEventListener("canplay", onReady);
      el.removeEventListener("error", onError);
    };
    el.addEventListener("loadedmetadata", onReady);
    el.addEventListener("loadeddata", onReady);
    el.addEventListener("canplay", onReady);
    el.addEventListener("error", onError);
  });
}

export function useAudioEngine() {
  const audioARef = useRef<HTMLAudioElement | null>(null);
  const audioBRef = useRef<HTMLAudioElement | null>(null);
  const activeRef = useRef<Bus>("A");
  const playEpochRef = useRef(0);
  const crossfadeTimerRef = useRef(0);
  const crossfadeActiveRef = useRef(false);
  const unlockedRef = useRef(false);
  const unlockAudioRef = useRef<HTMLAudioElement | null>(null);

  const SILENT_WAV =
    "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";

  const onTrackEndedRef = useRef<(() => void) | null>(null);
  const masterVolumeRef = useRef(1);
  const volumeBeforeMuteRef = useRef(1);
  const mutedRef = useRef(false);
  const busGainRef = useRef<BusGains>({ A: 0, B: 0 });
  const busUrlRef = useRef<Record<Bus, string>>({ A: "", B: "" });
  const audioContextRef = useRef<AudioContext | null>(null);
  const masterGainRef = useRef<GainNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const peakMeterBufferRef = useRef<Float32Array | null>(null);
  const graphsRef = useRef<Partial<Record<Bus, BusGraph>>>({});
  const playbackStoreRef = useRef(createPlaybackStore());
  /** Incoming bus time during crossfade — keeps pad lyrics on the new track clock. */
  const lyricsPlaybackStoreRef = useRef(createPlaybackStore());
  const preloadedRef = useRef<PreloadedTrack | null>(null);
  const preloadInFlightRef = useRef<Promise<void> | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [volume, setVolumeState] = useState(1);
  const [muted, setMutedState] = useState(false);
  const [hasTrack, setHasTrack] = useState(false);
  const [isCrossfading, setIsCrossfading] = useState(false);
  const [playbackMs, setPlaybackMs] = useState(0);
  const [durationMs, setDurationMs] = useState(0);

  const setOnTrackEnded = useCallback((handler: (() => void) | null) => {
    onTrackEndedRef.current = handler;
  }, []);

  const getBus = (bus: Bus) => (bus === "A" ? audioARef.current! : audioBRef.current!);

  const ensureElements = useCallback(() => {
    if (!audioARef.current) {
      audioARef.current = new Audio();
      audioARef.current.preload = "auto";
    }
    if (!audioBRef.current) {
      audioBRef.current = new Audio();
      audioBRef.current.preload = "auto";
    }
    return { a: audioARef.current, b: audioBRef.current };
  }, []);

  const ensureAudioGraph = useCallback(() => {
    ensureElements();
    if (!audioContextRef.current) {
      const ctx = new AudioContext();
      audioContextRef.current = ctx;
      const master = ctx.createGain();
      master.gain.value = 1;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0;
      master.connect(analyser);
      analyser.connect(ctx.destination);
      masterGainRef.current = master;
      analyserRef.current = analyser;
    }
    const ctx = audioContextRef.current;
    for (const bus of ["A", "B"] as const) {
      if (graphsRef.current[bus]) continue;
      const el = getBus(bus);
      el.volume = 1;
      const source = ctx.createMediaElementSource(el);
      const normGain = ctx.createGain();
      normGain.gain.value = 1;
      const busGain = ctx.createGain();
      busGain.gain.value = busGainRef.current[bus];
      const limiter = ctx.createDynamicsCompressor();
      limiter.threshold.value = -1;
      limiter.knee.value = 0;
      limiter.ratio.value = 20;
      limiter.attack.value = 0.003;
      limiter.release.value = 0.05;
      source.connect(normGain);
      normGain.connect(busGain);
      busGain.connect(limiter);
      limiter.connect(masterGainRef.current!);
      graphsRef.current[bus] = { source, normGain, busGain, limiter };
    }
  }, [ensureElements]);

  const resumeAudioContext = useCallback(async () => {
    ensureAudioGraph();
    const ctx = audioContextRef.current;
    if (ctx?.state === "suspended") {
      await ctx.resume();
    }
  }, [ensureAudioGraph]);

  const readPlaybackMs = useCallback((): number => {
    if (crossfadeActiveRef.current) {
      const outEl = getBus(activeRef.current);
      if (outEl && Number.isFinite(outEl.currentTime) && !isAudioAtEnd(outEl)) {
        return Math.round(outEl.currentTime * 1000);
      }
      const inBus: Bus = activeRef.current === "A" ? "B" : "A";
      const incoming = getBus(inBus);
      if (incoming && Number.isFinite(incoming.currentTime)) {
        return Math.round(incoming.currentTime * 1000);
      }
    }

    const active = getBus(activeRef.current);
    if (active && !active.paused && Number.isFinite(active.currentTime)) {
      return Math.round(active.currentTime * 1000);
    }
    for (const bus of ["A", "B"] as const) {
      const el = getBus(bus);
      if (el && !el.paused && el.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        return Math.round(el.currentTime * 1000);
      }
    }
    if (active && Number.isFinite(active.currentTime)) {
      return Math.round(active.currentTime * 1000);
    }
    return playbackStoreRef.current.getSnapshot();
  }, []);

  const readLyricsPlaybackMs = useCallback((): number => {
    if (crossfadeActiveRef.current) {
      const inBus: Bus = activeRef.current === "A" ? "B" : "A";
      const incoming = getBus(inBus);
      if (incoming && Number.isFinite(incoming.currentTime)) {
        return Math.round(incoming.currentTime * 1000);
      }
    }
    return readPlaybackMs();
  }, [readPlaybackMs]);

  const syncPlaybackClock = useCallback(() => {
    const ms = readPlaybackMs();
    playbackStoreRef.current.setSnapshot(ms);
    lyricsPlaybackStoreRef.current.setSnapshot(readLyricsPlaybackMs());
    setPlaybackMs(ms);
    const el = getBus(activeRef.current);
    if (!el) return;
    if (Number.isFinite(el.duration) && el.duration > 0) {
      setDurationMs(Math.round(el.duration * 1000));
    }
    const ctx = audioContextRef.current;
    if (ctx?.state === "suspended") {
      void ctx.resume();
    }
  }, [readPlaybackMs, readLyricsPlaybackMs]);

  const alignPlaybackClock = useCallback(
    (ms: number) => {
      playbackStoreRef.current.forceSnapshot(ms);
      lyricsPlaybackStoreRef.current.forceSnapshot(ms);
      setPlaybackMs(ms);
    },
    [],
  );

  /** Both buses — timeupdate on active bus alone misses crossfade / bus switch. */
  useEffect(() => {
    if (!hasTrack) return;
    ensureElements();
    const onClock = () => syncPlaybackClock();
    const events = ["timeupdate", "seeked", "loadedmetadata", "durationchange", "play"] as const;
    const elements = [audioARef.current, audioBRef.current].filter(Boolean) as HTMLAudioElement[];
    for (const element of elements) {
      for (const event of events) {
        element.addEventListener(event, onClock);
      }
    }
    syncPlaybackClock();
    return () => {
      for (const element of elements) {
        for (const event of events) {
          element.removeEventListener(event, onClock);
        }
      }
    };
  }, [hasTrack, ensureElements, syncPlaybackClock]);

  /** rAF while playing — smooth lyric sync; poll covers background tabs. */
  useEffect(() => {
    if (!hasTrack || !isPlaying) return;
    let raf = 0;
    const tick = () => {
      syncPlaybackClock();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [hasTrack, isPlaying, syncPlaybackClock]);

  useEffect(() => {
    if (!hasTrack || !isPlaying) return;
    return schedulePlaybackPoll(syncPlaybackClock);
  }, [hasTrack, isPlaying, syncPlaybackClock]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState !== "visible") return;
      void resumeAudioContext();
      syncPlaybackClock();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [resumeAudioContext, syncPlaybackClock]);

  const applyBusVolumes = useCallback(() => {
    const scale = mutedRef.current ? 0 : perceptualToAmplitude(masterVolumeRef.current);
    const master = masterGainRef.current;
    if (master) {
      master.gain.value = scale;
    }
    const ctx = audioContextRef.current;
    if (!ctx) return;
    for (const bus of ["A", "B"] as const) {
      const graph = graphsRef.current[bus];
      if (!graph) continue;
      graph.busGain.gain.setTargetAtTime(
        busGainRef.current[bus],
        ctx.currentTime,
        0.02,
      );
    }
  }, []);

  const setNormGain = useCallback((bus: Bus, linearGain: number) => {
    const graph = graphsRef.current[bus];
    const ctx = audioContextRef.current;
    if (!graph || !ctx) return;
    graph.normGain.gain.setTargetAtTime(
      Math.max(0, Math.min(1, linearGain)),
      ctx.currentTime,
      0.08,
    );
  }, []);

  const scheduleYoutubeNormalization = useCallback(
    (bus: Bus, url: string, startMs: number, catalogGain?: number) => {
      busUrlRef.current[bus] = url;
      if (catalogGain != null) {
        seedCatalogYoutubeGain(url, catalogGain);
        setNormGain(bus, catalogGain);
        return;
      }
      setNormGain(bus, initialYoutubeGain(url, startMs));
      prefetchYoutubeLoudness(url, startMs);
      void youtubePlaybackGainForUrl(url, startMs).then((gain) => {
        if (busUrlRef.current[bus] !== url) return;
        setNormGain(bus, gain);
      });
    },
    [setNormGain],
  );

  const setBusGain = useCallback(
    (bus: Bus, gain: number) => {
      busGainRef.current[bus] = clamp01(gain);
      applyBusVolumes();
    },
    [applyBusVolumes],
  );

  const setVolume = useCallback(
    (level: number) => {
      const v = clamp01(level);
      masterVolumeRef.current = v;
      volumeBeforeMuteRef.current = v;
      if (mutedRef.current) {
        mutedRef.current = false;
        setMutedState(false);
      }
      setVolumeState(v);
      applyBusVolumes();
    },
    [applyBusVolumes],
  );

  const toggleMute = useCallback(() => {
    if (!mutedRef.current) {
      volumeBeforeMuteRef.current = masterVolumeRef.current;
      mutedRef.current = true;
      setMutedState(true);
    } else {
      const restored = clamp01(volumeBeforeMuteRef.current);
      masterVolumeRef.current = restored;
      setVolumeState(restored);
      mutedRef.current = false;
      setMutedState(false);
    }
    applyBusVolumes();
  }, [applyBusVolumes]);

  useEffect(() => {
    ensureElements();
    const onEnded = (e: Event) => {
      if (crossfadeActiveRef.current) return;
      const target = e.currentTarget as HTMLAudioElement;
      const activeEl = getBus(activeRef.current);
      if (target !== activeEl) return;
      setIsPlaying(false);
      setPlaybackMs(Math.round((activeEl.duration || activeEl.currentTime) * 1000));
      onTrackEndedRef.current?.();
    };

    const a = audioARef.current!;
    const b = audioBRef.current!;
    a.addEventListener("ended", onEnded);
    b.addEventListener("ended", onEnded);
    return () => {
      a.removeEventListener("ended", onEnded);
      b.removeEventListener("ended", onEnded);
    };
  }, [ensureElements]);

  /** Unlock audio on user gesture (call synchronously from click/touch). */
  const ensureContext = useCallback(() => {
    ensureAudioGraph();
    void resumeAudioContext();

    if (unlockedRef.current) return;

    ensureElements();
    const activeEl = getBus(activeRef.current);
    if (activeEl.src && !activeEl.paused) {
      unlockedRef.current = true;
      return;
    }

    if (!unlockAudioRef.current) {
      unlockAudioRef.current = new Audio(SILENT_WAV);
    }
    void unlockAudioRef.current
      .play()
      .then(() => {
        unlockAudioRef.current?.pause();
        unlockedRef.current = true;
      })
      .catch(() => {
        /* ignore — real play happens after load */
      });
  }, [ensureAudioGraph, ensureElements, resumeAudioContext]);

  const prepareOnBus = useCallback(
    async (
      bus: Bus,
      url: string,
      startMs: number,
      volume: number,
      epoch: number,
      catalogGain?: number,
      opts?: { forceSeek?: boolean },
    ): Promise<{ el: HTMLAudioElement; seekAfterPlayMs: number }> => {
      const el = getBus(bus);
      const deferSeek = !opts?.forceSeek && startMs > DEFER_SEEK_MS;
      const initialMs = deferSeek ? 0 : startMs;

      void warmAudioUrl(url, startMs);

      el.pause();
      setBusGain(bus, volume);
      if (el.src !== url) {
        el.src = url;
        el.load();
      }
      ensureAudioGraph();
      scheduleYoutubeNormalization(bus, url, startMs, catalogGain);
      if (epoch !== playEpochRef.current) return { el, seekAfterPlayMs: 0 };
      try {
        await waitForMetadata(el);
      } catch {
        if (!hasUsableMetadata(el) && el.readyState < HTMLMediaElement.HAVE_FUTURE_DATA) {
          throw new Error("Audio metadata timeout");
        }
      }
      if (epoch !== playEpochRef.current) return { el, seekAfterPlayMs: 0 };

      if (initialMs > 0) {
        const duration = Number.isFinite(el.duration) && el.duration > 0 ? el.duration : undefined;
        const startSec = Math.max(0, Math.min(initialMs / 1000, duration ?? initialMs / 1000));
        try {
          await seekTo(el, startSec);
        } catch {
          if (startSec > 0.5) el.currentTime = 0;
        }
      }

      if (catalogGain == null && !hasCatalogYoutubeGain(url)) {
        const gain = await Promise.race([
          youtubePlaybackGainForUrl(url, startMs),
          new Promise<null>((resolve) => {
            window.setTimeout(() => resolve(null), LOUDNESS_READY_MS);
          }),
        ]);
        if (epoch === playEpochRef.current && busUrlRef.current[bus] === url && gain != null) {
          setNormGain(bus, gain);
        }
      }

      return { el, seekAfterPlayMs: deferSeek ? startMs : 0 };
    },
    [ensureAudioGraph, scheduleYoutubeNormalization, setBusGain],
  );

  const stopCrossfadeLoop = useCallback(() => {
    if (crossfadeTimerRef.current) {
      window.clearInterval(crossfadeTimerRef.current);
      crossfadeTimerRef.current = 0;
    }
  }, []);

  const bumpPlaybackGeneration = useCallback(() => {
    stopCrossfadeLoop();
    crossfadeActiveRef.current = false;
    setIsCrossfading(false);
    playEpochRef.current += 1;
  }, [stopCrossfadeLoop]);

  const interruptPlayback = useCallback(() => {
    preloadedRef.current = null;
    bumpPlaybackGeneration();
    audioARef.current?.pause();
    audioBRef.current?.pause();
    if (audioARef.current) audioARef.current.playbackRate = 1;
    if (audioBRef.current) audioBRef.current.playbackRate = 1;
    const active = activeRef.current;
    setBusGain(active, 1);
    setBusGain(active === "A" ? "B" : "A", 0);
  }, [bumpPlaybackGeneration, stopCrossfadeLoop, setBusGain]);

  const isTrackPreloaded = useCallback((url: string, startMs: number): boolean => {
    const preloaded = preloadedRef.current;
    return Boolean(
      preloaded &&
        preloaded.url === url &&
        preloaded.startMs === startMs &&
        busUrlRef.current[preloaded.bus] === url,
    );
  }, []);

  const awaitPreloadFor = useCallback(
    async (url: string, startMs: number): Promise<boolean> => {
      if (isTrackPreloaded(url, startMs)) return true;
      if (preloadInFlightRef.current) {
        await preloadInFlightRef.current.catch(() => {});
      }
      return isTrackPreloaded(url, startMs);
    },
    [isTrackPreloaded],
  );

  const ensureSeekBeforePlay = useCallback(
    async (el: HTMLAudioElement, targetMs: number) => {
      if (targetMs <= 0) return;
      const duration =
        Number.isFinite(el.duration) && el.duration > 0 ? el.duration : undefined;
      const targetSec = Math.max(
        0,
        Math.min(targetMs / 1000, duration ?? targetMs / 1000),
      );
      if (Math.abs(el.currentTime - targetSec) < 0.35) return;
      try {
        await seekTo(el, targetSec);
      } catch {
        /* keep prepared position */
      }
    },
    [],
  );

  const preloadTrack = useCallback(
    async ({ url, startMs = 0, youtubePlaybackGain }: PreloadTrackOptions) => {
      if (preloadInFlightRef.current) {
        await preloadInFlightRef.current.catch(() => {});
        if (isTrackPreloaded(url, startMs)) return;
      }

      const run = async () => {
        const epoch = playEpochRef.current;
        ensureElements();
        ensureAudioGraph();
        activeRef.current = "A";
        const inactive = getBus("B");
        inactive.pause();
        setBusGain("B", 0);
        busUrlRef.current.A = url;

        const { seekAfterPlayMs } = await prepareOnBus(
          "A",
          url,
          startMs,
          1,
          epoch,
          youtubePlaybackGain,
          { forceSeek: true },
        );
        if (epoch !== playEpochRef.current) return;

        preloadedRef.current = { url, startMs, seekAfterPlayMs, bus: "A" };
        setHasTrack(true);
        setIsPlaying(false);
        syncPlaybackClock();
      };

      const task = run().finally(() => {
        if (preloadInFlightRef.current === task) {
          preloadInFlightRef.current = null;
        }
      });
      preloadInFlightRef.current = task;
      await task;
    },
    [ensureAudioGraph, ensureElements, isTrackPreloaded, prepareOnBus, setBusGain, syncPlaybackClock],
  );

  const play = useCallback(
    async ({ url, startMs = 0, youtubePlaybackGain, onPlayStart }: PlayOptions) => {
      if (preloadInFlightRef.current) {
        await preloadInFlightRef.current.catch(() => {});
      }

      const preloaded = preloadedRef.current;
      if (
        preloaded &&
        preloaded.url === url &&
        preloaded.startMs === startMs &&
        busUrlRef.current[preloaded.bus] === url
      ) {
        const el = getBus(preloaded.bus);
        if (hasUsableMetadata(el)) {
          const epoch = playEpochRef.current;
          preloadedRef.current = null;
          ensureAudioGraph();
          await resumeAudioContext();
          activeRef.current = preloaded.bus;
          setBusGain(preloaded.bus, 1);
          setBusGain(preloaded.bus === "A" ? "B" : "A", 0);

          await ensureSeekBeforePlay(
            el,
            preloaded.seekAfterPlayMs > 0 ? preloaded.seekAfterPlayMs : preloaded.startMs,
          );

          try {
            await el.play();
          } catch (err) {
            throw err instanceof Error ? err : new Error("Audio play failed");
          }
          if (epoch !== playEpochRef.current) {
            el.pause();
            return;
          }

          el.playbackRate = 1;
          unlockedRef.current = true;
          setHasTrack(true);
          setIsPlaying(true);
          onPlayStart?.();
          syncPlaybackClock();
          return;
        }
      }

      bumpPlaybackGeneration();
      const epoch = playEpochRef.current;
      ensureElements();
      ensureAudioGraph();
      await resumeAudioContext();
      activeRef.current = "A";
      const inactive = getBus("B");
      inactive.pause();
      setBusGain("B", 0);

      const { el, seekAfterPlayMs } = await prepareOnBus(
        "A",
        url,
        startMs,
        1,
        epoch,
        youtubePlaybackGain,
        { forceSeek: true },
      );
      if (epoch !== playEpochRef.current) return;

      await ensureSeekBeforePlay(el, seekAfterPlayMs > 0 ? seekAfterPlayMs : startMs);

      try {
        await el.play();
      } catch (err) {
        throw err instanceof Error ? err : new Error("Audio play failed");
      }
      if (epoch !== playEpochRef.current) {
        el.pause();
        return;
      }

      el.playbackRate = 1;
      unlockedRef.current = true;
      setHasTrack(true);
      setIsPlaying(true);
      onPlayStart?.();
      syncPlaybackClock();
    },
    [ensureAudioGraph, ensureElements, ensureSeekBeforePlay, prepareOnBus, resumeAudioContext, setBusGain, syncPlaybackClock],
  );

  const crossfadeTo = useCallback(
    async ({
      url,
      startMs = 0,
      youtubePlaybackGain,
      plan,
      onCrossfadeStart,
    }: CrossfadePlayOptions) => {
      bumpPlaybackGeneration();
      const epoch = playEpochRef.current;
      crossfadeActiveRef.current = true;
      setIsCrossfading(true);
      ensureElements();
      ensureAudioGraph();
      await resumeAudioContext();

      const outBus = activeRef.current;
      const inBus: Bus = outBus === "A" ? "B" : "A";
      const outEl = getBus(outBus);

      // Never resume a finished track — HTMLMediaElement.play() restarts from 0.
      if (outEl.src && outEl.paused && !isAudioAtEnd(outEl)) {
        try {
          await outEl.play();
        } catch {
          /* outgoing may have ended */
        }
      }

      const { el: incoming, seekAfterPlayMs } = await prepareOnBus(
        inBus,
        url,
        startMs,
        0,
        epoch,
        youtubePlaybackGain,
        { forceSeek: true },
      );
      if (epoch !== playEpochRef.current) return;

      incoming.playbackRate = plan.playbackRateStart;
      setBusGain(inBus, 0);
      outEl.playbackRate = 1;

      await ensureSeekBeforePlay(
        incoming,
        seekAfterPlayMs > 0 ? seekAfterPlayMs : startMs,
      );

      try {
        await incoming.play();
      } catch (err) {
        throw err instanceof Error ? err : new Error("Audio play failed");
      }
      if (epoch !== playEpochRef.current) {
        incoming.pause();
        return;
      }

      const fadeMs = Math.max(600, plan.crossfadeMs);
      onCrossfadeStart?.();
      try {
        await new Promise<void>((resolve, reject) => {
          const startedAt = performance.now();

          const step = () => {
            if (epoch !== playEpochRef.current) {
              stopCrossfadeLoop();
              resolve();
              return;
            }

            const progress = Math.min(1, (performance.now() - startedAt) / fadeMs);
            setBusGain(inBus, fadeInGain(progress, plan.curve));
            setBusGain(outBus, fadeOutGain(progress, plan.curve));
            incoming.playbackRate = lerp(
              plan.playbackRateStart,
              plan.playbackRateEnd,
              progress,
            );
            outEl.playbackRate = lerp(1, plan.playbackRateOutEnd, progress);

            if (progress >= 1) {
              stopCrossfadeLoop();
              outEl.pause();
              setBusGain(outBus, 0);
              outEl.playbackRate = 1;
              setBusGain(inBus, 1);
              incoming.playbackRate = plan.playbackRateEnd;
              activeRef.current = inBus;
              unlockedRef.current = true;
              setHasTrack(true);
              setIsPlaying(!incoming.paused);
              syncPlaybackClock();
              resolve();
            } else {
              syncPlaybackClock();
            }
          };

          try {
            step();
            crossfadeTimerRef.current = window.setInterval(
              step,
              BACKGROUND_INTERVAL_MS,
            );
          } catch (e) {
            reject(e instanceof Error ? e : new Error("Crossfade failed"));
          }
        });
      } finally {
        if (epoch === playEpochRef.current) {
          crossfadeActiveRef.current = false;
          setIsCrossfading(false);
        }
      }
    },
    [
      bumpPlaybackGeneration,
      ensureAudioGraph,
      ensureElements,
      ensureSeekBeforePlay,
      prepareOnBus,
      resumeAudioContext,
      setBusGain,
      stopCrossfadeLoop,
      syncPlaybackClock,
    ],
  );

  const activeEl = () => getBus(activeRef.current);

  const pause = useCallback(() => {
    const el = activeEl();
    if (!el || el.paused) return;
    el.pause();
    setIsPlaying(false);
  }, []);

  const resume = useCallback(async () => {
    const el = activeEl();
    if (!el || !hasTrack) return;
    ensureAudioGraph();
    await resumeAudioContext();
    await el.play();
    setIsPlaying(true);
  }, [ensureAudioGraph, hasTrack, resumeAudioContext]);

  const togglePlayPause = useCallback(async () => {
    if (isPlaying) {
      pause();
      return;
    }
    await resume();
  }, [isPlaying, pause, resume]);

  const rewind = useCallback(async () => {
    const el = activeEl();
    if (!el) return;
    el.currentTime = 0;
    syncPlaybackClock();
    if (el.paused) await el.play();
    setIsPlaying(true);
  }, [syncPlaybackClock]);

  const samplePlaybackLinearPeak = useCallback((): number => {
    const analyser = analyserRef.current;
    if (!analyser) return 0;
    if (!peakMeterBufferRef.current || peakMeterBufferRef.current.length !== analyser.fftSize) {
      peakMeterBufferRef.current = new Float32Array(analyser.fftSize);
    }
    return sampleAnalyserLinearPeak(analyser, peakMeterBufferRef.current);
  }, []);

  const seekToMs = useCallback(
    async (ms: number) => {
      const el = activeEl();
      if (!el || !hasTrack) return;
      ensureAudioGraph();
      await resumeAudioContext();
      const duration =
        Number.isFinite(el.duration) && el.duration > 0 ? el.duration : undefined;
      const targetSec = Math.max(0, Math.min(ms / 1000, duration ?? ms / 1000));
      await seekTo(el, targetSec);
      syncPlaybackClock();
      if (el.paused) {
        try {
          await el.play();
          setIsPlaying(true);
        } catch {
          /* user gesture may be required */
        }
      }
    },
    [ensureAudioGraph, hasTrack, resumeAudioContext, syncPlaybackClock],
  );

  return {
    play,
    crossfadeTo,
    preloadTrack,
    awaitPreloadFor,
    isTrackPreloaded,
    interruptPlayback,
    bumpPlaybackGeneration,
    pause,
    resume,
    togglePlayPause,
    rewind,
    seekToMs,
    alignPlaybackClock,
    syncPlaybackClock,
    ensureContext,
    setOnTrackEnded,
    isPlaying,
    hasTrack,
    isCrossfading,
    playbackMs,
    playbackStore: playbackStoreRef.current as PlaybackStore,
    lyricsPlaybackStore: lyricsPlaybackStoreRef.current as PlaybackStore,
    durationMs,
    volume,
    muted,
    setVolume,
    toggleMute,
    samplePlaybackLinearPeak,
  };
}
