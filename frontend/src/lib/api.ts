function abortError(signal: AbortSignal): DOMException {
  const reason = signal.reason;
  const message =
    typeof reason === "string" && reason.trim()
      ? reason.trim()
      : "The operation was aborted.";
  return new DOMException(message, "AbortError");
}

/** Dev: same-origin + Vite proxy. Docker/production: set VITE_API_URL if needed. */
const base =
  import.meta.env.VITE_API_URL?.replace(/\/$/, "") ??
  (import.meta.env.DEV ? "" : "http://localhost:8090");

/** Base URL for docs / quick-start (display). Empty in dev = same-origin via Vite proxy. */
export function getApiBaseUrlLabel(): string {
  if (base) return base;
  if (typeof window !== "undefined") return window.location.origin;
  return "";
}

export function trackAudioUrl(trackId: string): string {
  return `${base}/tracks/${trackId}/audio`;
}

async function fetchTimeline(
  trackId: string,
  signal?: AbortSignal,
): Promise<TrackTimeline> {
  return request<TrackTimeline>(`/tracks/${trackId}/timeline`, { signal });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const signal = init?.signal;
  if (signal?.aborted) {
    throw abortError(signal);
  }
  let resp: Response;
  try {
    resp = await fetch(`${base}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch (err) {
    if (signal?.aborted) {
      throw abortError(signal);
    }
    throw err;
  }
  if (signal?.aborted) {
    throw abortError(signal);
  }
  if (!resp.ok) {
    const text = await resp.text();
    try {
      const body = JSON.parse(text) as { detail?: string | { msg?: string }[] };
      if (typeof body.detail === "string") {
        throw new Error(body.detail);
      }
      if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        throw new Error(body.detail[0].msg);
      }
    } catch (e) {
      if (e instanceof Error && e.message !== text) throw e;
    }
    throw new Error(text || resp.statusText);
  }
  return resp.json() as Promise<T>;
}

export type MossSegment = {
  t_start: number;
  t_end: number;
  v: number;
  ar: number;
  label: string;
  emotion_label?: string;
  description?: string;
  /** Dominant Cyanite mood tag for this section (e.g. dark, happy). */
  cyanite_mood_tag?: string;
  /** Cyanite continuous valence [-1, 1] — null when not analyzed */
  cyanite_v?: number | null;
  /** Cyanite continuous arousal [-1, 1] — null when not analyzed */
  cyanite_ar?: number | null;
};

export type VA = { v: number; ar: number };

export type CatalogStats = {
  catalog_name?: string;
  track_count: number;
  segment_count: number;
  avg_segments_per_track?: number;
  mood_labels: string[];
  mood_segment_counts: number[];
  mood_segment_share: number[];
  dominant_mood_track_counts: number[];
  with_motion?: number;
  motion_coverage?: number;
  with_loudness?: number;
  loudness_coverage?: number;
  with_musixmatch?: number;
  segments_with_embedding?: number;
  matcher?: string;
  analyzer?: string;
  embedding_model?: string;
  catalog_schema?: string;
  version?: string;
  generated_at?: string;
  bpm_range?: { min: number; max: number };
  lyrics_mode?: string;
};

export type TrackTimeline = {
  track_id: string;
  title: string;
  artist: string;
  bpm: number;
  duration_ms: number;
  musixmatch?: Record<string, unknown> | null;
  /** Cyanite explicit energy signal [0, 1] per sample. */
  energy_curve?: number[];
  /** Millisecond timestamps aligned 1:1 with energy_curve. */
  energy_curve_timestamps_ms?: number[];
  segments: MossSegment[];
};

export type MotionAtResponse = {
  track_id: string;
  has_motion: boolean;
  interpolated: boolean;
  t_sec: number;
  energy: number;
  vocal: number;
  valence: number;
  arousal: number;
  mood: number;
};

export type MatchResponse = {
  track_id: string;
  title: string;
  artist: string;
  bpm: number;
  audio_url: string;
  start_ms: number;
  score: number;
  mood_distance?: number;
  mood_quality?: string;
  emotion_label?: string;
  segment: {
    v: number;
    ar: number;
    label: string;
    emotion_label?: string;
    t_start: number;
    t_end: number;
  };
  musixmatch?: Record<string, unknown>;
  bpm_from?: number;
  bpm_to?: number;
  playback_rate_start?: number;
  playback_rate_end?: number;
  playback_rate_out_end?: number;
  crossfade_ms?: number;
  crossfade_curve?: string;
  crossfade_mood_jump?: number;
  crossfade_start_ms?: number;
  /** Precomputed attenuation at start_ms (from catalog); instant norm when present. */
  youtube_playback_gain?: number;
};

export type PrefetchCandidate = {
  track_id: string;
  title: string;
  artist: string;
  bpm: number;
  audio_url: string;
  segment_idx: number;
  audio_start_ms: number;
  score: number;
  segment: MatchResponse["segment"];
  musixmatch?: Record<string, unknown> | null;
  crossfade_ms?: number;
  crossfade_curve?: string;
  crossfade_start_ms?: number;
  playback_rate_start?: number;
  playback_rate_end?: number;
  playback_rate_out_end?: number;
  youtube_playback_gain?: number;
};

export type PrefetchL2Branch = {
  from: { track_id: string; title: string; artist: string };
  intents: Record<string, PrefetchCandidate[]>;
};

export type PrefetchResponse = {
  current_track_id: string;
  t_ms: number;
  intents: Record<string, PrefetchCandidate[]>;
  l2: Record<string, PrefetchL2Branch>;
};

export type EmbeddingPenaltyRange = {
  track_id: string;
  from_ms: number;
  to_ms: number;
  added_at_ms: number;
};

export type LyricsResponse = {
  track_id: string;
  lines: { t_ms: number; text: string; line_index: number }[];
  lyrics_copyright: string;
  pixel_tracking_url?: string;
  source: string;
};

export type JamendoSearchResponse = {
  headers?: { status?: string; code?: number };
  results?: {
    id: string;
    name: string;
    artist_name: string;
    duration: number;
    audio: string;
  }[];
};

export const api = {
  health: () =>
    request<{
      status: string;
      catalog: CatalogStats;
      play_stats?: { enabled?: boolean; total_plays?: number };
    }>("/health"),
  catalogStats: (signal?: AbortSignal) =>
    request<CatalogStats>("/catalog/stats", { signal }),
  match: (
    body: {
      position: VA;
      direction: VA;
      bpm_current: number;
      exclude_ids?: string[];
      current_track_id?: string;
      current_t_ms?: number;
      pad_only?: boolean;
      session_seed?: boolean;
      same_mood_handoff?: boolean;
      embedding_penalties?: EmbeddingPenaltyRange[];
    },
    signal?: AbortSignal,
  ) =>
    request<MatchResponse>("/match", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),
  prefetch: (
    body: {
      current_track_id: string;
      t_ms: number;
      position: VA;
      bpm_current: number;
      depth?: number;
      exclude_ids?: string[];
      same_mood_only?: boolean;
      single_intent?: number;
      restrict_mood_share?: boolean;
      embedding_penalties?: EmbeddingPenaltyRange[];
    },
    signal?: AbortSignal,
  ) =>
    request<PrefetchResponse>("/prefetch", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),
  trackTimeline: (trackId: string, signal?: AbortSignal) => fetchTimeline(trackId, signal),
  motionAt: (trackId: string, tSec: number, signal?: AbortSignal) =>
    request<MotionAtResponse>(`/tracks/${trackId}/motion/at?t_sec=${tSec}`, { signal }),
  resolveTargetEntry: (trackId: string, target: VA, afterTMs?: number) =>
    request<{ track_id: string; start_ms: number; segment: MatchResponse["segment"] }>(
      `/tracks/${trackId}/target-entry`,
      {
        method: "POST",
        body: JSON.stringify({
          target,
          after_t_ms: afterTMs,
        }),
      },
    ),
  lyrics: (trackId: string, signal?: AbortSignal) =>
    request<LyricsResponse>(`/tracks/${trackId}/lyrics`, { signal }),
  getPlayCount: (trackId: string, signal?: AbortSignal) =>
    request<{ track_id: string; play_count: number; stats_enabled: boolean }>(
      `/tracks/${trackId}/play-count`,
      { signal },
    ),
  recordPlay: (trackId: string) =>
    request<{ track_id: string; play_count: number; stats_enabled: boolean }>(
      `/tracks/${trackId}/played`,
      { method: "POST" },
    ),
  jamendoSearch: (tags: string, limit = 20, signal?: AbortSignal) =>
    request<JamendoSearchResponse>(
      `/jamendo/tracks?tags=${encodeURIComponent(tags)}&limit=${limit}`,
      { signal },
    ),
};
