import type { MatchResponse, PrefetchCandidate } from "./api";

/** Playback payload: entry at prefetch `audio_start_ms`, MOSS segment metadata unchanged. */
export function matchResponseFromPrefetchCandidate(
  candidate: PrefetchCandidate,
  bpmFrom: number,
): MatchResponse {
  const seg = candidate.segment;
  return {
    track_id: candidate.track_id,
    title: candidate.title,
    artist: candidate.artist,
    bpm: candidate.bpm,
    audio_url: candidate.audio_url,
    start_ms: candidate.audio_start_ms,
    score: candidate.score,
    segment: {
      t_start: seg.t_start ?? candidate.audio_start_ms,
      t_end: seg.t_end,
      v: seg.v,
      ar: seg.ar,
      label: seg.label,
      emotion_label: seg.emotion_label,
    },
    musixmatch: candidate.musixmatch ?? undefined,
    bpm_from: bpmFrom,
    bpm_to: candidate.bpm,
    crossfade_ms: candidate.crossfade_ms,
    crossfade_curve: candidate.crossfade_curve,
    crossfade_start_ms: candidate.crossfade_start_ms,
    playback_rate_start: candidate.playback_rate_start,
    playback_rate_end: candidate.playback_rate_end,
    playback_rate_out_end: candidate.playback_rate_out_end,
    youtube_playback_gain: candidate.youtube_playback_gain,
  };
}
