/**
 * Pad semantics (do not invert):
 * - Filled white dot = user emotion TARGET (drag / release → match API `position`).
 * - Animated water shadow = CURRENT track mood (motion poll / crossfade entry only).
 */
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { EMOTION_ZONES } from "../lib/emotions";
import { drawEmotionColorDiscOnContext } from "../lib/emotionColorDisc";

type Props = {
  onPositionChange: (v: number, ar: number) => void;
  onDragStart?: () => void;
  /** Fired once when a pad drag ends (pointer up or leave). */
  onDragEnd?: () => void;
  /** Fired after drag end with the final target (for match). */
  onPositionSettled?: (v: number, ar: number) => void;
  /** Block drag / match while audio is switching tracks. */
  interactionDisabled?: boolean;
};

export type EmotionPadHandle = {
  animateSongMoodTo: (v: number, ar: number, durationMs: number, onComplete?: () => void) => void;
  setPlaybackMotion: (v: number, ar: number) => void;
  seedShadowMotion: (v: number, ar: number) => void;
  clearPlaybackDrive: () => void;
  lockFilledToIntent: () => void;
  resumePlaybackDrive: () => void;
  /** Move the user pointer to a pad V/A target. */
  setUserTarget: (v: number, ar: number) => void;
  /** White-dot user target (not live song shadow). */
  getUserTarget: () => { v: number; ar: number };
};

type Point = { v: number; ar: number };

const EMOTIONS = EMOTION_ZONES.map((z) => ({
  text: z.name,
  v: z.v,
  ar: z.ar,
  rgb: z.rgb,
}));

const LIVE_INERTIA = 0.82;
const LABEL_FONT_PX = 15;
const LABEL_OUTER = 0.4;
const SCALE = 1.5;
const CANVAS_SIZE = Math.round(320 * SCALE);
const WRAPPER_SIZE = Math.round(400 * SCALE);

/** Layout size of the pad wrapper (for overlays aligned to the Mentos disc). */
export const EMOTION_PAD_WRAPPER_PX = WRAPPER_SIZE;
const PAD_RADIUS_RATIO = 0.38;
const MENTOS_RING_RATIO = 0.105;
const POINTER_BASE_R = 10 * SCALE;
const POINTER_R = POINTER_BASE_R * 3;
/** Max fraction of pointer radius that may extend past the colored disc edge. */
const POINTER_OVERHANG_RATIO = 0.2;

function maxPointerCenterDist(padR: number, pointerR: number): number {
  return Math.max(0, padR - pointerR * (1 - POINTER_OVERHANG_RATIO));
}

function drawEmotionField(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  drawEmotionColorDiscOnContext(ctx, cx, cy, r);
}

/** White Mentos-style rim around the colored mood disc. */
function drawMentosCandy(ctx: CanvasRenderingContext2D, cx: number, cy: number, padR: number) {
  const outerR = padR * (1 + MENTOS_RING_RATIO);

  ctx.save();

  ctx.shadowColor = "rgba(0, 0, 0, 0.45)";
  ctx.shadowBlur = 18 * SCALE;
  ctx.shadowOffsetY = 6 * SCALE;

  const body = ctx.createRadialGradient(cx - outerR * 0.22, cy - outerR * 0.28, outerR * 0.05, cx, cy, outerR);
  body.addColorStop(0, "#ffffff");
  body.addColorStop(0.45, "#f4f4f0");
  body.addColorStop(0.82, "#e6e6de");
  body.addColorStop(1, "#d4d4cc");
  ctx.fillStyle = body;
  ctx.beginPath();
  ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
  ctx.fill();

  ctx.shadowColor = "transparent";
  ctx.shadowBlur = 0;
  ctx.shadowOffsetY = 0;

  const gloss = ctx.createRadialGradient(
    cx - outerR * 0.35,
    cy - outerR * 0.4,
    0,
    cx - outerR * 0.1,
    cy - outerR * 0.15,
    outerR * 0.85,
  );
  gloss.addColorStop(0, "rgba(255, 255, 255, 0.72)");
  gloss.addColorStop(0.35, "rgba(255, 255, 255, 0.18)");
  gloss.addColorStop(1, "rgba(255, 255, 255, 0)");
  ctx.fillStyle = gloss;
  ctx.beginPath();
  ctx.arc(cx, cy, outerR * 0.92, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = "rgba(255, 255, 255, 0.55)";
  ctx.lineWidth = 1.5 * SCALE;
  ctx.beginPath();
  ctx.arc(cx, cy, outerR - 1, 0, Math.PI * 2);
  ctx.stroke();

  ctx.restore();
}

/** User target — white Mentos dragee (3D), 3× base size. */
function drawMentosPointer(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  const squash = 0.94;
  const rx = r;
  const ry = r * squash;

  ctx.save();

  ctx.shadowColor = "rgba(0, 0, 0, 0.5)";
  ctx.shadowBlur = r * 0.35;
  ctx.shadowOffsetY = r * 0.12;

  const body = ctx.createRadialGradient(
    x - rx * 0.32,
    y - ry * 0.38,
    r * 0.04,
    x + rx * 0.08,
    y + ry * 0.12,
    r * 1.05,
  );
  body.addColorStop(0, "#ffffff");
  body.addColorStop(0.35, "#f6f6f2");
  body.addColorStop(0.7, "#e8e8e0");
  body.addColorStop(1, "#c8c8be");
  ctx.fillStyle = body;
  ctx.beginPath();
  ctx.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.shadowColor = "transparent";
  ctx.shadowBlur = 0;
  ctx.shadowOffsetY = 0;

  const gloss = ctx.createRadialGradient(
    x - rx * 0.42,
    y - ry * 0.48,
    0,
    x - rx * 0.12,
    y - ry * 0.18,
    r * 0.75,
  );
  gloss.addColorStop(0, "rgba(255, 255, 255, 0.95)");
  gloss.addColorStop(0.4, "rgba(255, 255, 255, 0.35)");
  gloss.addColorStop(1, "rgba(255, 255, 255, 0)");
  ctx.fillStyle = gloss;
  ctx.beginPath();
  ctx.ellipse(x, y - ry * 0.06, rx * 0.88, ry * 0.72, 0, 0, Math.PI * 2);
  ctx.fill();

  const rim = ctx.createLinearGradient(x - rx, y - ry, x + rx, y + ry);
  rim.addColorStop(0, "rgba(255, 255, 255, 0.7)");
  rim.addColorStop(0.5, "rgba(200, 198, 190, 0.15)");
  rim.addColorStop(1, "rgba(90, 88, 82, 0.35)");
  ctx.strokeStyle = rim;
  ctx.lineWidth = Math.max(1.5, r * 0.06);
  ctx.beginPath();
  ctx.ellipse(x, y, rx - 1, ry - 1, 0, 0, Math.PI * 2);
  ctx.stroke();

  const spec = ctx.createRadialGradient(x - rx * 0.25, y - ry * 0.3, 0, x - rx * 0.25, y - ry * 0.3, r * 0.22);
  spec.addColorStop(0, "rgba(255, 255, 255, 1)");
  spec.addColorStop(1, "rgba(255, 255, 255, 0)");
  ctx.fillStyle = spec;
  ctx.beginPath();
  ctx.ellipse(x - rx * 0.22, y - ry * 0.28, r * 0.18, r * 0.12, -0.4, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3;
}

function lerpPoint(prev: Point, target: Point, inertia: number): Point {
  const t = 1 - inertia;
  return {
    v: prev.v + (target.v - prev.v) * t,
    ar: prev.ar + (target.ar - prev.ar) * t,
  };
}

function drawSongMoodShadow(ctx: CanvasRenderingContext2D, x: number, y: number, t: number) {
  ctx.save();

  const poolR = 38 * SCALE;
  const pool = ctx.createRadialGradient(x, y, 0, x, y, poolR);
  pool.addColorStop(0, "rgba(10, 14, 26, 0.38)");
  pool.addColorStop(0.4, "rgba(10, 14, 26, 0.2)");
  pool.addColorStop(0.75, "rgba(10, 14, 26, 0.06)");
  pool.addColorStop(1, "rgba(10, 14, 26, 0)");
  ctx.fillStyle = pool;
  ctx.beginPath();
  ctx.arc(x, y, poolR, 0, Math.PI * 2);
  ctx.fill();

  for (let i = 0; i < 3; i++) {
    const phase = t * 2.4 + i * 2.09;
    const breathe = 0.5 + 0.5 * Math.sin(phase);
    const wobbleX = Math.sin(phase * 1.6) * 2 * SCALE;
    const wobbleY = Math.cos(phase * 1.4) * 2 * SCALE;
    const rx = (10 + i * 5 + Math.sin(phase * 1.25) * 2.5) * SCALE;
    const ry = (10 + i * 5 + Math.cos(phase * 1.35) * 2.5) * SCALE;
    const alpha = 0.1 + 0.14 * breathe;

    ctx.strokeStyle = `rgba(18, 26, 42, ${alpha * 0.85})`;
    ctx.lineWidth = 1.4 * SCALE;
    ctx.beginPath();
    ctx.ellipse(x + wobbleX, y + wobbleY, rx, ry, phase * 0.22, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = `rgba(210, 228, 255, ${alpha * 0.45})`;
    ctx.lineWidth = 0.9 * SCALE;
    ctx.beginPath();
    ctx.ellipse(x + wobbleX * 0.6, y + wobbleY * 0.6, rx + 1.2, ry + 1.2, -phase * 0.18, 0, Math.PI * 2);
    ctx.stroke();
  }

  const shimmer = 0.3 + 0.18 * Math.sin(t * 3.8);
  const highlight = ctx.createRadialGradient(x, y - 2, 0, x, y, 9 * SCALE);
  highlight.addColorStop(0, `rgba(255, 255, 255, ${shimmer})`);
  highlight.addColorStop(1, "rgba(255, 255, 255, 0)");
  ctx.fillStyle = highlight;
  ctx.beginPath();
  ctx.arc(x, y, 9 * SCALE, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

/** Map pointer to V/A; center clamped so at most 20% of pointer radius crosses the colored disc. */
function pointerToVa(
  e: React.PointerEvent<HTMLCanvasElement>,
  canvas: HTMLCanvasElement,
  padR: number,
): Point | null {
  const rect = canvas.getBoundingClientRect();
  const scale = canvas.width / rect.width;
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;
  const dx = (e.clientX - rect.left) * scale - cx;
  const dy = (e.clientY - rect.top) * scale - cy;
  const dist = Math.hypot(dx, dy);
  const maxCenter = maxPointerCenterDist(padR, POINTER_R);
  if (dist > maxCenter * 1.001) {
    if (dist < 1e-6) return { v: 0, ar: 0 };
    const clamped = maxCenter / dist;
    return {
      v: Math.max(-1, Math.min(1, (dx * clamped) / padR)),
      ar: Math.max(-1, Math.min(1, (-dy * clamped) / padR)),
    };
  }
  return {
    v: Math.max(-1, Math.min(1, dx / padR)),
    ar: Math.max(-1, Math.min(1, -dy / padR)),
  };
}

function pointerEventCanvasCoords(
  e: React.PointerEvent<HTMLCanvasElement>,
  canvas: HTMLCanvasElement,
): { dx: number; dy: number } {
  const rect = canvas.getBoundingClientRect();
  const scale = canvas.width / rect.width;
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;
  return {
    dx: (e.clientX - rect.left) * scale - cx,
    dy: (e.clientY - rect.top) * scale - cy,
  };
}

function canStartPointerDrag(
  e: React.PointerEvent<HTMLCanvasElement>,
  canvas: HTMLCanvasElement,
  padR: number,
  pointer: Point,
): boolean {
  const { dx, dy } = pointerEventCanvasCoords(e, canvas);
  if (Math.hypot(dx, dy) <= padR) return true;
  const px = pointer.v * padR;
  const py = -pointer.ar * padR;
  return Math.hypot(dx - px, dy - py) <= POINTER_R * 1.05;
}

export const EmotionPad = forwardRef<EmotionPadHandle, Props>(function EmotionPad(
  { onPositionChange, onDragStart, onDragEnd, onPositionSettled, interactionDisabled },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [userTarget, setUserTargetState] = useState<Point>({ v: 0, ar: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragging = useRef(false);
  const playbackDriveRef = useRef(false);
  const targetLockRef = useRef(false);
  const songAnimatingRef = useRef(false);
  const userTargetRef = useRef(userTarget);
  const songMoodRef = useRef<Point>({ v: 0, ar: 0 });
  const songMoodTargetRef = useRef<Point>({ v: 0, ar: 0 });
  const songAnimRef = useRef<number | null>(null);
  const ripplePhaseRef = useRef(0);
  const filledRef = useRef<Point>({ v: 0, ar: 0 });
  const hasSongSampleRef = useRef(false);

  userTargetRef.current = userTarget;

  const cancelSongAnim = () => {
    if (songAnimRef.current !== null) {
      cancelAnimationFrame(songAnimRef.current);
      songAnimRef.current = null;
    }
    songAnimatingRef.current = false;
  };

  const animateSongMoodTo = (v: number, ar: number, durationMs: number, onComplete?: () => void) => {
    cancelSongAnim();
    const from = { ...songMoodRef.current };
    const to = { v, ar };

    if (durationMs <= 0) {
      songMoodRef.current = to;
      songMoodTargetRef.current = to;
      hasSongSampleRef.current = true;
      onComplete?.();
      return;
    }

    songAnimatingRef.current = true;
    hasSongSampleRef.current = true;
    const start = performance.now();
    const step = (now: number) => {
      const t = easeOutCubic(Math.min(1, (now - start) / durationMs));
      songMoodRef.current = {
        v: from.v + (to.v - from.v) * t,
        ar: from.ar + (to.ar - from.ar) * t,
      };
      if (t < 1) {
        songAnimRef.current = requestAnimationFrame(step);
      } else {
        songMoodRef.current = to;
        songMoodTargetRef.current = to;
        songAnimRef.current = null;
        songAnimatingRef.current = false;
        onComplete?.();
      }
    };
    songAnimRef.current = requestAnimationFrame(step);
  };

  const seedShadowMotion = (v: number, ar: number) => {
    const pos = { v, ar };
    songMoodTargetRef.current = pos;
    songMoodRef.current = pos;
    hasSongSampleRef.current = true;
    playbackDriveRef.current = true;
    targetLockRef.current = false;
  };

  const setPlaybackMotion = (v: number, ar: number) => {
    if (dragging.current || targetLockRef.current || songAnimatingRef.current) return;
    songMoodTargetRef.current = { v, ar };
    hasSongSampleRef.current = true;
    playbackDriveRef.current = true;
  };

  const clearPlaybackDrive = () => {
    playbackDriveRef.current = false;
    targetLockRef.current = false;
    hasSongSampleRef.current = false;
  };

  const lockFilledToIntent = () => {
    const pos = { ...userTargetRef.current };
    targetLockRef.current = true;
    playbackDriveRef.current = false;
    filledRef.current = pos;
  };

  const finishDrag = () => {
    if (!dragging.current) return;
    dragging.current = false;
    setIsDragging(false);
    lockFilledToIntent();
    const { v, ar } = userTargetRef.current;
    onPositionSettled?.(v, ar);
    onDragEnd?.();
  };

  const resumePlaybackDrive = () => {
    targetLockRef.current = false;
    if (hasSongSampleRef.current) {
      playbackDriveRef.current = true;
    }
  };

  const setUserTarget = (v: number, ar: number) => {
    const next = { v, ar };
    userTargetRef.current = next;
    setUserTargetState(next);
  };

  useImperativeHandle(
    ref,
    () => ({
      animateSongMoodTo,
      setPlaybackMotion,
      seedShadowMotion,
      clearPlaybackDrive,
      lockFilledToIntent,
      resumePlaybackDrive,
      setUserTarget,
      getUserTarget: () => ({ ...userTargetRef.current }),
    }),
    [],
  );

  useEffect(() => () => cancelSongAnim(), []);

  useEffect(() => {
    let frame = 0;
    const tick = () => {
      ripplePhaseRef.current += 0.045;

      const nextFilled = dragging.current
        ? lerpPoint(filledRef.current, userTargetRef.current, 0.35)
        : userTargetRef.current;
      filledRef.current = nextFilled;

      if (hasSongSampleRef.current && !songAnimatingRef.current && songAnimRef.current === null) {
        if (targetLockRef.current) {
          songMoodRef.current = lerpPoint(songMoodRef.current, userTargetRef.current, 0.22);
        } else if (playbackDriveRef.current) {
          songMoodRef.current = lerpPoint(songMoodRef.current, songMoodTargetRef.current, LIVE_INERTIA);
        }
      }

      const canvas = canvasRef.current;
      const ctx = canvas?.getContext("2d");
      if (canvas && ctx) {
        const size = canvas.width;
        const cx = size / 2;
        const cy = size / 2;
        const padR = size * PAD_RADIUS_RATIO;
        const songPt = songMoodRef.current;
        const targetPt = userTargetRef.current;
        const filledPt = nextFilled;
        const draggingNow = dragging.current;
        const pointerR = POINTER_R;
        const targetRingR = POINTER_R * 1.12;

        ctx.clearRect(0, 0, size, size);
        drawMentosCandy(ctx, cx, cy, padR);
        drawEmotionField(ctx, cx, cy, padR);

        ctx.strokeStyle = "rgba(255,255,255,0.2)";
        ctx.lineWidth = 1.5 * SCALE;
        ctx.beginPath();
        ctx.arc(cx, cy, padR, 0, Math.PI * 2);
        ctx.stroke();

        const showSongShadow =
          !dragging.current &&
          (playbackDriveRef.current || songAnimatingRef.current || targetLockRef.current);
        if (showSongShadow) {
          const sx = cx + songPt.v * padR;
          const sy = cy - songPt.ar * padR;
          drawSongMoodShadow(ctx, sx, sy, ripplePhaseRef.current);
        }

        const fx = cx + filledPt.v * padR;
        const fy = cy - filledPt.ar * padR;
        drawMentosPointer(ctx, fx, fy, pointerR);

        if (draggingNow) {
          const px = cx + targetPt.v * padR;
          const py = cy - targetPt.ar * padR;
          ctx.strokeStyle = "rgba(255,255,255,0.28)";
          ctx.lineWidth = 2 * SCALE;
          ctx.setLineDash([5, 6]);
          ctx.beginPath();
          ctx.ellipse(px, py, targetRingR, targetRingR * 0.94, 0, 0, Math.PI * 2);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }

      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  const applyPointer = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const padR = canvas.width * PAD_RADIUS_RATIO;
    const pt = pointerToVa(e, canvas, padR);
    if (!pt) return;
    setUserTargetState(pt);
    onPositionChange(pt.v, pt.ar);
  };

  return (
    <div
      className={`mx-auto flex flex-col items-center ${interactionDisabled ? "pointer-events-none opacity-60" : ""}`}
      style={{ width: WRAPPER_SIZE, height: WRAPPER_SIZE }}
    >
      <div className="relative h-full w-full">
        <canvas
          ref={canvasRef}
          data-testid="emotion-pad"
          width={CANVAS_SIZE}
          height={CANVAS_SIZE}
          className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 touch-none ${
            interactionDisabled ? "cursor-not-allowed" : "cursor-crosshair"
          }`}
          style={{ width: CANVAS_SIZE, height: CANVAS_SIZE }}
          onPointerDown={(e) => {
            if (interactionDisabled) return;
            const canvas = canvasRef.current;
            if (!canvas) return;
            const padR = canvas.width * PAD_RADIUS_RATIO;
            if (!canStartPointerDrag(e, canvas, padR, userTargetRef.current)) return;

            dragging.current = true;
            targetLockRef.current = false;
            playbackDriveRef.current = false;
            setIsDragging(true);
            cancelSongAnim();
            onDragStart?.();
            canvas.setPointerCapture(e.pointerId);
            applyPointer(e);
          }}
          onPointerMove={(e) => dragging.current && applyPointer(e)}
          onPointerUp={finishDrag}
          onPointerCancel={finishDrag}
          onLostPointerCapture={finishDrag}
        />
        {isDragging
          ? EMOTIONS.map((e) => {
              const mag = Math.hypot(e.v, e.ar) || 1;
              const nx = e.v / mag;
              const ny = e.ar / mag;
              const [red, green, blue] = e.rgb;
              return (
                <span
                  key={e.text}
                  className="pointer-events-none absolute font-semibold"
                  style={{
                    left: `${50 + nx * LABEL_OUTER * 100}%`,
                    top: `${50 - ny * LABEL_OUTER * 100}%`,
                    transform: "translate(-50%, -50%)",
                    fontSize: LABEL_FONT_PX * SCALE,
                    color: `rgb(${red}, ${green}, ${blue})`,
                    textShadow: "0 1px 4px rgba(0,0,0,0.85)",
                  }}
                >
                  {e.text}
                </span>
              );
            })
          : null}
      </div>
    </div>
  );
});
