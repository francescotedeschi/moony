import { describe, expect, it } from "vitest";
import {
  createLyricsSyncGate,
  LYRICS_ENTRY_TOLERANCE_MS,
  LYRICS_HANDOFF_HOLD_READS,
  LYRICS_TRUST_WINDOW_MS,
  resolveLyricsSyncMs,
} from "./lyricsSyncGate";

describe("resolveLyricsSyncMs", () => {
  it("holds entry while deferred seek is still near track start", () => {
    const gate = createLyricsSyncGate();
    const entry = 45_000;

    expect(resolveLyricsSyncMs(gate, 0, "track-a", entry)).toBe(0);
    expect(resolveLyricsSyncMs(gate, 2_500, "track-a", entry)).toBe(2_500);
    expect(gate.trustClock).toBe(false);
  });

  it("trusts once the clock lands on the entry point", () => {
    const gate = createLyricsSyncGate();
    const entry = 45_000;

    expect(resolveLyricsSyncMs(gate, entry, "track-a", entry)).toBe(entry);
    expect(gate.trustClock).toBe(true);

    expect(resolveLyricsSyncMs(gate, entry + 1_200, "track-a", entry)).toBe(entry + 1_200);
  });

  it("trusts seek overshoot within the post-entry window", () => {
    const gate = createLyricsSyncGate();
    const entry = 45_000;
    const overshoot = entry + 1_200;

    expect(resolveLyricsSyncMs(gate, overshoot, "track-a", entry)).toBe(overshoot);
    expect(gate.trustClock).toBe(true);
  });

  it("rejects stale outgoing clock far ahead of the new entry", () => {
    const gate = createLyricsSyncGate();
    const entry = 45_000;
    const stale = entry + LYRICS_TRUST_WINDOW_MS + 1;

    expect(resolveLyricsSyncMs(gate, stale, "track-b", entry)).toBe(entry);
    expect(gate.trustClock).toBe(false);
  });

  it("follows live playback when lyrics enable after the post-entry window", () => {
    const gate = createLyricsSyncGate();
    const entry = 45_000;
    const late = entry + LYRICS_TRUST_WINDOW_MS + 5_000;

    for (let i = 0; i < LYRICS_HANDOFF_HOLD_READS; i += 1) {
      expect(resolveLyricsSyncMs(gate, late, "track-a", entry)).toBe(entry);
      expect(gate.trustClock).toBe(false);
    }

    expect(resolveLyricsSyncMs(gate, late, "track-a", entry)).toBe(late);
    expect(gate.trustClock).toBe(true);
    expect(resolveLyricsSyncMs(gate, late + 1_000, "track-a", entry)).toBe(late + 1_000);
  });

  it("resets trust on track change", () => {
    const gate = createLyricsSyncGate();
    const entry = 45_000;

    resolveLyricsSyncMs(gate, entry, "track-a", entry);
    expect(gate.trustClock).toBe(true);

    const stale = 120_000;
    expect(resolveLyricsSyncMs(gate, stale, "track-b", entry)).toBe(entry);
    expect(gate.trustClock).toBe(false);
  });

  it("resets trust on same-track entry seek", () => {
    const gate = createLyricsSyncGate();

    resolveLyricsSyncMs(gate, 30_000, "track-a", 30_000);
    expect(gate.trustClock).toBe(true);

    expect(resolveLyricsSyncMs(gate, 80_000, "track-a", 80_000)).toBe(80_000);
    expect(gate.trustClock).toBe(true);
    expect(gate.entryMs).toBe(80_000);
  });

  it("keeps following playback after trust is established", () => {
    const gate = createLyricsSyncGate();
    const entry = 45_000;

    resolveLyricsSyncMs(gate, entry, "track-a", entry);
    const later = entry + LYRICS_TRUST_WINDOW_MS + 5_000;

    expect(resolveLyricsSyncMs(gate, later, "track-a", entry)).toBe(later);
  });

  it("accepts aligned clocks within entry tolerance", () => {
    const gate = createLyricsSyncGate();
    const entry = 45_000;
    const almost = entry + LYRICS_ENTRY_TOLERANCE_MS;

    expect(resolveLyricsSyncMs(gate, almost, "track-a", entry)).toBe(almost);
    expect(gate.trustClock).toBe(true);
  });

  it("handles entry at zero for tracks starting from the top", () => {
    const gate = createLyricsSyncGate();

    expect(resolveLyricsSyncMs(gate, 0, "track-a", 0)).toBe(0);
    expect(gate.trustClock).toBe(true);

    expect(resolveLyricsSyncMs(gate, 12_000, "track-a", 0)).toBe(12_000);
  });

  it("follows live playback before the matched entry point", () => {
    const gate = createLyricsSyncGate();
    const entry = 45_000;

    expect(resolveLyricsSyncMs(gate, 8_000, "track-a", entry)).toBe(8_000);
    expect(gate.trustClock).toBe(false);

    expect(resolveLyricsSyncMs(gate, 46_000, "track-a", entry)).toBe(46_000);
    expect(gate.trustClock).toBe(true);
  });
});
