import { useLayoutEffect, useRef } from "react";

import type { MotionPreviewPoint } from "../lib/api";

/** A single control-point for the Cyanite energy spline. */
export type CySegmentPoint = {
  /** Sample timestamp in milliseconds. */
  t_ms: number;
  /** Cyanite energy in [0, 1] — high = top of bar. */
  energy: number;
};

type Props = {
  points?: MotionPreviewPoint[];
  durationMs: number;
  /** Cyanite arousal sampled at segment midpoints — drawn as a second spline. */
  cyPoints?: CySegmentPoint[];
};

// ---------------------------------------------------------------------------
// Catmull-Rom spline helpers
// ---------------------------------------------------------------------------

type Pt = { x: number; y: number };

/**
 * Draw a Catmull-Rom spline through `pts` onto `ctx`.
 * Uses ghost boundary points so the curve passes through every data point.
 * When `xBounds` is set, ghost x is pinned to the track edges so the spline
 * does not overshoot past the rounded timeline ends.
 */
function drawCatmullRom(
  ctx: CanvasRenderingContext2D,
  pts: Pt[],
  xBounds?: { min: number; max: number },
): void {
  if (pts.length < 2) return;

  const ghostStart = {
    x: 2 * pts[0].x - pts[1].x,
    y: 2 * pts[0].y - pts[1].y,
  };
  const ghostEnd = {
    x: 2 * pts[pts.length - 1].x - pts[pts.length - 2].x,
    y: 2 * pts[pts.length - 1].y - pts[pts.length - 2].y,
  };

  if (xBounds) {
    ghostStart.x = xBounds.min;
    ghostEnd.x = xBounds.max;
  }

  const p = [ghostStart, ...pts, ghostEnd];

  ctx.moveTo(pts[0].x, pts[0].y);

  for (let i = 1; i < p.length - 2; i++) {
    // Catmull-Rom → Cubic Bezier conversion (tension = 1/6)
    const cp1x = p[i].x + (p[i + 1].x - p[i - 1].x) / 6;
    const cp1y = p[i].y + (p[i + 1].y - p[i - 1].y) / 6;
    const cp2x = p[i + 1].x - (p[i + 2].x - p[i].x) / 6;
    const cp2y = p[i + 1].y - (p[i + 2].y - p[i].y) / 6;
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p[i + 1].x, p[i + 1].y);
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MotionCurveOverlay({ points, durationMs, cyPoints }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const hasMoss = (points?.length ?? 0) >= 2;
  const hasCy = (cyPoints?.length ?? 0) >= 2;

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || durationMs <= 0 || (!hasMoss && !hasCy)) return;

    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) return;

      const dpr = window.devicePixelRatio || 1;
      const w = Math.floor(rect.width * dpr);
      const h = Math.floor(rect.height * dpr);
      canvas.width = w;
      canvas.height = h;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.clearRect(0, 0, w, h);

      // Clip to pill shape so curves (and their glow) stay inside rounded ends.
      ctx.save();
      ctx.beginPath();
      ctx.roundRect(0, 0, w, h, h / 2);
      ctx.clip();

      const padY = h * 0.18;
      const innerH = h - padY * 2;

      // ── MOSS motion curve (existing, straight line-to segments) ──────────
      if (hasMoss && points) {
        ctx.beginPath();
        points.forEach((p, i) => {
          const x = (p.t_ms / durationMs) * w;
          const y = padY + (1 - p.y) * innerH;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });

        const grad = ctx.createLinearGradient(0, 0, w, 0);
        grad.addColorStop(0, "rgba(167, 139, 250, 0.25)");
        grad.addColorStop(0.45, "rgba(255, 255, 255, 0.92)");
        grad.addColorStop(1, "rgba(124, 108, 255, 0.25)");

        ctx.strokeStyle = grad;
        ctx.lineWidth = Math.max(1.2, 1.65 * dpr);
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.shadowColor = "rgba(167, 139, 250, 0.45)";
        ctx.shadowBlur = 5 * dpr;
        ctx.stroke();
      }

      // ── Cyanite energy spline (Catmull-Rom, white) ─────────────────────
      if (hasCy && cyPoints) {
        // energy ∈ [0, 1] → y (top = high energy)
        const pts: Pt[] = cyPoints.map((p) => ({
          x: (p.t_ms / durationMs) * w,
          y: padY + (1 - p.energy) * innerH,
        }));

        ctx.shadowColor = "rgba(255, 255, 255, 0.45)";
        ctx.shadowBlur = 5 * dpr;

        ctx.beginPath();
        drawCatmullRom(ctx, pts, { min: 0, max: w });

        const cyGrad = ctx.createLinearGradient(0, 0, w, 0);
        cyGrad.addColorStop(0, "rgba(255, 255, 255, 0.35)");
        cyGrad.addColorStop(0.5, "rgba(255, 255, 255, 0.92)");
        cyGrad.addColorStop(1, "rgba(255, 255, 255, 0.35)");

        ctx.strokeStyle = cyGrad;
        ctx.lineWidth = Math.max(1.0, 1.4 * dpr);
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.stroke();

        ctx.shadowBlur = 0;
      }

      ctx.restore();
    };

    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [points, durationMs, cyPoints, hasMoss, hasCy]);

  if (!hasMoss && !hasCy) return null;

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-[8] h-full w-full"
      aria-hidden
    />
  );
}
