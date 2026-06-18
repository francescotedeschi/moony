import { describe, expect, it } from "vitest";
import {
  hasLyricsAtTime,
  LYRICS_SYNC_LEAD_MS,
  lyricAtTime,
  prepareLyricLines,
} from "./lyricsSync";

const lines = [
  { t_ms: 5_000, text: "First line", line_index: 0 },
  { t_ms: 12_000, text: "Second line", line_index: 1 },
  { t_ms: 20_000, text: "", line_index: 2 },
  { t_ms: 28_000, text: "Third line", line_index: 3 },
];

describe("hasLyricsAtTime", () => {
  it("is false before the first timed line", () => {
    expect(hasLyricsAtTime(lines, 2_000)).toBe(false);
  });

  it("is true while inside a lyric line window", () => {
    expect(hasLyricsAtTime(lines, 6_000)).toBe(true);
    expect(hasLyricsAtTime(lines, 11_500)).toBe(true);
  });

  it("is false before the first line and after the last line window", () => {
    expect(hasLyricsAtTime(lines, 4_000)).toBe(false);
    expect(hasLyricsAtTime(lines, 40_000)).toBe(false);
  });

  it("is false on empty timed lines", () => {
    expect(hasLyricsAtTime(lines, 21_000)).toBe(false);
  });

  it("accepts prepared lines", () => {
    const prepared = prepareLyricLines(lines);
    expect(hasLyricsAtTime(prepared, 29_000)).toBe(true);
    expect(lyricAtTime(prepared, 29_000)?.text).toBe("Third line");
  });

  it("returns the same line for visibility and display", () => {
    const at = lyricAtTime(lines, 6_000);
    expect(at?.text).toBe("First line");
    expect(hasLyricsAtTime(lines, 6_000)).toBe(true);
    expect(lyricAtTime(lines, 4_000)).toBeNull();
  });

  it("hides lyrics during instrumental gaps inside a timed line window", () => {
    expect(
      lyricAtTime(lines, 6_000, LYRICS_SYNC_LEAD_MS, { vocalLevel: 0.2 }),
    ).toBeNull();
    expect(
      lyricAtTime(lines, 6_000, LYRICS_SYNC_LEAD_MS, { vocalLevel: 0.5 })?.text,
    ).toBe("First line");
  });
});
