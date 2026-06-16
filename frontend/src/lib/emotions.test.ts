import { describe, expect, it } from "vitest";
import { EMOTION_ZONES, pickRandomSessionSeedTarget } from "./emotions";

describe("pickRandomSessionSeedTarget", () => {
  it("returns a pad target for Calm, Joy, or Energy", () => {
    const allowed = EMOTION_ZONES.filter((z) =>
      ["Calm", "Joy", "Energy"].includes(z.name),
    ).map((z) => `${z.v},${z.ar}`);

    for (let i = 0; i < 20; i += 1) {
      const target = pickRandomSessionSeedTarget();
      expect(allowed).toContain(`${target.v},${target.ar}`);
    }
  });
});
