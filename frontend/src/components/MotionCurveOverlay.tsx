import { useLayoutEffect, useRef } from "react";

import type { MotionPreviewPoint } from "../lib/api";

type Props = {
  points?: MotionPreviewPoint[];
  durationMs: number;
};

export function MotionCurveOverlay({ points, durationMs }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !points?.length || durationMs <= 0 || points.length < 2) {
      return;
    }

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
      const padY = h * 0.18;
      const innerH = h - padY * 2;

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
    };

    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [points, durationMs]);

  if (!points?.length || durationMs <= 0 || points.length < 2) {
    return null;
  }

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-[8] h-full w-full"
      aria-hidden
    />
  );
}
