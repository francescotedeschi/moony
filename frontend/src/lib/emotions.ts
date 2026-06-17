import type { CatalogMoodSlice } from "./catalogMoodSlices";
import { getCatalogMoodArcSlices } from "./catalogMoodShares";

/** Pad emotion zones — label positions on the UI (catalog search uses mapped targets server-side). */
export type EmotionZone = {
  name: string;
  v: number;
  ar: number;
  intent: number;
  rgb: [number, number, number];
  dotClass: string;
  buttonClass: string;
};

export const EMOTION_ZONES: EmotionZone[] = [
  {
    name: "Energetic",
    v: 0.24,
    ar: 0.67,
    intent: 3,
    rgb: [239, 68, 68],
    dotClass: "bg-red-400",
    buttonClass: "border-red-400/40 text-red-300 hover:border-red-400",
  },
  {
    name: "Happy",
    v: 0.65,
    ar: 0.25,
    intent: 2,
    rgb: [250, 204, 21],
    dotClass: "bg-yellow-400",
    buttonClass: "border-yellow-400/40 text-yellow-200 hover:border-yellow-400",
  },
  {
    name: "Chilled",
    v: 0.29,
    ar: -0.18,
    intent: 8,
    rgb: [34, 197, 94],
    dotClass: "bg-emerald-400",
    buttonClass: "border-emerald-400/40 text-emerald-300 hover:border-emerald-400",
  },
  {
    name: "Romantic",
    v: 0.10,
    ar: -0.10,
    intent: 9,
    rgb: [244, 114, 182],
    dotClass: "bg-pink-400",
    buttonClass: "border-pink-400/40 text-pink-300 hover:border-pink-400",
  },
  {
    name: "Sad",
    v: -0.27,
    ar: -0.14,
    intent: 6,
    rgb: [168, 85, 247],
    dotClass: "bg-violet-400",
    buttonClass: "border-violet-400/40 text-violet-300 hover:border-violet-400",
  },
  {
    name: "Dark",
    v: -0.28,
    ar: 0.13,
    intent: 4,
    rgb: [100, 116, 139],
    dotClass: "bg-slate-400",
    buttonClass: "border-slate-400/40 text-slate-300 hover:border-slate-400",
  },
  {
    name: "Tense",
    v: -0.50,
    ar: 0.70,
    intent: 10,
    rgb: [249, 115, 22],
    dotClass: "bg-orange-400",
    buttonClass: "border-orange-400/40 text-orange-300 hover:border-orange-400",
  },
];

const SESSION_SEED_MOOD_NAMES = new Set(["Chilled", "Happy", "Energetic"]);

/** Random opener mood for the first track of a browser session. */
export function pickRandomSessionSeedTarget(): { v: number; ar: number } {
  const zones = EMOTION_ZONES.filter((zone) => SESSION_SEED_MOOD_NAMES.has(zone.name));
  const zone = zones[Math.floor(Math.random() * zones.length)] ?? EMOTION_ZONES[1];
  return { v: zone.v, ar: zone.ar };
}

/** Solid bar colors — one per pad mood (no V/A gradients). */
export const MOOD_COLORS: Record<string, string> = {
  energetic: "rgb(239, 68, 68)",
  happy:     "rgb(250, 204, 21)",
  chilled:   "rgb(34, 197, 94)",
  romantic:  "rgb(244, 114, 182)",
  sad:       "rgb(168, 85, 247)",
  dark:      "rgb(100, 116, 139)",
  tense:     "rgb(249, 115, 22)",
  neutral:   "rgb(71, 85, 105)",
  // Legacy aliases — kept for backward compat with MOSS labels
  calm:      "rgb(34, 197, 94)",
  joy:       "rgb(250, 204, 21)",
  energy:    "rgb(239, 68, 68)",
  tension:   "rgb(249, 115, 22)",
};

export function moodColorForName(name: string): string {
  const key = name.trim().toLowerCase();
  return MOOD_COLORS[key] ?? MOOD_COLORS.neutral;
}

/** Display label for catalog / segment emotion strings. */
export function formatCatalogMood(label: string | undefined): string {
  if (!label?.trim()) return "—";
  const lower = label.trim().toLowerCase();
  const zone = EMOTION_ZONES.find((z) => z.name.toLowerCase() === lower);
  if (zone) return zone.name;
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

export function moodColorForVa(v: number, ar: number): string {
  return moodColorForName(nearestEmotionZone(v, ar).name);
}

/**
 * ## Mood nomenclature (Moony)
 *
 * **Target mood** — where the user placed the pad pointer (`getUserTarget`).
 * Resolved to the nearest zone: Calm, Joy, Energy, Tension, Sad.
 *
 * **Segment mood** — `emotion_label` and V/A of the MOSS segment at the playhead
 * (what the song is expressing right now).
 *
 * **Pad zone prefetch** (Joy, Calm, …) — next track per pad zone. Initial load
 * uses standard ranking; while the **target mood** stays on the same zone for
 * ≥30s, that zone's prefetch is replaced with candidates where
 * `mood_distribution ≥ 0.5` on the target label (used for handoff + match rows).
 *
 * **Segment mood slot** (`SEGMENT_MOOD_INTENT`, API key `"0"`) — legacy backend
 * bucket for **segment mood** (live playhead), not pad target. Unused in the UI.
 */
export const SEGMENT_MOOD_INTENT = 0;
/** @deprecated Use {@link SEGMENT_MOOD_INTENT}. Segment mood, not pad target. */
export const SAME_MOOD_INTENT = SEGMENT_MOOD_INTENT;

export type VA = { v: number; ar: number };

export function vaDistance(a: VA, b: VA): number {
  return Math.hypot(a.v - b.v, a.ar - b.ar);
}

/** Vignette multiplier for pad radius (0 = center, 1 = edge). */
export function moodpadDiscEdgeVignette(edge: number): number {
  return moodpadEdgeVignette(edge);
}

function moodpadEdgeVignette(edge: number): number {
  return 0.84 + 0.16 * (1 - Math.min(1, edge) ** 1.5);
}

function emotionRgbWithVignette(v: number, ar: number, rgb: [number, number, number]): [number, number, number] {
  const edge = Math.hypot(v, ar);
  const vignette = moodpadEdgeVignette(edge);
  return [
    Math.round(rgb[0] * vignette),
    Math.round(rgb[1] * vignette),
    Math.round(rgb[2] * vignette),
  ];
}

/** Push RGB away from luminance — factor > 1 increases perceived saturation. */
function boostRgbSaturation(rgb: [number, number, number], factor: number): [number, number, number] {
  const luma = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2];
  return [
    Math.round(Math.max(0, Math.min(255, luma + (rgb[0] - luma) * factor))),
    Math.round(Math.max(0, Math.min(255, luma + (rgb[1] - luma) * factor))),
    Math.round(Math.max(0, Math.min(255, luma + (rgb[2] - luma) * factor))),
  ];
}

function boostRgbBrightness(rgb: [number, number, number], factor: number): [number, number, number] {
  return [
    Math.round(Math.max(0, Math.min(255, rgb[0] * factor))),
    Math.round(Math.max(0, Math.min(255, rgb[1] * factor))),
    Math.round(Math.max(0, Math.min(255, rgb[2] * factor))),
  ];
}

const MOODPAD_COLOR_SATURATION = 1.72;
const MOODPAD_COLOR_BRIGHTNESS = 1.14;

function finishMoodpadRgb(rgb: [number, number, number]): [number, number, number] {
  return boostRgbBrightness(boostRgbSaturation(rgb, MOODPAD_COLOR_SATURATION), MOODPAD_COLOR_BRIGHTNESS);
}

function catalogShareForZone(
  zone: EmotionZone,
  catalogSlices: readonly CatalogMoodSlice[],
): number {
  const slice = catalogSlices.find(
    (s) => s.label.toLowerCase() === zone.name.toLowerCase(),
  );
  return slice?.share ?? 0;
}

/**
 * Inverse-distance blend between pad mood anchors.
 * With catalog slices, each zone's weight is scaled by its catalog share
 * while keeping smooth gradients between neighbors.
 */
export function blendEmotionColor(
  v: number,
  ar: number,
  catalogSlices?: readonly CatalogMoodSlice[] | null,
): [number, number, number] {
  const blendPower = 1.35;
  const blendEps = 0.06;
  let wSum = 0;
  let r = 0;
  let g = 0;
  let b = 0;

  for (const zone of EMOTION_ZONES) {
    const d2 = (v - zone.v) ** 2 + (ar - zone.ar) ** 2;
    let w = 1 / (d2 + blendEps) ** blendPower;
    if (catalogSlices?.length) {
      w *= catalogShareForZone(zone, catalogSlices);
    }
    wSum += w;
    r += w * zone.rgb[0];
    g += w * zone.rgb[1];
    b += w * zone.rgb[2];
  }

  if (wSum <= 0) {
    return blendEmotionColor(v, ar);
  }

  return finishMoodpadRgb(
    [Math.round(r / wSum), Math.round(g / wSum), Math.round(b / wSum)],
  );
}

/** Colored mood disc radius ratio on the legacy pad canvas. */
export const PAD_COLOR_DISC_RATIO = 0.38;

export function padOffsetToVa(dx: number, dy: number, discRadius: number): VA {
  return {
    v: dx / discRadius,
    ar: -dy / discRadius,
  };
}

export function vaToPadOffset(v: number, ar: number, discRadius: number): { x: number; y: number } {
  return { x: v * discRadius, y: -ar * discRadius };
}

/** RGB at a pad offset, including edge vignette from the legacy field. */
export function emotionColorAtPadOffset(
  dx: number,
  dy: number,
  discRadius: number,
  catalogSlices?: readonly CatalogMoodSlice[] | null,
): [number, number, number] {
  const { v, ar } = padOffsetToVa(dx, dy, discRadius);
  const slices = catalogSlices ?? getCatalogMoodArcSlices();
  return emotionRgbWithVignette(
    v,
    ar,
    blendEmotionColor(v, ar, slices?.length ? slices : null),
  );
}

/** Convert 0–255 emotion RGB to WebGL fluid dye intensity. */
export function emotionRgbToFluidSplat(rgb: [number, number, number]): { r: number; g: number; b: number } {
  const scale = 0.15 / 255;
  return { r: rgb[0] * scale, g: rgb[1] * scale, b: rgb[2] * scale };
}

export function emotionFluidColorAtPadOffset(
  dx: number,
  dy: number,
  discRadius: number,
): { r: number; g: number; b: number } {
  return emotionRgbToFluidSplat(emotionColorAtPadOffset(dx, dy, discRadius));
}

/** Nearest labeled emotion zone for a pad coordinate. */
export function nearestEmotionZone(v: number, ar: number): EmotionZone {
  let best = EMOTION_ZONES[0];
  let bestD = Infinity;
  for (const zone of EMOTION_ZONES) {
    const d = (v - zone.v) ** 2 + (ar - zone.ar) ** 2;
    if (d < bestD) {
      bestD = d;
      best = zone;
    }
  }
  return best;
}

