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
    name: "Calm",
    v: 0,
    ar: -0.8,
    intent: 7,
    rgb: [34, 197, 94],
    dotClass: "bg-emerald-400",
    buttonClass: "border-emerald-400/40 text-emerald-300 hover:border-emerald-400",
  },
  {
    name: "Joy",
    v: 0.8,
    ar: 0.6,
    intent: 2,
    rgb: [250, 204, 21],
    dotClass: "bg-yellow-400",
    buttonClass: "border-yellow-400/40 text-yellow-200 hover:border-yellow-400",
  },
  {
    name: "Energy",
    v: 0.2,
    ar: 0.9,
    intent: 3,
    rgb: [239, 68, 68],
    dotClass: "bg-red-400",
    buttonClass: "border-red-400/40 text-red-300 hover:border-red-400",
  },
  {
    name: "Tension",
    v: -0.5,
    ar: 0.7,
    intent: 4,
    rgb: [249, 115, 22],
    dotClass: "bg-orange-400",
    buttonClass: "border-orange-400/40 text-orange-300 hover:border-orange-400",
  },
  {
    name: "Sad",
    v: -0.7,
    ar: -0.5,
    intent: 6,
    rgb: [168, 85, 247],
    dotClass: "bg-violet-400",
    buttonClass: "border-violet-400/40 text-violet-300 hover:border-violet-400",
  },
];

/** Solid bar colors — one per pad mood (no V/A gradients). */
export const MOOD_COLORS: Record<string, string> = {
  calm: "rgb(34, 197, 94)",
  joy: "rgb(250, 204, 21)",
  energy: "rgb(239, 68, 68)",
  tension: "rgb(249, 115, 22)",
  sad: "rgb(168, 85, 247)",
  neutral: "rgb(100, 116, 139)",
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

function emotionRgbWithVignette(v: number, ar: number, rgb: [number, number, number]): [number, number, number] {
  const edge = Math.min(1, Math.hypot(v, ar));
  const vignette = 0.72 + 0.28 * (1 - edge ** 1.6);
  return [
    Math.round(rgb[0] * vignette),
    Math.round(rgb[1] * vignette),
    Math.round(rgb[2] * vignette),
  ];
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

  return [Math.round(r / wSum), Math.round(g / wSum), Math.round(b / wSum)];
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

