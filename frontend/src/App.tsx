import { useCallback, useEffect, useRef, useState } from "react";
import { EmotionPadHandle } from "./components/EmotionPad";
import { FluidEmotionPad, FLUID_PAD_WRAPPER_PX } from "./components/FluidEmotionPad";
import { DevPanelsDock } from "./components/DevPanelsDock";
import { LandingIntro } from "./components/LandingIntro";
import { FeatureTipToast } from "./components/FeatureTipToast";
import { PostPlayHint, dismissPostPlayHint } from "./components/PostPlayHint";
import { useFeatureTips } from "./hooks/useFeatureTips";
import { useMatchesHighlight } from "./hooks/useMatchesHighlight";
import { useTimelineDockHint } from "./hooks/useTimelineDockHint";
import { MoonyAboutPanel } from "./components/info/MoonyAboutPanel";
import { MoonyApiPanel } from "./components/info/MoonyApiPanel";
import { TopInfoNav, type InfoPanel } from "./components/info/TopInfoNav";
import { MatchesGearButton } from "./components/MatchesGearButton";
import { SegmentTimelinePlayer } from "./components/SegmentTimelinePlayer";
import { PlaybackControls } from "./components/PlaybackControls";
import { LyricsScroller } from "./components/LyricsScroller";
import {
  api,
  MatchResponse,
  PrefetchCandidate,
  PrefetchResponse,
  trackAudioUrl,
  type TrackTimeline,
} from "./lib/api";
import { EMOTION_ZONES, formatCatalogMood, nearestEmotionZone, pickRandomSessionSeedTarget } from "./lib/emotions";
import {
  buildMatchFromPrefetch,
  buildMatchFromPrefetchAtEntry,
  pickPrefetchForPadTarget,
  type TrackChangeReason,
} from "./lib/trackNavigation";
import {
  earlySameMoodHandoffMs,
  isInSameMoodHandoffZone,
  isOnLastSegment,
  needsEarlySameMoodHandoff,
  needsHandoffTimeline,
  needsTimelineEnrich,
  segmentAtTime,
  segmentCrossedBetween,
  segmentIndexAtTime,
  trackDurationMs,
  type MatchTimelineRow,
  type TimelineView,
} from "./lib/segments";
import {
  pruneEmbeddingPenalties,
  registerEarlyRejectPenalty,
  type EmbeddingPenaltyRange,
} from "./lib/embeddingPenalties";
import { moodMonitor, type MoodTrackEntry } from "./lib/moodMonitor";
import { errorMessage, isAbortError } from "./lib/abortError";
import { resolveCrossfadeStartForHandoff } from "./lib/crossfadeTiming";
import { crossfadeFromMatch, estimateSameMoodFadeMs } from "./lib/motion";
import { waitUntilPlaybackMs } from "./lib/waitPlayback";
import { seedCatalogYoutubeGain } from "./lib/analyzeTrackLoudness";
import { useAudioEngine } from "./hooks/useAudioEngine";
import { useTrackLyrics } from "./hooks/useTrackLyrics";
import { usePadLyricsDisplay } from "./hooks/usePadLyricsDisplay";
import { hasSyncedLyrics } from "./lib/lyricsSync";
import {
  prefetchLyricsFromPrefetchResponse,
} from "./lib/lyricsCache";

const MOTION_POLL_MS = 1200;
/** Min pad movement (V/A space) before auto-matching while playing. */
const PAD_MATCH_MIN_DELTA = 0.12;
const APPLY_MATCH_TIMEOUT_MS = 45_000;
/** First play: fail fast if the API does not respond. */
const FIRST_MATCH_TIMEOUT_MS = 15_000;
const PREFETCH_MIN_INTERVAL_MS = 6_000;
/** Target mood (pad zone) unchanged → deep prefetch (mood_distribution ≥ 0.5). */
const TARGET_MOOD_STABLE_MS = 30_000;
const TARGET_MOOD_PREFETCH_POLL_MS = 5_000;
const TARGET_ZONE_NO_MATCH_NOTE_MS = 5_000;
/** Block last-segment handoff until timeline + playhead match the new track. */
const TRACK_HANDOFF_SETTLE_MS = 3_000;

function syncedTimelineForTrack(
  trackId: string,
  timeline: TrackTimeline | null,
): TrackTimeline | null {
  return timeline?.track_id === trackId ? timeline : null;
}

function prefetchCandidateToRow(emotion: string, c: PrefetchCandidate): MatchTimelineRow {
  const seg = c.segment;
  const entryMs = c.audio_start_ms;
  const tStart = seg.t_start ?? entryMs;
  const tEnd = Math.max(seg.t_end, entryMs + 15_000);
  return {
    track_id: c.track_id,
    title: c.title,
    artist: c.artist,
    bpm: c.bpm,
    duration_ms: tEnd + 60_000,
    segments: [
      {
        t_start: tStart,
        t_end: tEnd,
        v: seg.v,
        ar: seg.ar,
        label: seg.label,
        emotion_label: seg.emotion_label,
      },
    ],
    emotion,
    entryMs,
  };
}

function firstUnplayedPrefetchCandidate(
  list: PrefetchCandidate[] | undefined,
  played: ReadonlySet<string>,
  alsoExclude?: string,
): PrefetchCandidate | undefined {
  if (!list?.length) return undefined;
  return list.find(
    (c) => !played.has(c.track_id) && (!alsoExclude || c.track_id !== alsoExclude),
  );
}

function findPrefetchCandidate(
  intents: PrefetchResponse["intents"],
  trackId: string,
): PrefetchCandidate | undefined {
  for (const list of Object.values(intents)) {
    const hit = list?.find((c) => c.track_id === trackId);
    if (hit) return hit;
  }
  return undefined;
}

function quickMatchRowsFromIntents(
  intents: PrefetchResponse["intents"],
  played: ReadonlySet<string>,
): MatchTimelineRow[] {
  const rows: MatchTimelineRow[] = [];
  for (const zone of EMOTION_ZONES) {
    const candidate = firstUnplayedPrefetchCandidate(
      intents[String(zone.intent)],
      played,
    );
    if (candidate) {
      rows.push(prefetchCandidateToRow(zone.name, candidate));
    }
  }
  return rows;
}

function mergePrefetchIntentIntoMatchRows(
  emotion: string,
  candidates: PrefetchCandidate[],
  played: ReadonlySet<string>,
): MatchTimelineRow | null {
  const candidate = firstUnplayedPrefetchCandidate(candidates, played);
  return candidate ? prefetchCandidateToRow(emotion, candidate) : null;
}

function isBetterPrefetchCandidate(
  prev: PrefetchCandidate | undefined,
  next: PrefetchCandidate | undefined,
): boolean {
  if (!next) return false;
  if (!prev) return true;
  return (
    next.track_id !== prev.track_id || next.audio_start_ms !== prev.audio_start_ms
  );
}

type TargetZonePrefetchUiStatus = "fetching" | "no_better_match";

/** Minimal timeline so match rows render before /tracks/.../timeline returns. */
function stubTimelineFromMatch(match: MatchResponse): TrackTimeline {
  const seg = match.segment;
  const start = seg.t_start ?? match.start_ms;
  const end = Math.max(seg.t_end, start + 30_000);
  return {
    track_id: match.track_id,
    title: match.title,
    artist: match.artist,
    bpm: match.bpm,
    duration_ms: end + 60_000,
    segments: [
      {
        t_start: start,
        t_end: end,
        v: seg.v,
        ar: seg.ar,
        label: seg.label,
        emotion_label: seg.emotion_label,
      },
    ],
  };
}

function matchRowKey(emotion: string, trackId: string): string {
  return `${emotion}:${trackId}`;
}

function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => {
      window.setTimeout(() => reject(new Error(message)), ms);
    }),
  ]);
}

export default function App() {
  const [lyricsMode, setLyricsMode] = useState<string>("off");
  const lyricsModeRef = useRef(lyricsMode);
  lyricsModeRef.current = lyricsMode;
  const [position, setPosition] = useState({ v: 0, ar: 0 });
  const [direction, setDirection] = useState({ v: 0, ar: 0 });
  const [nowPlaying, setNowPlaying] = useState<MatchResponse | null>(null);
  const [prefetch, setPrefetch] = useState<PrefetchResponse["intents"] | null>(null);
  const [targetZonePrefetchNote, setTargetZonePrefetchNote] = useState<{
    zone: string;
    status: TargetZonePrefetchUiStatus;
  } | null>(null);
  const [currentTimeline, setCurrentTimeline] = useState<TrackTimeline | null>(null);
  const [matchRows, setMatchRows] = useState<MatchTimelineRow[]>([]);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [switchingTrack, setSwitchingTrack] = useState(false);
  const [trackPlayCount, setTrackPlayCount] = useState<number | null>(null);
  const [playStatsEnabled, setPlayStatsEnabled] = useState(false);
  const [showSyncedMatches, setShowSyncedMatches] = useState(false);
  const [infoPanel, setInfoPanel] = useState<InfoPanel | null>(null);
  const { currentTip: featureTip, dismissCurrent: dismissFeatureTip } = useFeatureTips(Boolean(nowPlaying));
  const { highlight: matchesHighlight, markDiscovered: markMatchesDiscovered } = useMatchesHighlight(
    Boolean(nowPlaying),
    showSyncedMatches,
  );
  const { showTimelineHint, dismissTimelineHint } = useTimelineDockHint(Boolean(nowPlaying));
  const audio = useAudioEngine();
  const prefetchLyricsIfEnabled = useCallback(
    (
      result: { intents?: PrefetchResponse["intents"]; l2?: PrefetchResponse["l2"] },
      extraTrackIds: string[] = [],
      signal?: AbortSignal,
    ) => {
      if (lyricsModeRef.current !== "musixmatch") return;
      prefetchLyricsFromPrefetchResponse(result, extraTrackIds, signal);
    },
    [],
  );
  const trackLyrics = useTrackLyrics(
    nowPlaying?.track_id,
    lyricsMode === "musixmatch" && Boolean(nowPlaying?.track_id),
  );
  const padLyrics = usePadLyricsDisplay(nowPlaying, trackLyrics, lyricsMode);
  const padLyricsReadyForTrack = Boolean(
    nowPlaying &&
      !trackLyrics.loading &&
      trackLyrics.lines.length > 0 &&
      hasSyncedLyrics(trackLyrics.source, trackLyrics.lines),
  );
  const padLyricsSyncPlayback = Boolean(
    padLyrics &&
      nowPlaying &&
      padLyrics.trackId === nowPlaying.track_id &&
      padLyricsReadyForTrack &&
      !audio.isCrossfading,
  );
  const padRef = useRef<EmotionPadHandle>(null);
  const dragRef = useRef(false);
  /** Track IDs already started this browser session — each song at most once. */
  const playedTrackIdsRef = useRef<Set<string>>(new Set());
  /** Opener mood (Calm / Joy / Energy) — fixed for this page load. */
  const sessionSeedTargetRef = useRef(pickRandomSessionSeedTarget());
  const positionRef = useRef(position);
  const targetRef = useRef(position);
  const directionRef = useRef(direction);
  directionRef.current = direction;
  const sessionAbortRef = useRef<AbortController | null>(null);
  const timelineLoadSeqRef = useRef(0);
  const enrichedRowsRef = useRef(new Set<string>());
  const switchingTrackRef = useRef(false);
  const prefetchInFlightRef = useRef(0);
  const lastPrefetchAtRef = useRef(0);
  const stablePadMoodRef = useRef<{ zone: string; sinceMs: number } | null>(null);
  const stablePadMoodTrackIdRef = useRef<string | null>(null);
  const lastSameMoodPrefetchAtRef = useRef(0);
  const sameMoodAbortRef = useRef<AbortController | null>(null);
  const sameMoodPrefetchInFlightRef = useRef(false);
  /** Drag on pad — freeze stability clock until release (time on pad does not count). */
  const sameMoodDragPausedAtRef = useRef<number | null>(null);
  const playbackMsRef = useRef(0);
  const embeddingPenaltyRangesRef = useRef<EmbeddingPenaltyRange[]>([]);
  const trackPlayStartSessionMsRef = useRef<number | null>(null);
  const trackEntryMsRef = useRef(0);
  const lastLiveMoodRef = useRef<{ v: number; ar: number } | null>(null);
  const lastPrefetchPlaybackMsRef = useRef(0);
  /** Mutex: at most one track change (A/B/C/…) at a time. */
  const trackChangeInFlightRef = useRef(false);
  const lastSegmentIdxRef = useRef(-1);
  const lastSegmentPlaybackMsRef = useRef<number | null>(null);
  /** One same-mood crossfade handoff per track when entering the last segment. */
  const lastSegmentHandoffTrackRef = useRef<string | null>(null);
  /** Blocks auto segment/handoff effects while the user seeks via timeline click. */
  const manualSegmentSeekRef = useRef<number | null>(null);
  const handoffAbortRef = useRef<AbortController | null>(null);
  /** Earliest time last-segment handoff may run after a track / timeline change. */
  const trackHandoffAllowedAfterRef = useRef(0);
  /** Set before natural last-segment handoff; cleared when next track applies or handoff aborts. */
  const naturalHandoffFromTrackRef = useRef<string | null>(null);
  const showSyncedMatchesRef = useRef(showSyncedMatches);
  const matchSeqRef = useRef(0);
  const matchingRef = useRef(false);
  const lastMatchedTargetRef = useRef({ v: 0, ar: 0 });
  const lastPadMatchAtRef = useRef(0);
  const sessionPlayStartedRef = useRef(false);
  const padDragStartZoneRef = useRef<string | null>(null);
  /** Handoff /match isolated from session abort when the track changes. */
  const nowPlayingRef = useRef(nowPlaying);
  const matchRowsRef = useRef(matchRows);
  const prefetchRef = useRef(prefetch);
  const currentTimelineRef = useRef(currentTimeline);
  nowPlayingRef.current = nowPlaying;
  currentTimelineRef.current = currentTimeline;
  matchRowsRef.current = matchRows;
  prefetchRef.current = prefetch;
  switchingTrackRef.current = switchingTrack;
  showSyncedMatchesRef.current = showSyncedMatches;

  const timelineView: TimelineView | null = nowPlaying
    ? {
        current: currentTimeline ?? stubTimelineFromMatch(nowPlaying),
        matches: showSyncedMatches ? matchRows : [],
      }
    : null;

  positionRef.current = position;
  playbackMsRef.current = audio.playbackMs;

  useEffect(() => {
    showSyncedMatchesRef.current = showSyncedMatches;
  }, [showSyncedMatches]);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setLyricsMode(String(h.catalog.lyrics_mode ?? "off"));
        setPlayStatsEnabled(Boolean(h.play_stats?.enabled));
      })
      .catch(() => {});
  }, []);

  const padMatchPosition = useCallback(() => {
    return padRef.current?.getUserTarget() ?? targetRef.current;
  }, []);

  /** After first Play: start mood monitoring for the session. */
  useEffect(() => {
    if (!nowPlaying || sessionPlayStartedRef.current) return;
    sessionPlayStartedRef.current = true;
    const pos = padMatchPosition();
    if (!moodMonitor.isSessionActive()) {
      moodMonitor.sessionStart(pos.v, pos.ar);
    }
  }, [nowPlaying, padMatchPosition]);

  useEffect(() => {
    moodMonitor.setPlaybackActive(Boolean(nowPlaying && audio.isPlaying));
  }, [nowPlaying, audio.isPlaying]);

  const abortSameMoodPrefetch = useCallback(() => {
    sameMoodAbortRef.current?.abort("same-mood-cancel");
    sameMoodAbortRef.current = null;
  }, []);

  const resetSameMoodStability = useCallback(
    (opts?: { v: number; ar: number; trackId?: string }) => {
      abortSameMoodPrefetch();
      lastSameMoodPrefetchAtRef.current = 0;
      sameMoodDragPausedAtRef.current = null;
      setTargetZonePrefetchNote(null);
      const trackId = opts?.trackId ?? nowPlayingRef.current?.track_id ?? null;
      stablePadMoodTrackIdRef.current = trackId;
      if (opts && trackId) {
        stablePadMoodRef.current = {
          zone: nearestEmotionZone(opts.v, opts.ar).name,
          sinceMs: Date.now(),
        };
      } else {
        stablePadMoodRef.current = null;
      }
    },
    [abortSameMoodPrefetch],
  );

  const pauseSameMoodStabilityClock = useCallback(() => {
    abortSameMoodPrefetch();
    lastSameMoodPrefetchAtRef.current = 0;
    if (sameMoodDragPausedAtRef.current == null) {
      sameMoodDragPausedAtRef.current = Date.now();
    }
  }, [abortSameMoodPrefetch]);

  const resumeSameMoodStabilityClock = useCallback(() => {
    const pausedAt = sameMoodDragPausedAtRef.current;
    if (pausedAt != null && stablePadMoodRef.current) {
      const dragMs = Date.now() - pausedAt;
      stablePadMoodRef.current = {
        ...stablePadMoodRef.current,
        sinceMs: stablePadMoodRef.current.sinceMs + dragMs,
      };
    }
    sameMoodDragPausedAtRef.current = null;
  }, []);

  const updateStablePadMood = useCallback(
    (v: number, ar: number) => {
      const trackId = nowPlayingRef.current?.track_id;
      if (!trackId) return;

      const zone = nearestEmotionZone(v, ar).name;
      if (stablePadMoodTrackIdRef.current !== trackId) {
        abortSameMoodPrefetch();
        stablePadMoodTrackIdRef.current = trackId;
        stablePadMoodRef.current = { zone, sinceMs: Date.now() };
        lastSameMoodPrefetchAtRef.current = 0;
        return;
      }

      const prev = stablePadMoodRef.current;
      if (!prev || prev.zone !== zone) {
        abortSameMoodPrefetch();
        stablePadMoodRef.current = { zone, sinceMs: Date.now() };
        lastSameMoodPrefetchAtRef.current = 0;
      }
    },
    [abortSameMoodPrefetch],
  );

  const onPositionChange = useCallback(
    (v: number, ar: number) => {
      const next = { v, ar };
      targetRef.current = next;
      updateStablePadMood(v, ar);
      moodMonitor.onPadPosition(v, ar);
      setPosition((prev) => {
        const dir = { v: v - prev.v, ar: ar - prev.ar };
        directionRef.current = dir;
        setDirection(dir);
        return next;
      });
    },
    [updateStablePadMood],
  );

  const enrichMatchRow = useCallback(
    async (
      emotion: string,
      trackId: string,
      entryMs: number,
      signal?: AbortSignal,
    ) => {
      const key = matchRowKey(emotion, trackId);
      if (enrichedRowsRef.current.has(key)) return;
      try {
        const row = await api.trackTimeline(trackId, signal, { motionPreview: true });
        if (signal?.aborted) return;
        enrichedRowsRef.current.add(key);
        setMatchRows((prev) =>
          prev.map((r) =>
            r.emotion === emotion && r.track_id === trackId
              ? { ...row, emotion, entryMs }
              : r,
          ),
        );
      } catch (e) {
        if (isAbortError(e) || signal?.aborted) return;
      }
    },
    [],
  );

  /** Load full catalog timelines for prefetch rows (all segments, motion preview). */
  const loadFullMatchRows = useCallback(
    async (rows: MatchTimelineRow[], signal?: AbortSignal): Promise<MatchTimelineRow[]> => {
      return Promise.all(
        rows.map(async (row) => {
          const key = matchRowKey(row.emotion, row.track_id);
          if (enrichedRowsRef.current.has(key) && row.segments.length > 1) {
            return row;
          }
          try {
            const timeline = await api.trackTimeline(row.track_id, signal, {
              motionPreview: true,
            });
            if (signal?.aborted) return row;
            enrichedRowsRef.current.add(key);
            return { ...timeline, emotion: row.emotion, entryMs: row.entryMs };
          } catch (e) {
            if (isAbortError(e)) throw e;
            return row;
          }
        }),
      );
    },
    [],
  );

  const embeddingPenaltiesForApi = useCallback(
    () => pruneEmbeddingPenalties(embeddingPenaltyRangesRef.current),
    [],
  );

  const registerEarlyRejectIfNeeded = useCallback(() => {
    const playing = nowPlayingRef.current;
    if (!playing || trackPlayStartSessionMsRef.current == null) return;
    const listenedMs =
      moodMonitor.getElapsedMs() - trackPlayStartSessionMsRef.current;
    embeddingPenaltyRangesRef.current = registerEarlyRejectPenalty(
      embeddingPenaltyRangesRef.current,
      {
        track_id: playing.track_id,
        track_entry_ms: trackEntryMsRef.current,
        listened_ms: listenedMs,
      },
    );
  }, []);

  const loadTrackTimeline = useCallback((match: MatchResponse) => {
    const trackId = match.track_id;
    const seq = ++timelineLoadSeqRef.current;
    setCurrentTimeline(stubTimelineFromMatch(match));

    const applyIfCurrent = (timeline: TrackTimeline) => {
      if (seq !== timelineLoadSeqRef.current) return;
      if (nowPlayingRef.current?.track_id !== trackId) return;
      setCurrentTimeline(timeline);
      trackHandoffAllowedAfterRef.current = Date.now() + TRACK_HANDOFF_SETTLE_MS;
      if (timeline.segments.length > 0) {
        lastSegmentIdxRef.current = segmentIndexAtTime(
          timeline.segments,
          playbackMsRef.current,
        );
      }
    };

    void (async () => {
      try {
        // Phase 1: all MOSS segments immediately (do not wait on motion preview).
        const segmentsTimeline = await api.trackTimeline(trackId, undefined, {
          motionPreview: false,
        });
        applyIfCurrent(segmentsTimeline);

        if (!needsTimelineEnrich(segmentsTimeline)) return;

        // Phase 2: motion curve overlay when available.
        const enriched = await api.trackTimeline(trackId, undefined, {
          motionPreview: true,
        });
        applyIfCurrent(enriched);
      } catch (e) {
        if (isAbortError(e)) return;
        if (seq !== timelineLoadSeqRef.current) return;
        if (nowPlayingRef.current?.track_id !== trackId) return;
        applyIfCurrent(stubTimelineFromMatch(match));
      }
    })();
  }, []);

  const refreshPrefetchFor = useCallback(
    async (
      track: MatchResponse,
      pos: { v: number; ar: number },
      playbackMs: number,
      opts?: { urgent?: boolean; signal?: AbortSignal },
    ) => {
      const signal = opts?.signal;
      const now = Date.now();
      const buildMatchUi = showSyncedMatchesRef.current;
      const hasCached =
        (buildMatchUi && matchRowsRef.current.length > 0) ||
        (!buildMatchUi && prefetchRef.current && Object.keys(prefetchRef.current).length > 0);
      if (
        !opts?.urgent &&
        hasCached &&
        now - lastPrefetchAtRef.current < PREFETCH_MIN_INTERVAL_MS
      ) {
        return;
      }
      lastPrefetchAtRef.current = now;

      prefetchInFlightRef.current += 1;
      if (buildMatchUi && matchRowsRef.current.length === 0) setMatchesLoading(true);
      try {
        const result = await api.prefetch(
          {
            current_track_id: track.track_id,
            t_ms: playbackMs,
            position: pos,
            bpm_current: track.bpm,
            depth: 1,
            exclude_ids: [...playedTrackIdsRef.current],
            embedding_penalties: embeddingPenaltiesForApi(),
          },
          signal,
        );
        if (signal?.aborted || nowPlayingRef.current?.track_id !== track.track_id) return;

        setPrefetch(result.intents);
        for (const list of Object.values(result.intents)) {
          for (const c of list) {
            if (c.youtube_playback_gain != null) {
              seedCatalogYoutubeGain(c.audio_url, c.youtube_playback_gain);
            }
          }
        }

        prefetchLyricsIfEnabled(
          result,
          lyricsModeRef.current === "musixmatch" ? [track.track_id] : [],
          signal,
        );

        if (!showSyncedMatchesRef.current) return;

        const quick = quickMatchRowsFromIntents(result.intents, playedTrackIdsRef.current);
        if (quick.length > 0) {
          try {
            const full = await loadFullMatchRows(quick, signal);
            if (!signal?.aborted && nowPlayingRef.current?.track_id === track.track_id) {
              setMatchRows(full);
            }
          } catch (e) {
            if (isAbortError(e)) return;
            if (!signal?.aborted && nowPlayingRef.current?.track_id === track.track_id) {
              setMatchRows(quick);
            }
          }
        }
      } catch (e) {
        if (isAbortError(e) || signal?.aborted) return;
        if (nowPlayingRef.current?.track_id !== track.track_id) return;
        if (showSyncedMatchesRef.current && matchRowsRef.current.length === 0) {
          const msg = errorMessage(e, "Prefetch failed");
          if (msg) setError(msg);
        }
      } finally {
        prefetchInFlightRef.current = Math.max(0, prefetchInFlightRef.current - 1);
        if (prefetchInFlightRef.current === 0) {
          setMatchesLoading(false);
        }
      }
    },
    [embeddingPenaltiesForApi, loadFullMatchRows, prefetchLyricsIfEnabled],
  );

  /** Overwrite pad-zone prefetch (e.g. Joy) with deep target-mood candidates (≥0.5). */
  const applyDeepPadZonePrefetch = useCallback(
    (zoneName: string, intentKey: string, candidates: PrefetchCandidate[]) => {
      setPrefetch((prev) => ({
        ...(prev ?? {}),
        [intentKey]: candidates,
      }));
      for (const c of candidates) {
        if (c.youtube_playback_gain != null) {
          seedCatalogYoutubeGain(c.audio_url, c.youtube_playback_gain);
        }
      }
      prefetchLyricsIfEnabled({ intents: { [intentKey]: candidates } });

      if (!showSyncedMatchesRef.current) return;
      const row = mergePrefetchIntentIntoMatchRows(
        zoneName,
        candidates,
        playedTrackIdsRef.current,
      );
      if (!row) return;

      enrichedRowsRef.current.delete(matchRowKey(zoneName, row.track_id));
      setMatchRows((prev) => {
        const idx = prev.findIndex((r) => r.emotion === zoneName);
        if (idx < 0) return [...prev, row];
        const next = [...prev];
        next[idx] = row;
        return next;
      });
      if (needsTimelineEnrich(row)) {
        void enrichMatchRow(
          zoneName,
          row.track_id,
          row.entryMs,
          sessionAbortRef.current?.signal,
        );
      }
    },
    [enrichMatchRow, prefetchLyricsIfEnabled],
  );

  /** Target mood stable 30s → refresh that pad zone's prefetch (mood_distribution ≥ 0.5). */
  const refreshTargetMoodPrefetch = useCallback(async () => {
    const track = nowPlayingRef.current;
    if (
      !track ||
      dragRef.current ||
      sameMoodDragPausedAtRef.current != null ||
      trackChangeInFlightRef.current ||
      sameMoodPrefetchInFlightRef.current ||
      manualSegmentSeekRef.current !== null
    ) {
      return;
    }
    if (stablePadMoodTrackIdRef.current !== track.track_id) return;

    const stable = stablePadMoodRef.current;
    if (!stable) return;
    const zone = EMOTION_ZONES.find((z) => z.name === stable.zone);
    if (!zone) return;

    abortSameMoodPrefetch();
    const controller = new AbortController();
    sameMoodAbortRef.current = controller;
    const trackId = track.track_id;
    const intentKey = String(zone.intent);
    const prevTop = firstUnplayedPrefetchCandidate(
      prefetchRef.current?.[intentKey],
      playedTrackIdsRef.current,
    );
    sameMoodPrefetchInFlightRef.current = true;
    setTargetZonePrefetchNote({ zone: zone.name, status: "fetching" });

    try {
      const result = await api.prefetch(
        {
          current_track_id: trackId,
          t_ms: playbackMsRef.current,
          position: padMatchPosition(),
          bpm_current: track.bpm,
          depth: 1,
          exclude_ids: [...playedTrackIdsRef.current],
          single_intent: zone.intent,
          restrict_mood_share: true,
          embedding_penalties: embeddingPenaltiesForApi(),
        },
        controller.signal,
      );
      if (
        controller.signal.aborted ||
        nowPlayingRef.current?.track_id !== trackId
      ) {
        setTargetZonePrefetchNote(null);
        return;
      }

      const candidates = result.intents[intentKey];
      const nextTop = firstUnplayedPrefetchCandidate(
        candidates,
        playedTrackIdsRef.current,
      );
      if (!isBetterPrefetchCandidate(prevTop, nextTop)) {
        setTargetZonePrefetchNote({ zone: zone.name, status: "no_better_match" });
        return;
      }

      applyDeepPadZonePrefetch(zone.name, intentKey, candidates!);
      setTargetZonePrefetchNote(null);
    } catch (e) {
      if (isAbortError(e) || controller.signal.aborted) {
        setTargetZonePrefetchNote(null);
        return;
      }
      setTargetZonePrefetchNote(null);
    } finally {
      if (sameMoodAbortRef.current === controller) {
        sameMoodAbortRef.current = null;
      }
      sameMoodPrefetchInFlightRef.current = false;
    }
  }, [abortSameMoodPrefetch, applyDeepPadZonePrefetch, padMatchPosition]);

  const applyMatch = useCallback(
    async (
      match: MatchResponse,
      seq: number,
      opts?: {
        onTransitionStart?: () => void;
      },
    ): Promise<boolean> => {
      if (seq !== matchSeqRef.current) return false;

      try {
        audio.ensureContext();
        const url = trackAudioUrl(match.track_id);
        const exit = nowPlayingRef.current?.segment
          ? { v: nowPlayingRef.current.segment.v, ar: nowPlayingRef.current.segment.ar }
          : undefined;
        const plan = crossfadeFromMatch(match, exit);
        const onStart = () => {
          audio.alignPlaybackClock(match.start_ms);
          trackEntryMsRef.current = match.start_ms;
          nowPlayingRef.current = match;
          setNowPlaying(match);
          opts?.onTransitionStart?.();
        };
        const normGain = match.youtube_playback_gain;

        if (audio.hasTrack && nowPlayingRef.current) {
          const playing = nowPlayingRef.current;
          const nowMs = playbackMsRef.current;
          const timeline =
            currentTimelineRef.current ?? stubTimelineFromMatch(playing);
          const segments = timeline.segments;
          const durationMs =
            audio.durationMs > 0
              ? audio.durationMs
              : trackDurationMs(timeline);
          const onLastSegment =
            segments.length >= 2 && isOnLastSegment(segments, nowMs);
          const inHandoffZone =
            segments.length >= 2 &&
            isInSameMoodHandoffZone(segments, nowMs, plan.crossfadeMs);
          const fadeStart = inHandoffZone
            ? null
            : resolveCrossfadeStartForHandoff({
                nowMs,
                fadeMs: plan.crossfadeMs,
                bpm: playing.bpm,
                durationMs,
                onLastSegment,
              });
          const waitMs =
            fadeStart != null && fadeStart > nowMs ? fadeStart - nowMs : 0;
          // Beat wait only while audio is advancing and the downbeat is reachable before track end.
          if (
            fadeStart != null &&
            audio.isPlaying &&
            waitMs > 0 &&
            waitMs <= 12_000
          ) {
            await waitUntilPlaybackMs(() => playbackMsRef.current, fadeStart, {
              maxWaitMs: waitMs + 800,
              isCancelled: () => {
                if (seq !== matchSeqRef.current) return true;
                const pos = playbackMsRef.current;
                if (durationMs > 0 && pos >= durationMs - 500) return true;
                return false;
              },
            });
            if (seq !== matchSeqRef.current) return false;
          }
          await withTimeout(
            audio.crossfadeTo({
              url,
              startMs: match.start_ms,
              youtubePlaybackGain: normGain,
              plan,
              onCrossfadeStart: onStart,
            }),
            APPLY_MATCH_TIMEOUT_MS,
            "Playback timed out — try again",
          );
        } else {
          audio.interruptPlayback();
          const entryFade =
            match.crossfade_ms != null && match.crossfade_ms > 0;
          await withTimeout(
            entryFade
              ? audio.crossfadeTo({
                  url,
                  startMs: match.start_ms,
                  youtubePlaybackGain: normGain,
                  plan,
                  onCrossfadeStart: onStart,
                })
              : audio.play({
                  url,
                  startMs: match.start_ms,
                  youtubePlaybackGain: normGain,
                  onPlayStart: onStart,
                }),
            APPLY_MATCH_TIMEOUT_MS,
            "Playback timed out — try again",
          );
        }
        padRef.current?.seedShadowMotion(match.segment.v, match.segment.ar);
        padRef.current?.resumePlaybackDrive();
        if (seq !== matchSeqRef.current) return false;

        nowPlayingRef.current = match;
        setNowPlaying(match);
        loadTrackTimeline(match);
        playedTrackIdsRef.current.add(match.track_id);
        if (!moodMonitor.isSessionActive()) {
          const pos = padRef.current?.getUserTarget() ?? targetRef.current;
          moodMonitor.sessionStart(pos.v, pos.ar);
        }
        moodMonitor.trackStarted({
          trackId: match.track_id,
          title: match.title,
          artist: match.artist,
          primaryMood: formatCatalogMood(match.emotion_label ?? match.segment.emotion_label),
          entryMs: match.start_ms,
          atMs: moodMonitor.getElapsedMs(),
        });
        const naturalFromTrackId = naturalHandoffFromTrackRef.current;
        if (naturalFromTrackId) {
          naturalHandoffFromTrackRef.current = null;
          const pos = padRef.current?.getUserTarget() ?? targetRef.current;
          moodMonitor.userAction("next_track", {
            v: pos.v,
            ar: pos.ar,
            detail: { fromTrackId: naturalFromTrackId, toTrackId: match.track_id },
          });
        }
        void api
          .recordPlay(match.track_id)
          .then((r) => {
            setPlayStatsEnabled(r.stats_enabled);
            if (r.stats_enabled) {
              setTrackPlayCount(r.play_count);
              moodMonitor.updateTrackPlayCount(match.track_id, r.play_count);
            }
          })
          .catch(() => {
            /* fairness works without stats; ignore network errors */
          });
        lastPrefetchPlaybackMsRef.current = match.start_ms;
        lastLiveMoodRef.current = { v: match.segment.v, ar: match.segment.ar };
        lastMatchedTargetRef.current = { ...targetRef.current };
        trackPlayStartSessionMsRef.current = moodMonitor.getElapsedMs();
        trackEntryMsRef.current = match.start_ms;
        audio.alignPlaybackClock(match.start_ms);
        prefetchLyricsIfEnabled(
          { intents: prefetchRef.current ?? {} },
          lyricsModeRef.current === "musixmatch" ? [match.track_id] : [],
        );
        return true;
      } catch (e) {
        if (!isAbortError(e)) {
          const msg = errorMessage(e, "Audio playback failed");
          if (msg) setError(msg);
        }
        padRef.current?.resumePlaybackDrive();
        throw e;
      }
    },
    [audio, loadTrackTimeline, prefetchLyricsIfEnabled],
  );

  const handoffMatchSignal = useCallback((): AbortSignal => {
    handoffAbortRef.current?.abort("handoff");
    const controller = new AbortController();
    handoffAbortRef.current = controller;
    return controller.signal;
  }, []);

  const requestMatch = useCallback(
    async (opts?: {
      force?: boolean;
      cut?: boolean;
      sessionSeed?: boolean;
      sameMoodHandoff?: boolean;
      /** Pad release / skip: search another track, not `pad_only` on the current one. */
      changeTrack?: boolean;
      /** Isolated from session abort (last-segment handoff). */
      detached?: boolean;
      suppressError?: boolean;
    }): Promise<boolean> => {
      if (matchingRef.current && !opts?.changeTrack && !opts?.force) return false;

      padRef.current?.lockFilledToIntent();
      const sessionSeed = opts?.sessionSeed ?? false;
      const target = sessionSeed ? sessionSeedTargetRef.current : padMatchPosition();
      targetRef.current = target;
      if (sessionSeed) {
        setPosition(target);
        padRef.current?.setUserTarget(target.v, target.ar);
      }
      if (
        !opts?.force &&
        nowPlayingRef.current &&
        Math.hypot(
          target.v - lastMatchedTargetRef.current.v,
          target.ar - lastMatchedTargetRef.current.ar,
        ) < PAD_MATCH_MIN_DELTA
      ) {
        return false;
      }

      const seq = ++matchSeqRef.current;
      matchingRef.current = true;
      setError(null);
      const isFirstStart = !nowPlayingRef.current;
      if (isFirstStart) setLoading(true);
      else setSwitchingTrack(true);
      try {
        const playing = nowPlayingRef.current;
        const exclude = new Set(playedTrackIdsRef.current);
        if (opts?.cut && playing) exclude.add(playing.track_id);
        const sameMoodHandoff = opts?.sameMoodHandoff ?? false;

        const matchRequest = api.match(
          {
            position: target,
            direction: directionRef.current,
            bpm_current: playing?.bpm ?? 120,
            exclude_ids: [...exclude],
            current_track_id:
              sameMoodHandoff || !opts?.cut ? playing?.track_id : undefined,
            current_t_ms:
              sameMoodHandoff || !opts?.cut
                ? playing
                  ? playbackMsRef.current
                  : undefined
                : undefined,
            pad_only: !sameMoodHandoff && !opts?.changeTrack,
            session_seed: sessionSeed,
            same_mood_handoff: sameMoodHandoff,
            embedding_penalties: embeddingPenaltiesForApi(),
          },
          opts?.detached ? handoffMatchSignal() : sessionAbortRef.current?.signal,
        );
        const match = isFirstStart
          ? await withTimeout(
              matchRequest,
              FIRST_MATCH_TIMEOUT_MS,
              "Still connecting to the Moony API. Check that the server is running, then try again.",
            )
          : await matchRequest;
        if (seq !== matchSeqRef.current) return false;
        await applyMatch(match, seq, {
          onTransitionStart: () => setSwitchingTrack(false),
        });
        return seq === matchSeqRef.current;
      } catch (e) {
        if (seq !== matchSeqRef.current) return false;
        if (
          isAbortError(e) ||
          (!opts?.detached && sessionAbortRef.current?.signal.aborted)
        ) {
          return false;
        }
        if (!opts?.suppressError) {
          const msg = errorMessage(e, "Match failed");
          if (msg) setError(msg);
        }
        padRef.current?.resumePlaybackDrive();
        return false;
      } finally {
        if (seq === matchSeqRef.current) {
          matchingRef.current = false;
          setLoading(false);
          setSwitchingTrack(false);
        }
      }
    },
    [applyMatch, embeddingPenaltiesForApi, handoffMatchSignal, padMatchPosition],
  );

  const playPrefetchCandidate = useCallback(
    async (
      candidate: PrefetchCandidate,
      opts?: {
        expectLeaveTrackId?: string;
        entryMs?: number;
        segments?: TrackTimeline["segments"];
      },
    ): Promise<boolean> => {
      if (switchingTrackRef.current) return false;
      if (matchingRef.current && !trackChangeInFlightRef.current) return false;

      const bpmFrom = nowPlayingRef.current?.bpm ?? candidate.bpm;
      const match =
        opts?.entryMs != null
          ? buildMatchFromPrefetchAtEntry(
              candidate,
              opts.entryMs,
              bpmFrom,
              opts.segments,
            )
          : buildMatchFromPrefetch(candidate, bpmFrom);
      const beforeTrackId = nowPlayingRef.current?.track_id;
      const beforeStartMs = nowPlayingRef.current?.start_ms;
      setSwitchingTrack(true);
      try {
        audio.ensureContext();
        const seq = ++matchSeqRef.current;
        matchingRef.current = true;
        try {
          const applied = await applyMatch(match, seq, {
            onTransitionStart: () => setSwitchingTrack(false),
          });
          if (!applied || seq !== matchSeqRef.current) return false;
          if (
            opts?.expectLeaveTrackId != null &&
            match.track_id === opts.expectLeaveTrackId
          ) {
            return false;
          }
          return (
            match.track_id !== beforeTrackId || match.start_ms !== beforeStartMs
          );
        } finally {
          if (seq === matchSeqRef.current) {
            matchingRef.current = false;
          }
        }
      } catch (e) {
        if (!isAbortError(e)) {
          const msg = errorMessage(e, "Playback failed");
          if (msg) setError(msg);
        }
        return false;
      } finally {
        setSwitchingTrack(false);
      }
    },
    [applyMatch, audio],
  );

  const schedulePrefetchAfterTimelineReplay = useCallback(
    (trackId: string, entryMs: number) => {
      const track = nowPlayingRef.current;
      if (!track || track.track_id !== trackId) return;
      void refreshPrefetchFor(track, padMatchPosition(), entryMs, {
        urgent: true,
        signal: sessionAbortRef.current?.signal,
      });
    },
    [refreshPrefetchFor, padMatchPosition],
  );

  const replayTimelineTrack = useCallback(
    async (trackId: string, entryMs: number): Promise<boolean> => {
      const row = matchRowsRef.current.find((r) => r.track_id === trackId);
      if (showSyncedMatchesRef.current && row && needsTimelineEnrich(row)) {
        await enrichMatchRow(row.emotion, trackId, entryMs, sessionAbortRef.current?.signal);
      }

      const playing = nowPlayingRef.current;
      if (playing?.track_id === trackId) {
        if (Math.abs(playbackMsRef.current - entryMs) > 400) {
          const timeline =
            currentTimelineRef.current ?? stubTimelineFromMatch(playing);
          const seg = segmentAtTime(timeline.segments, entryMs);
          if (!seg) return false;
          manualSegmentSeekRef.current = segmentIndexAtTime(
            timeline.segments,
            entryMs,
          );
          try {
            audio.ensureContext();
            await audio.seekToMs(entryMs);
            audio.alignPlaybackClock(entryMs);
            playbackMsRef.current = entryMs;
            lastSegmentIdxRef.current = manualSegmentSeekRef.current;
            const updated: MatchResponse = {
              ...playing,
              start_ms: entryMs,
              segment: {
                t_start: entryMs,
                t_end: seg.t_end,
                v: seg.v,
                ar: seg.ar,
                label: seg.label,
                emotion_label: seg.emotion_label,
              },
            };
            nowPlayingRef.current = updated;
            setNowPlaying(updated);
            trackEntryMsRef.current = entryMs;
          } finally {
            manualSegmentSeekRef.current = null;
          }
        }
        schedulePrefetchAfterTimelineReplay(trackId, entryMs);
        return true;
      }

      const intents = prefetchRef.current;
      const candidate = intents ? findPrefetchCandidate(intents, trackId) : undefined;
      if (candidate) {
        const played = await playPrefetchCandidate(candidate, {
          entryMs,
          segments: row?.segments,
        });
        if (played || nowPlayingRef.current?.track_id === trackId) {
          schedulePrefetchAfterTimelineReplay(trackId, entryMs);
          return true;
        }
      }

      try {
        const timeline = await api.trackTimeline(
          trackId,
          sessionAbortRef.current?.signal,
        );
        const seg =
          segmentAtTime(timeline.segments, entryMs) ?? timeline.segments[0];
        if (!seg) return false;
        const match: MatchResponse = {
          track_id: trackId,
          title: timeline.title,
          artist: timeline.artist,
          bpm: timeline.bpm,
          audio_url: trackAudioUrl(trackId),
          start_ms: entryMs,
          score: 0,
          segment: {
            t_start: entryMs,
            t_end: seg.t_end,
            v: seg.v,
            ar: seg.ar,
            label: seg.label,
            emotion_label: seg.emotion_label,
          },
          musixmatch: timeline.musixmatch ?? candidate?.musixmatch ?? undefined,
          bpm_from: playing?.bpm ?? timeline.bpm,
          bpm_to: timeline.bpm,
        };
        const seq = ++matchSeqRef.current;
        matchingRef.current = true;
        setSwitchingTrack(true);
        try {
          const applied = await applyMatch(match, seq, {
            onTransitionStart: () => setSwitchingTrack(false),
          });
          if (!applied || nowPlayingRef.current?.track_id !== trackId) return false;
          schedulePrefetchAfterTimelineReplay(trackId, entryMs);
          return true;
        } finally {
          if (seq === matchSeqRef.current) {
            matchingRef.current = false;
            setSwitchingTrack(false);
          }
        }
      } catch (e) {
        if (!isAbortError(e)) {
          const msg = errorMessage(e, "Replay failed");
          if (msg) setError(msg);
        }
        return false;
      }
    },
    [
      applyMatch,
      audio,
      enrichMatchRow,
      playPrefetchCandidate,
      schedulePrefetchAfterTimelineReplay,
    ],
  );

  /** Last segment → crossfade to prefetch /match for the pad mood target. */
  const runLastSegmentHandoff = useCallback(
    async (sourceId: string) => {
      if (lastSegmentHandoffTrackRef.current === sourceId) return;
      lastSegmentHandoffTrackRef.current = sourceId;
      naturalHandoffFromTrackRef.current = sourceId;

      ++matchSeqRef.current;
      trackChangeInFlightRef.current = true;
      audio.bumpPlaybackGeneration();
      padRef.current?.lockFilledToIntent();
      setError(null);

      try {
        const target = padMatchPosition();
        targetRef.current = target;

        const candidate = pickPrefetchForPadTarget(
          prefetchRef.current,
          target.v,
          target.ar,
          playedTrackIdsRef.current,
          sourceId,
        );
        if (candidate) {
          const ok = await playPrefetchCandidate(candidate, {
            expectLeaveTrackId: sourceId,
          });
          if (ok) {
            lastMatchedTargetRef.current = target;
            return;
          }
        }
        if (nowPlayingRef.current?.track_id !== sourceId) {
          naturalHandoffFromTrackRef.current = null;
          return;
        }

        const ok = await requestMatch({
          force: true,
          cut: true,
          changeTrack: true,
          detached: true,
          suppressError: true,
        });
        if (ok) {
          lastMatchedTargetRef.current = target;
        } else if (nowPlayingRef.current?.track_id === sourceId) {
          lastSegmentHandoffTrackRef.current = null;
          naturalHandoffFromTrackRef.current = null;
        }
      } finally {
        trackChangeInFlightRef.current = false;
      }
    },
    [audio, padMatchPosition, playPrefetchCandidate, requestMatch],
  );

  const seekToCurrentSegment = useCallback(
    async (segIdx: number) => {
      const playing = nowPlayingRef.current;
      if (!playing || !audio.hasTrack || dragRef.current) return;
      if (trackChangeInFlightRef.current || matchingRef.current) return;

      const timeline = currentTimeline ?? stubTimelineFromMatch(playing);
      const seg = timeline.segments[segIdx];
      if (!seg) return;

      const currentIdx = segmentIndexAtTime(timeline.segments, playbackMsRef.current);
      if (
        currentIdx === segIdx &&
        Math.abs(playbackMsRef.current - seg.t_start) < 400
      ) {
        return;
      }

      manualSegmentSeekRef.current = segIdx;
      try {
        audio.ensureContext();
        await audio.seekToMs(seg.t_start);
        audio.alignPlaybackClock(seg.t_start);
        playbackMsRef.current = seg.t_start;
        lastSegmentIdxRef.current = segIdx;

        const updated: MatchResponse = {
          ...playing,
          start_ms: seg.t_start,
          segment: {
            t_start: seg.t_start,
            t_end: seg.t_end,
            v: seg.v,
            ar: seg.ar,
            label: seg.label,
            emotion_label: seg.emotion_label,
          },
        };
        nowPlayingRef.current = updated;
        setNowPlaying(updated);
        padRef.current?.seedShadowMotion(seg.v, seg.ar);
        lastLiveMoodRef.current = { v: seg.v, ar: seg.ar };
      } finally {
        manualSegmentSeekRef.current = null;
      }
    },
    [audio, currentTimeline],
  );

  /** Segment entry on the current track only (`pad_only` — no other songs). */
  const applySegmentOnCurrentTrack = useCallback(async () => {
    const playing = nowPlayingRef.current;
    if (!playing || dragRef.current) return;
    if (trackChangeInFlightRef.current || matchingRef.current) {
      return;
    }

    const synced = syncedTimelineForTrack(
      playing.track_id,
      currentTimelineRef.current,
    );
    const segments =
      synced?.segments ?? stubTimelineFromMatch(playing).segments;
    if (!synced || segments.length < 2) return;
    if (isOnLastSegment(segments, playbackMsRef.current)) return;

    const seq = ++matchSeqRef.current;
    matchingRef.current = true;
    try {
      const match = await api.match(
        {
          position: padMatchPosition(),
          direction: directionRef.current,
          bpm_current: playing.bpm,
          exclude_ids: [...playedTrackIdsRef.current],
          current_track_id: playing.track_id,
          current_t_ms: playbackMsRef.current,
          pad_only: true,
          embedding_penalties: embeddingPenaltiesForApi(),
        },
        sessionAbortRef.current?.signal,
      );
      if (seq !== matchSeqRef.current) return;
      if (trackChangeInFlightRef.current) return;
      if (match.track_id !== playing.track_id) return;
      if (Math.abs(match.start_ms - playbackMsRef.current) < 1200) return;

      await applyMatch(match, seq);
    } catch (e) {
      if (seq !== matchSeqRef.current) return;
      if (isAbortError(e)) return;
    } finally {
      if (seq === matchSeqRef.current) {
        matchingRef.current = false;
      }
    }
  }, [applyMatch, currentTimeline, embeddingPenaltiesForApi, padMatchPosition]);

  /** Sole track-change pipeline (pad release, skip, start, timeline). */
  const changeTrack = useCallback(
    async (
      reason: TrackChangeReason,
      opts?: {
        target?: { v: number; ar: number };
        trackId?: string;
        entryMs?: number;
        sameZoneHandoff?: boolean;
      },
    ) => {
      if (trackChangeInFlightRef.current) return;
      const userInitiated =
        reason === "pad-release" || reason === "skip" || reason === "timeline";
      if (matchingRef.current && !userInitiated && reason !== "start") return;

      if (reason === "start") {
        audio.ensureContext();
        trackChangeInFlightRef.current = true;
        try {
          await requestMatch({ force: true, sessionSeed: true });
        } finally {
          trackChangeInFlightRef.current = false;
        }
        return;
      }

      if (reason === "timeline") {
        if (!opts?.trackId || opts.entryMs == null) return;
        naturalHandoffFromTrackRef.current = null;
        const pos = padMatchPosition();
        moodMonitor.userAction("timeline", {
          v: pos.v,
          ar: pos.ar,
          detail: { trackId: opts.trackId, entryMs: opts.entryMs },
        });
        trackChangeInFlightRef.current = true;
        try {
          await replayTimelineTrack(opts.trackId, opts.entryMs);
        } finally {
          trackChangeInFlightRef.current = false;
        }
        return;
      }

      if (!nowPlayingRef.current) return;
      if (
        dragRef.current &&
        reason !== "pad-release" &&
        reason !== "skip"
      ) {
        return;
      }

      abortSameMoodPrefetch();
      naturalHandoffFromTrackRef.current = null;
      if (reason === "pad-release" && opts?.target) {
        resetSameMoodStability({
          v: opts.target.v,
          ar: opts.target.ar,
          trackId: nowPlayingRef.current.track_id,
        });
      } else if (reason === "skip") {
        const target = padMatchPosition();
        resetSameMoodStability({
          v: target.v,
          ar: target.ar,
          trackId: nowPlayingRef.current.track_id,
        });
      }

      if (reason === "skip") {
        registerEarlyRejectIfNeeded();
      } else if (reason === "pad-release" && opts?.sameZoneHandoff) {
        registerEarlyRejectIfNeeded();
      }

      trackChangeInFlightRef.current = true;
      ++matchSeqRef.current;
      setError(null);
      padRef.current?.lockFilledToIntent();

      try {
        const target = opts?.target ?? padMatchPosition();
        targetRef.current = target;
        if (reason === "pad-release" && opts?.target) {
          setPosition(opts.target);
          lastPadMatchAtRef.current = Date.now();
        }

        const excludeCurrent = reason === "skip" || reason === "pad-release";
        const playingId = nowPlayingRef.current.track_id;
        const prefetchHit = pickPrefetchForPadTarget(
          prefetchRef.current,
          target.v,
          target.ar,
          playedTrackIdsRef.current,
          excludeCurrent ? playingId : undefined,
        );
        if (prefetchHit && (await playPrefetchCandidate(prefetchHit))) {
          lastMatchedTargetRef.current = target;
          return;
        }

        const trackIdBefore = playingId;
        if (nowPlayingRef.current?.track_id !== trackIdBefore) return;
        await requestMatch({
          force: true,
          cut: true,
          changeTrack: reason === "pad-release" || reason === "skip",
        });
        lastMatchedTargetRef.current = target;
      } finally {
        trackChangeInFlightRef.current = false;
      }
    },
    [
      abortSameMoodPrefetch,
      audio,
      padMatchPosition,
      playPrefetchCandidate,
      replayTimelineTrack,
      registerEarlyRejectIfNeeded,
      requestMatch,
      resetSameMoodStability,
    ],
  );

  const onSkip = useCallback(async () => {
    if (!nowPlayingRef.current) return;
    audio.ensureContext();
    const pos = padMatchPosition();
    moodMonitor.userAction("skip", { v: pos.v, ar: pos.ar });
    await changeTrack("skip");
  }, [audio, changeTrack, padMatchPosition]);

  useEffect(() => {
    if (!nowPlaying) {
      moodMonitor.sessionEnd();
      embeddingPenaltyRangesRef.current = [];
      trackPlayStartSessionMsRef.current = null;
      sessionPlayStartedRef.current = false;
      sessionAbortRef.current?.abort("session-stop");
      sessionAbortRef.current = null;
      enrichedRowsRef.current.clear();
      prefetchInFlightRef.current = 0;
      setPrefetch(null);
      setTargetZonePrefetchNote(null);
      timelineLoadSeqRef.current += 1;
      setCurrentTimeline(null);
      setMatchRows([]);
      setMatchesLoading(false);
      setShowSyncedMatches(false);
      padRef.current?.clearPlaybackDrive();
      return;
    }

    setError(null);
    sessionAbortRef.current?.abort("track-change");
    const controller = new AbortController();
    sessionAbortRef.current = controller;
    const signal = controller.signal;
    enrichedRowsRef.current.clear();
    lastSegmentIdxRef.current = -1;
    lastSegmentPlaybackMsRef.current = null;
    lastSegmentHandoffTrackRef.current = null;
    trackHandoffAllowedAfterRef.current = Date.now() + TRACK_HANDOFF_SETTLE_MS;
    resetSameMoodStability();

    const track = nowPlaying;
    padRef.current?.seedShadowMotion(track.segment.v, track.segment.ar);
    {
      const pos = padMatchPosition();
      resetSameMoodStability({ v: pos.v, ar: pos.ar, trackId: track.track_id });
    }
    lastPrefetchPlaybackMsRef.current = track.start_ms;
    lastLiveMoodRef.current = { v: track.segment.v, ar: track.segment.ar };
    lastMatchedTargetRef.current = { ...targetRef.current };

    void refreshPrefetchFor(track, padMatchPosition(), track.start_ms, {
      urgent: true,
      signal,
    });

    return () => {
      controller.abort("track-change");
    };
  }, [
    nowPlaying?.track_id,
    nowPlaying?.start_ms,
    refreshPrefetchFor,
    padMatchPosition,
    resetSameMoodStability,
  ]);

  /**
   * Target mood stable ≥30s → replace that pad zone's prefetch (mood_distribution ≥ 0.5).
   */
  useEffect(() => {
    if (!nowPlaying || !audio.hasTrack) return;

    const tick = () => {
      const track = nowPlayingRef.current;
      if (!track) return;
      if (
        dragRef.current ||
        sameMoodDragPausedAtRef.current != null ||
        trackChangeInFlightRef.current ||
        sameMoodPrefetchInFlightRef.current ||
        manualSegmentSeekRef.current !== null
      ) {
        return;
      }
      if (stablePadMoodTrackIdRef.current !== track.track_id) return;

      const target = padMatchPosition();
      updateStablePadMood(target.v, target.ar);
      const stable = stablePadMoodRef.current;
      if (!stable) return;

      const now = Date.now();
      if (now - stable.sinceMs < TARGET_MOOD_STABLE_MS) return;
      if (now - lastSameMoodPrefetchAtRef.current < TARGET_MOOD_STABLE_MS) return;

      lastSameMoodPrefetchAtRef.current = now;
      void refreshTargetMoodPrefetch();
    };

    const id = window.setInterval(tick, TARGET_MOOD_PREFETCH_POLL_MS);
    return () => {
      window.clearInterval(id);
      abortSameMoodPrefetch();
    };
  }, [
    nowPlaying?.track_id,
    audio.hasTrack,
    abortSameMoodPrefetch,
    padMatchPosition,
    updateStablePadMood,
    refreshTargetMoodPrefetch,
  ]);

  useEffect(() => {
    if (targetZonePrefetchNote?.status !== "no_better_match") return;
    const id = window.setTimeout(() => {
      setTargetZonePrefetchNote((prev) =>
        prev?.status === "no_better_match" ? null : prev,
      );
    }, TARGET_ZONE_NO_MATCH_NOTE_MS);
    return () => window.clearTimeout(id);
  }, [targetZonePrefetchNote]);

  /** Panel closed: drop match UI state; keep current track timeline. */
  useEffect(() => {
    if (showSyncedMatches || !nowPlaying) return;
    setMatchRows([]);
    setMatchesLoading(false);
  }, [showSyncedMatches, nowPlaying]);

  /**
   * Panel opened: prefetch intents are kept in memory while closed, but match rows
   * are cleared — hydrate from cache immediately instead of waiting for a track change.
   */
  useEffect(() => {
    if (!showSyncedMatches) return;
    const track = nowPlayingRef.current;
    if (!track) return;

    const intents = prefetchRef.current;
    const hasPrefetch = intents != null && Object.keys(intents).length > 0;

    if (hasPrefetch && matchRowsRef.current.length === 0) {
      const quick = quickMatchRowsFromIntents(intents, playedTrackIdsRef.current);
      if (quick.length > 0) {
        setMatchRows(quick);
        void loadFullMatchRows(quick, sessionAbortRef.current?.signal).then((full) => {
          if (nowPlayingRef.current?.track_id === track.track_id) {
            setMatchRows(full);
          }
        });
      }
    }

    void refreshPrefetchFor(track, padMatchPosition(), playbackMsRef.current, {
      urgent: !hasPrefetch,
    });
  }, [showSyncedMatches, loadFullMatchRows, refreshPrefetchFor, padMatchPosition]);

  /** When synced-matches panel is open, load full MOSS segments + motion for every row. */
  useEffect(() => {
    if (!showSyncedMatches || !nowPlaying) return;

    const controller = new AbortController();
    const signal = controller.signal;

    void (async () => {
      const trackId = nowPlaying.track_id;
      const currentView = currentTimeline ?? stubTimelineFromMatch(nowPlaying);
      const currentNeedsMotion = needsTimelineEnrich(currentView);
      const currentNeedsSegments = needsHandoffTimeline(currentView);
      const rowsNeedingEnrich = matchRows.filter(needsTimelineEnrich);
      if (!currentNeedsMotion && !currentNeedsSegments && rowsNeedingEnrich.length === 0) {
        return;
      }

      try {
        if (currentNeedsMotion || currentNeedsSegments) {
          const full = await api.trackTimeline(trackId, signal, { motionPreview: true });
          if (!signal.aborted && nowPlayingRef.current?.track_id === trackId) {
            setCurrentTimeline(full);
          }
        }
        await Promise.all(
          rowsNeedingEnrich.map((row) =>
            enrichMatchRow(row.emotion, row.track_id, row.entryMs, signal),
          ),
        );
      } catch (e) {
        if (isAbortError(e) || signal.aborted) return;
      }
    })();

    return () => controller.abort("panel-close");
  }, [
    showSyncedMatches,
    matchRows,
    nowPlaying,
    currentTimeline,
    enrichMatchRow,
  ]);

  useEffect(() => {
    const trackId = nowPlaying?.track_id;
    if (!trackId) {
      setTrackPlayCount(null);
      return;
    }

    const controller = new AbortController();
    void api
      .getPlayCount(trackId, controller.signal)
      .then((r) => {
        if (nowPlayingRef.current?.track_id !== trackId) return;
        setPlayStatsEnabled(r.stats_enabled);
        const count = r.stats_enabled ? r.play_count : null;
        setTrackPlayCount(count);
        moodMonitor.updateTrackPlayCount(trackId, count);
      })
      .catch((e) => {
        if (isAbortError(e)) return;
      });

    return () => controller.abort("play-count");
  }, [nowPlaying?.track_id]);

  /**
   * Segment change: pad_only seek on same track, except entering the last segment
   * → crossfade to the prefetch match for the pad mood target.
   */
  useEffect(() => {
    if (!nowPlaying || !audio.hasTrack || dragRef.current) return;
    if (trackChangeInFlightRef.current) return;
    if (manualSegmentSeekRef.current !== null) return;

    const syncedTimeline = syncedTimelineForTrack(
      nowPlaying.track_id,
      currentTimeline,
    );
    const segments =
      syncedTimeline?.segments ?? stubTimelineFromMatch(nowPlaying).segments;
    if (segments.length < 2) return;

    const idx = segmentIndexAtTime(segments, audio.playbackMs);
    const lastIdx = segments.length - 1;
    const { crossed: crossedSegment, prevIdx } = segmentCrossedBetween(
      segments,
      lastSegmentPlaybackMsRef.current,
      audio.playbackMs,
    );
    lastSegmentPlaybackMsRef.current = audio.playbackMs;

    const estFadeMs = estimateSameMoodFadeMs(nowPlaying.bpm);
    const earlyHandoffMs = needsEarlySameMoodHandoff(segments, estFadeMs)
      ? earlySameMoodHandoffMs(segments, estFadeMs)
      : null;

    const durationMs = syncedTimeline ? trackDurationMs(syncedTimeline) : 0;
    const playheadStale =
      durationMs > 0 && audio.playbackMs > durationMs + 1_500;
    const handoffReady =
      syncedTimeline != null &&
      !playheadStale &&
      Date.now() >= trackHandoffAllowedAfterRef.current;
    const handoffPending =
      lastSegmentHandoffTrackRef.current !== nowPlaying.track_id;

    if (handoffPending && handoffReady) {
      const shouldHandoff =
        earlyHandoffMs != null
          ? audio.playbackMs >= earlyHandoffMs
          : crossedSegment && idx === lastIdx && prevIdx < lastIdx;
      if (shouldHandoff) {
        void runLastSegmentHandoff(nowPlaying.track_id);
        return;
      }
    }

    if (!crossedSegment) {
      lastSegmentIdxRef.current = idx;
      return;
    }

    if (idx === lastSegmentIdxRef.current) return;

    lastSegmentIdxRef.current = idx;
    if (idx === lastIdx) return;

    void applySegmentOnCurrentTrack();
  }, [
    audio.playbackMs,
    audio.hasTrack,
    nowPlaying,
    currentTimeline,
    applySegmentOnCurrentTrack,
    runLastSegmentHandoff,
  ]);

  useEffect(() => {
    if (!nowPlaying || !audio.hasTrack) return;
    let cancelled = false;
    const syncPadFromMotion = async () => {
      const track = nowPlayingRef.current;
      if (!track) return;
      try {
        const at = await api.motionAt(
          track.track_id,
          playbackMsRef.current / 1000,
          sessionAbortRef.current?.signal,
        );
        if (!cancelled && !dragRef.current && !sessionAbortRef.current?.signal.aborted) {
          padRef.current?.setPlaybackMotion(at.valence, at.arousal);
        }
      } catch (e) {
        if (isAbortError(e)) return;
      }
    };
    void syncPadFromMotion();
    const id = window.setInterval(() => void syncPadFromMotion(), MOTION_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [nowPlaying?.track_id, audio.hasTrack]);

  const onPadDragStart = () => {
    dismissPostPlayHint();
    const pos = padMatchPosition();
    padDragStartZoneRef.current = nearestEmotionZone(pos.v, pos.ar).name;
    dragRef.current = true;
    audio.ensureContext();
    pauseSameMoodStabilityClock();
  };

  const onPadDragEnd = useCallback(() => {
    dragRef.current = false;
    resumeSameMoodStabilityClock();
  }, [resumeSameMoodStabilityClock]);

  const onPadPositionSettled = useCallback(
    (v: number, ar: number) => {
      dragRef.current = false;
      const endZone = nearestEmotionZone(v, ar).name;
      const startZone = padDragStartZoneRef.current;
      padDragStartZoneRef.current = null;
      if (startZone && startZone !== endZone) {
        moodMonitor.userAction("mood_change", {
          v,
          ar,
          fromZone: startZone,
        });
      } else {
        moodMonitor.userAction("same_mood_change", {
          v,
          ar,
          fromZone: startZone ?? endZone,
        });
      }
      resetSameMoodStability({
        v,
        ar,
        trackId: nowPlayingRef.current?.track_id,
      });
      const sameZone = !startZone || startZone === endZone;
      void changeTrack("pad-release", {
        target: { v, ar },
        sameZoneHandoff: sameZone,
      });
    },
    [changeTrack, resetSameMoodStability],
  );

  const onRewind = useCallback(() => {
    const pos = padMatchPosition();
    moodMonitor.userAction("replay", { v: pos.v, ar: pos.ar });
    void audio.rewind();
  }, [audio, padMatchPosition]);

  const onStartListening = useCallback(() => {
    void changeTrack("start");
  }, [changeTrack]);

  const onRetryStartListening = useCallback(() => {
    setError(null);
    void changeTrack("start");
  }, [changeTrack]);

  const firstPlayErrorTimedOut =
    Boolean(error) &&
    !nowPlaying &&
    error!.includes("Still connecting to the Moony API");

  const onReplayHistoryTrack = useCallback(
    (track: MoodTrackEntry) => {
      void changeTrack("timeline", {
        trackId: track.trackId,
        entryMs: track.entryMs,
      });
    },
    [changeTrack],
  );

  /** Compact header + tighter layout once the first track card can render. */
  const sessionLayoutActive = Boolean(nowPlaying);
  const onDismissFeatureTip = useCallback(() => {
    if (featureTip?.id === "matches") markMatchesDiscovered();
    dismissFeatureTip();
  }, [featureTip?.id, dismissFeatureTip, markMatchesDiscovered]);

  const subtitleHidden = Boolean(loading || nowPlaying);

  return (
    <>
      <TopInfoNav
        active={infoPanel}
        onSelect={(panel) => setInfoPanel((current) => (current === panel ? null : panel))}
      />
      <MoonyApiPanel
        open={infoPanel === "api"}
        onClose={() => setInfoPanel(null)}
        onOpenAbout={() => setInfoPanel("about")}
      />
      <MoonyAboutPanel
        open={infoPanel === "about"}
        onClose={() => setInfoPanel(null)}
        onExploreApi={() => setInfoPanel("api")}
      />
      <div
        className={`moony-app-shell mx-auto flex min-h-screen flex-col px-6${
          sessionLayoutActive ? " moony-app--playing" : " moony-app--landing"
        }${nowPlaying ? " moony-app--has-dock" : ""}${
          showSyncedMatches && nowPlaying ? " moony-app--has-matches" : ""
        }`}
        style={{ maxWidth: FLUID_PAD_WRAPPER_PX + 48 }}
      >
      <header
        className={`moony-header${subtitleHidden ? " moony-header--subtitle-hidden" : ""}${
          sessionLayoutActive ? " moony-header--playing" : ""
        }`}
      >
        <div className="moony-header-brand">
          <h1 className="moony-title moony-header-title tracking-tight">moony</h1>
          <p className="moony-header-subtitle px-2">
            <span className="moony-header-subtitle-line">the emotional intelligence API</span>
            <span className="moony-header-subtitle-line">for music catalogs</span>
          </p>
        </div>
      </header>

      <section
        className={`moony-player-section mx-auto flex flex-col items-center${
          sessionLayoutActive ? " moony-player-section--playing" : ""
        }`}
        style={{ width: FLUID_PAD_WRAPPER_PX }}
      >
        <div
          className="moony-pad-shell relative mx-auto"
          style={{ width: FLUID_PAD_WRAPPER_PX, height: FLUID_PAD_WRAPPER_PX }}
        >
          <FluidEmotionPad
            ref={padRef}
            interactionDisabled={switchingTrack}
            playbackEnvelopeActive={Boolean(nowPlaying && audio.isPlaying && !switchingTrack)}
            sampleLinearPeak={audio.samplePlaybackLinearPeak}
            playbackBpm={nowPlaying?.bpm}
            onPositionChange={onPositionChange}
            onDragStart={onPadDragStart}
            onDragEnd={onPadDragEnd}
            onPositionSettled={onPadPositionSettled}
          />
          {switchingTrack && nowPlaying ? (
            <div
              className="pointer-events-none absolute left-1/2 top-1/2 z-20 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center"
              role="status"
              aria-label="Loading track"
              data-testid="pad-track-switch-loader"
            >
              <span className="h-7 w-7 animate-spin rounded-full border-2 border-white/25 border-t-white/90" />
            </div>
          ) : null}
          {nowPlaying && padLyrics ? (
            <LyricsScroller
              key={padLyrics.trackId}
              variant="pad"
              trackId={padLyrics.trackId}
              lines={padLyrics.lines}
              playbackStore={audio.lyricsPlaybackStore}
              entryMs={padLyrics.entryMs}
              pixelUrl={padLyrics.pixelUrl}
              source={padLyrics.source}
              loading={false}
              enabled={audio.hasTrack}
              syncPlayback={padLyricsSyncPlayback}
            />
          ) : null}
          {!nowPlaying ? (
            <button
              type="button"
              data-testid="start-listening"
              aria-label={loading ? "Loading" : "Start listening"}
              title={loading ? "Loading…" : "Play"}
              disabled={loading || switchingTrack}
              onClick={onStartListening}
              className="absolute left-1/2 top-1/2 z-10 flex h-28 w-28 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-[6px] border-white/90 bg-moony-accent text-white shadow-[0_8px_32px_rgba(0,0,0,0.45)] transition hover:scale-[1.03] hover:opacity-95 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100"
            >
              {loading ? (
                <span className="h-10 w-10 animate-spin rounded-full border-4 border-white/30 border-t-white" />
              ) : (
                <svg
                  className="ml-1.5 h-14 w-14 shrink-0"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  aria-hidden
                >
                  <path d="M8 5v14l11-7L8 5z" />
                </svg>
              )}
            </button>
          ) : null}
        </div>

        {loading && !nowPlaying ? (
          <p className="moony-loading-status" role="status" aria-live="polite">
            Matching your mood…
          </p>
        ) : null}

        {!nowPlaying && !loading ? (
          <LandingIntro
            onOpenAbout={() => setInfoPanel("about")}
            onOpenApi={() => setInfoPanel("api")}
          />
        ) : null}

        {nowPlaying ? (
          <div className="moony-playback-stack">
            <PlaybackControls
              disabled={switchingTrack}
              isPlaying={audio.isPlaying}
              hasTrack={audio.hasTrack}
              volume={audio.volume}
              muted={audio.muted}
              onVolumeChange={audio.setVolume}
              onToggleMute={audio.toggleMute}
              onPlayPause={() => void audio.togglePlayPause()}
              onRewind={onRewind}
              onSkip={() => void onSkip()}
            />
          </div>
        ) : null}

        {nowPlaying ? <PostPlayHint /> : null}
      </section>

      {error && !nowPlaying ? (
        <div className="moony-session-error" role="alert">
          <p className="moony-session-error__title">
            {firstPlayErrorTimedOut ? "Connection timed out" : "Can't reach the Moony API"}
          </p>
          <p className="moony-session-error__detail">{error}</p>
          <div className="moony-session-error__actions">
            <button
              type="button"
              className="moony-session-error__action moony-session-error__action--primary"
              onClick={onRetryStartListening}
            >
              Try again
            </button>
            <button
              type="button"
              className="moony-session-error__action"
              onClick={() => setInfoPanel("api")}
            >
              View API setup
            </button>
          </div>
        </div>
      ) : null}
      {error && nowPlaying ? <p className="text-sm text-red-400">{error}</p> : null}

      {nowPlaying ? (
        <>
          <section
            data-testid="now-playing"
            className="now-playing-panel space-y-4 rounded-2xl p-5"
          >
            <div className="now-playing-panel__chrome">
              <div className="space-y-2">
                <div>
                  <h2 data-testid="track-title" className="text-lg font-medium tracking-tight">
                    {nowPlaying.title}
                  </h2>
                  <p data-testid="track-artist" className="text-white/55">
                    {nowPlaying.artist}
                  </p>
                </div>
                <div className="track-meta-chips">
                  {playStatsEnabled && trackPlayCount != null ? (
                    <span data-testid="play-count" className="track-meta-chip">
                      {trackPlayCount === 0
                        ? "Unplayed globally"
                        : trackPlayCount === 1
                          ? "1 play total"
                          : `${trackPlayCount} plays total`}
                    </span>
                  ) : playStatsEnabled ? (
                    <span className="track-meta-chip">Loading play count…</span>
                  ) : (
                    <span className="track-meta-chip">Global play stats offline</span>
                  )}
                  <span className="track-meta-chip">{nowPlaying.bpm} BPM</span>
                  {showSyncedMatches && nowPlaying.emotion_label ? (
                    <span className="track-meta-chip">{nowPlaying.emotion_label}</span>
                  ) : null}
                  {showSyncedMatches && nowPlaying.mood_quality ? (
                    <span className="track-meta-chip">fit {nowPlaying.mood_quality}</span>
                  ) : null}
                </div>
              </div>
              {timelineView ? (
                <SegmentTimelinePlayer
                  view={timelineView}
                  currentMs={audio.playbackMs}
                  onSelectCurrentSegment={(segIdx) => void seekToCurrentSegment(segIdx)}
                  matchesToggle={
                    <>
                      {featureTip?.id === "matches" ? (
                        <FeatureTipToast
                          title={featureTip.title}
                          body={featureTip.body}
                          onDismiss={onDismissFeatureTip}
                          className="feature-tip--matches"
                          testId="feature-tip-matches"
                        />
                      ) : null}
                      <MatchesGearButton
                        active={showSyncedMatches}
                        highlight={matchesHighlight && featureTip?.id !== "matches"}
                        emphasizeLabel={matchesHighlight}
                        onClick={() => {
                          markMatchesDiscovered();
                          setShowSyncedMatches((open) => !open);
                        }}
                      />
                    </>
                  }
                />
              ) : null}
            </div>
            {showSyncedMatches && timelineView ? (
              <SegmentTimelinePlayer
                matchesOnly
                view={timelineView}
                currentMs={audio.playbackMs}
                matchesLoading={matchesLoading}
                showSyncedMatches
                targetZonePrefetchNote={
                  targetZonePrefetchNote
                    ? {
                        zone: targetZonePrefetchNote.zone,
                        text:
                          targetZonePrefetchNote.status === "fetching"
                            ? "fetching better match..."
                            : "no better match found",
                      }
                    : null
                }
                onSelectMatch={(trackId, entryMs) =>
                  void changeTrack("timeline", { trackId, entryMs })
                }
              />
            ) : null}
          </section>
        </>
      ) : null}
      {nowPlaying ? (
        <DevPanelsDock
          isPlaying={Boolean(nowPlaying && audio.isPlaying)}
          onReplayHistoryTrack={onReplayHistoryTrack}
          featureTip={featureTip}
          onFeatureTipDismiss={onDismissFeatureTip}
          timelineDockHint={showTimelineHint}
          onTimelineDockHintDismiss={dismissTimelineHint}
        />
      ) : null}
      </div>
    </>
  );
}
