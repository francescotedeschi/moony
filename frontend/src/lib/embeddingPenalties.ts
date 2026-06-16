export const EARLY_REJECT_MAX_MS = 15_000;
export const PENALTY_HALF_LIFE_MS = 10 * 60 * 1000;

export type EmbeddingPenaltyRange = {
  track_id: string;
  from_ms: number;
  to_ms: number;
  added_at_ms: number;
};

export function penaltyDecayWeight(addedAtMs: number, nowMs = Date.now()): number {
  const age = Math.max(0, nowMs - addedAtMs);
  return 0.5 ** (age / PENALTY_HALF_LIFE_MS);
}

export function pruneEmbeddingPenalties(
  ranges: EmbeddingPenaltyRange[],
  nowMs = Date.now(),
): EmbeddingPenaltyRange[] {
  return ranges.filter((r) => penaltyDecayWeight(r.added_at_ms, nowMs) > 0.01);
}

export function registerEarlyRejectPenalty(
  ranges: EmbeddingPenaltyRange[],
  entry: {
    track_id: string;
    track_entry_ms: number;
    listened_ms: number;
    added_at_ms?: number;
  },
): EmbeddingPenaltyRange[] {
  if (entry.listened_ms <= 0 || entry.listened_ms > EARLY_REJECT_MAX_MS) {
    return pruneEmbeddingPenalties(ranges);
  }
  const from_ms = Math.max(0, entry.track_entry_ms);
  const to_ms = from_ms + Math.min(entry.listened_ms, EARLY_REJECT_MAX_MS);
  const next: EmbeddingPenaltyRange = {
    track_id: entry.track_id,
    from_ms,
    to_ms,
    added_at_ms: entry.added_at_ms ?? Date.now(),
  };
  return pruneEmbeddingPenalties([...ranges, next]);
}
