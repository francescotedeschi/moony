import { describe, expect, it } from "vitest";
import type { MossSegment } from "./api";
import {
  earlySameMoodHandoffMs,
  isInSameMoodHandoffZone,
  needsEarlySameMoodHandoff,
  SAME_MOOD_HANDOFF_PREP_MS,
} from "./segments";

const timeline: MossSegment[] = [
  { t_start: 0, t_end: 30_000, v: 0.5, ar: 0.5, label: "verse" },
  { t_start: 30_000, t_end: 35_000, v: 0.4, ar: 0.3, label: "bridge" },
  { t_start: 35_000, t_end: 39_000, v: 0.2, ar: 0.1, label: "outro" },
];

describe("same-mood handoff timing", () => {
  it("requests early handoff when the outro is shorter than fade + prep", () => {
    expect(needsEarlySameMoodHandoff(timeline, 3_000, SAME_MOOD_HANDOFF_PREP_MS)).toBe(true);
  });

  it("keeps normal handoff when the outro has enough runway", () => {
    const longOutro: MossSegment[] = [
      ...timeline.slice(0, 2),
      { ...timeline[2], t_end: 55_000 },
    ];
    expect(needsEarlySameMoodHandoff(longOutro, 3_000, SAME_MOOD_HANDOFF_PREP_MS)).toBe(false);
    expect(earlySameMoodHandoffMs(longOutro, 3_000, SAME_MOOD_HANDOFF_PREP_MS)).toBeNull();
  });

  it("starts early enough before a short outro for fade + prep", () => {
    const fadeMs = 3_000;
    const earlyAt = earlySameMoodHandoffMs(timeline, fadeMs, SAME_MOOD_HANDOFF_PREP_MS);
    expect(earlyAt).toBe(34_000);

    expect(isInSameMoodHandoffZone(timeline, 33_500, fadeMs)).toBe(false);
    expect(isInSameMoodHandoffZone(timeline, 34_000, fadeMs)).toBe(true);
    expect(isInSameMoodHandoffZone(timeline, 36_000, fadeMs)).toBe(true);
  });
});
