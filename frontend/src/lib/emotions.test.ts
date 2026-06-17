import { describe, expect, it } from "vitest";
import { EMOTION_ZONES, pickRandomSessionSeedTarget } from "./emotions";

describe("pickRandomSessionSeedTarget", () => {
  it("returns a pad target for Chilled, Happy, or Energetic", () => {
    const allowed = EMOTION_ZONES.filter((z) =>
      ["Chilled", "Happy", "Energetic"].includes(z.name),
    ).map((z) => `${z.v},${z.ar}`);

    for (let i = 0; i < 20; i += 1) {
      const target = pickRandomSessionSeedTarget();
      expect(allowed).toContain(`${target.v},${target.ar}`);
    }
  });
});
