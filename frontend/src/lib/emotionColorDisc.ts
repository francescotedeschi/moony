import type { CatalogMoodSlice } from "./catalogMoodSlices";
import { blendEmotionColor } from "./emotions";

function parseHexBg(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  if (h.length === 6) {
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  return [10, 10, 15];
}

/** Draw emotion color wheel into an existing 2D context (canvas size unchanged). */
export function drawEmotionColorDiscOnContext(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  outsideRgb?: [number, number, number],
  catalogSlices?: readonly CatalogMoodSlice[] | null,
) {
  const size = ctx.canvas.width;
  const image = ctx.createImageData(size, size);
  const data = image.data;
  const outside = outsideRgb ?? [0, 0, 0];

  for (let py = 0; py < size; py++) {
    for (let px = 0; px < size; px++) {
      const dx = px - cx;
      const dy = py - cy;
      const dist = Math.hypot(dx, dy);
      const idx = (py * size + px) * 4;

      if (dist > r) {
        data[idx] = outside[0];
        data[idx + 1] = outside[1];
        data[idx + 2] = outside[2];
        data[idx + 3] = outsideRgb ? 255 : 0;
        continue;
      }

      const v = dx / r;
      const ar = -dy / r;
      const [red, green, blue] = blendEmotionColor(
        v,
        ar,
        catalogSlices?.length ? catalogSlices : null,
      );
      const edge = dist / r;
      const vignette = 0.72 + 0.28 * (1 - edge ** 1.6);

      data[idx] = red * vignette;
      data[idx + 1] = green * vignette;
      data[idx + 2] = blue * vignette;
      data[idx + 3] = 255;
    }
  }

  ctx.putImageData(image, 0, 0);
}

/** Standalone background canvas for the fluid pad. */
export function paintEmotionColorDisc(
  canvas: HTMLCanvasElement,
  discRadiusCss: number,
  backdrop = "#0a0a0f",
  catalogSlices?: readonly CatalogMoodSlice[] | null,
) {
  const dpr = window.devicePixelRatio || 1;
  const cssSize = canvas.clientWidth || canvas.offsetWidth || discRadiusCss * 2;
  if (!cssSize) return;

  canvas.width = Math.round(cssSize * dpr);
  canvas.height = Math.round(cssSize * dpr);

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  drawEmotionColorDiscOnContext(
    ctx,
    canvas.width / 2,
    canvas.height / 2,
    discRadiusCss * dpr,
    parseHexBg(backdrop),
    catalogSlices,
  );
}
