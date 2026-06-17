import { describe, expect, it } from "vitest";
import { bloomIntensityForEnergy, energyAtTimeMs, flowIntensityScaleForEnergy } from "./energyCurve";

describe("energyAtTimeMs", () => {
  const values = [0.2, 0.5, 1];
  const ts = [0, 10_000, 20_000];

  it("interpolates between knots", () => {
    expect(energyAtTimeMs(values, ts, 5_000)).toBeCloseTo(0.35);
  });

  it("clamps before first and after last sample", () => {
    expect(energyAtTimeMs(values, ts, -1)).toBe(0.2);
    expect(energyAtTimeMs(values, ts, 99_000)).toBe(1);
  });
});

describe("bloomIntensityForEnergy", () => {
  it("scales with energy", () => {
    expect(bloomIntensityForEnergy(0)).toBeLessThan(bloomIntensityForEnergy(1));
    expect(bloomIntensityForEnergy(0.5)).toBeGreaterThan(0.1);
  });
});

describe("flowIntensityScaleForEnergy", () => {
  it("scales flow with energy", () => {
    expect(flowIntensityScaleForEnergy(0)).toBeLessThan(flowIntensityScaleForEnergy(1));
    expect(flowIntensityScaleForEnergy(0.5)).toBeCloseTo(0.95, 1);
  });
});
