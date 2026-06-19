import { describe, expect, it } from "vitest";
import type { MossSegment } from "./api";
import type { TrackTimeline } from "./api";
import {
  earlySameMoodHandoffMs,
  isInSameMoodHandoffZone,
  isPrefetchTimelineStub,
  isTimelineBarReady,
  needsEarlySameMoodHandoff,
  needsTimelineEnrich,
  SAME_MOOD_HANDOFF_PREP_MS,
  segmentCyaniteMoodLabel,
  segmentCrossedBetween,
  segmentHasInspectData,
} from "./segments";

const timeline: MossSegment[] = [
  { t_start: 0, t_end: 30_000, v: 0.5, ar: 0.5, label: "verse" },
  { t_start: 30_000, t_end: 35_000, v: 0.4, ar: 0.3, label: "bridge" },
  { t_start: 35_000, t_end: 39_000, v: 0.2, ar: 0.1, label: "outro" },
];

const stubTimeline: TrackTimeline = {
  track_id: "a",
  title: "A",
  artist: "B",
  bpm: 120,
  duration_ms: 60_000,
  segments: [{ t_start: 0, t_end: 60_000, v: 0, ar: 0, label: "all" }],
};

const enrichedTimeline: TrackTimeline = {
  ...stubTimeline,
  segments: [
    { t_start: 0, t_end: 30_000, v: 0.5, ar: 0.5, label: "verse" },
    { t_start: 30_000, t_end: 60_000, v: 0.2, ar: 0.1, label: "outro" },
  ],
  energy_curve: [0.2, 0.5, 0.4],
  energy_curve_timestamps_ms: [0, 30_000, 60_000],
};

describe("segment inspect metadata", () => {
  it("exposes Cyanite dominant mood label", () => {
    const seg: MossSegment = {
      t_start: 0,
      t_end: 10_000,
      v: 0,
      ar: 0,
      label: "verse",
      cyanite_mood_tag: "dark",
    };
    expect(segmentCyaniteMoodLabel(seg)).toBe("Dark");
    expect(segmentHasInspectData(seg)).toBe(true);
  });
});

describe("timeline display readiness", () => {
  it("treats prefetch stubs as not display-ready", () => {
    const prefetchStub: TrackTimeline = {
      track_id: "a",
      title: "A",
      artist: "B",
      bpm: 120,
      duration_ms: 90_000,
      segments: [{ t_start: 10_000, t_end: 30_000, v: 0, ar: 0, label: "verse" }],
    };
    expect(isPrefetchTimelineStub(prefetchStub)).toBe(true);
    expect(isTimelineBarReady(prefetchStub)).toBe(false);
    expect(needsTimelineEnrich(prefetchStub)).toBe(true);
  });

  it("shows multi-segment timelines without extra enrich", () => {
    const segmentsOnly: TrackTimeline = {
      ...stubTimeline,
      segments: enrichedTimeline.segments,
    };
    expect(isTimelineBarReady(segmentsOnly)).toBe(true);
    expect(needsTimelineEnrich(segmentsOnly)).toBe(false);
  });

  it("accepts timelines with Cyanite energy curve", () => {
    expect(isTimelineBarReady(enrichedTimeline)).toBe(true);
    expect(needsTimelineEnrich(enrichedTimeline)).toBe(false);
  });
});

describe("needsTimelineEnrich (legacy stub checks)", () => {
  it("treats prefetch stubs as needing enrich", () => {
    const prefetchStub: TrackTimeline = {
      track_id: "a",
      title: "A",
      artist: "B",
      bpm: 120,
      duration_ms: 90_000,
      segments: [{ t_start: 10_000, t_end: 30_000, v: 0, ar: 0, label: "verse" }],
    };
    expect(needsTimelineEnrich(prefetchStub)).toBe(true);
  });

  it("accepts multi-segment timelines", () => {
    expect(needsTimelineEnrich(enrichedTimeline)).toBe(false);
  });
});

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

  it("ignores timeline-only segment index changes at the same playhead", () => {
    const sparse: MossSegment[] = [
      { t_start: 0, t_end: 60_000, v: 0.5, ar: 0.5, label: "all" },
    ];
    const detailed: MossSegment[] = [
      { t_start: 0, t_end: 30_000, v: 0.5, ar: 0.5, label: "verse" },
      { t_start: 30_000, t_end: 45_000, v: 0.4, ar: 0.3, label: "bridge" },
      { t_start: 45_000, t_end: 60_000, v: 0.2, ar: 0.1, label: "outro" },
    ];
    const playbackMs = 35_000;

    expect(segmentCrossedBetween(sparse, playbackMs - 500, playbackMs)).toEqual({
      crossed: false,
      prevIdx: 0,
      currentIdx: 0,
    });
    expect(segmentCrossedBetween(detailed, playbackMs - 500, playbackMs)).toEqual({
      crossed: false,
      prevIdx: 1,
      currentIdx: 1,
    });
    expect(segmentCrossedBetween(detailed, playbackMs, playbackMs + 500)).toEqual({
      crossed: false,
      prevIdx: 1,
      currentIdx: 1,
    });
    expect(segmentCrossedBetween(detailed, 29_500, 30_500)).toEqual({
      crossed: true,
      prevIdx: 0,
      currentIdx: 1,
    });
  });
});
