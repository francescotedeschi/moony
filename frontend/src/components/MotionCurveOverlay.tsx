import { useLayoutEffect, useRef } from "react";

/** A single control-point for the Cyanite energy spline. */
export type CySegmentPoint = {
  /** Sample timestamp in milliseconds. */
  t_ms: number;
  /** Cyanite energy in [0, 1] — high = top of bar. */
  energy: number;
};

type Props = {
  durationMs: number;
  cyPoints?: CySegmentPoint[];
};

// ---------------------------------------------------------------------------
// Catmull-Rom spline helpers
// ---------------------------------------------------------------------------

type Pt = { x: number; y: number };

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
    const cp1x = p[i].x + (p[i + 1].x - p[i - 1].x) / 6;
    const cp1y = p[i].y + (p[i + 1].y - p[i - 1].y) / 6;
    const cp2x = p[i + 1].x - (p[i + 2].x - p[i].x) / 6;
    const cp2y = p[i + 1].y - (p[i + 2].y - p[i].y) / 6;
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p[i + 1].x, p[i + 1].y);
  }
}

export function MotionCurveOverlay({ durationMs, cyPoints }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const hasCy = (cyPoints?.length ?? 0) >= 2;

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || durationMs <= 0 || !hasCy) return;

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

      ctx.save();
      ctx.beginPath();
      ctx.roundRect(0, 0, w, h, h / 2);
      ctx.clip();

      const padY = h * 0.18;
      const innerH = h - padY * 2;

      if (hasCy && cyPoints) {
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
  }, [durationMs, cyPoints, hasCy]);

  if (!hasCy) return null;

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-[8] h-full w-full"
      aria-hidden
    />
  );
}
