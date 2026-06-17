import { useEffect, useRef, type CSSProperties, type RefObject } from "react";
import { emotionColorAtPadOffset } from "../lib/emotions";

export const DOTTED_POINTER_R = 63;
const SIZE = DOTTED_POINTER_R * 2;
const GRID_STEP = 7;
const MAX_DOT_R = 3.4;
const MIN_DOT_R = 1.05;
/** Light direction for a soft convex-sphere read (top-left, toward viewer). */
const LIGHT = { x: -0.32, y: -0.38, z: 0.86 };

const WAVE_PERIOD_REST_S = 2.6;
const WAVE_PERIOD_HOVER_S = 1.05;
const WAVE_PERIOD_LERP = 0.14;
const WAVE_BAND = 0.22;
const WAVE_LAYERS = 2;
/** Normalized radius band where perimeter dots fade with the wave (inner stays always visible). */
const WAVE_EDGE_START = 0.62;
const WAVE_EDGE_FULL = 0.88;

/** Max radial spacing shift (fraction of radius from center). */
const DRAG_SPEED_FULL = 4.5;
const LEAD_FOLLOW = 0.58;
const TRAIL_SPRING = 0.05;
const TRAIL_DAMPING = 0.92;
const REST_FOLLOW = 0.2;
const REST_TRAIL_FOLLOW = 0.032;
/** Comet envelope: tail narrows and streams backward while the head stays round. */
const COMET_BACK_PUSH = 0.72;
const COMET_WING_NARROW = 0.94;
const COMET_HEAD_PUFF = 0.14;
const COMET_LEAD_COMPRESS = 0.28;
const COMET_TAIL_FADE = 0.55;

export type DragMotion = {
  vx: number;
  vy: number;
  active: boolean;
};

/** Outward ripple: 0 at rest, 1 when the wave front crosses this radius. */
function waveBoost(normalizedRadius: number, wavePhase: number): number {
  let boost = 0;

  for (let layer = 0; layer < WAVE_LAYERS; layer++) {
    const stagger = layer / WAVE_LAYERS;
    const progress = (wavePhase + stagger) % 1;
    const front = progress * 1.1;
    const delta = Math.abs(normalizedRadius - front);
    if (delta >= WAVE_BAND) continue;

    const envelope = 0.5 * (1 + Math.cos((Math.PI * delta) / WAVE_BAND));
    boost = Math.max(boost, envelope);
  }

  return boost;
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const u = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)));
  return u * u * (3 - 2 * u);
}

/** 0 = center (always visible), 1 = perimeter (full wave fade). */
function perimeterWaveWeight(normalizedRadius: number): number {
  return smoothstep(WAVE_EDGE_START, WAVE_EDGE_FULL, normalizedRadius);
}

function drawDotWithShadow(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  red: number,
  green: number,
  blue: number,
  alpha: number,
) {
  const shadowX = 0.45;
  const shadowY = 0.65;
  const shadowR = r * 1.05;
  const shadowAlpha = Math.min(0.58, (0.2 + alpha * 0.82) * 0.88);

  ctx.fillStyle = `rgba(0, 0, 0, ${shadowAlpha.toFixed(3)})`;
  ctx.beginPath();
  ctx.arc(x + shadowX, y + shadowY, shadowR, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = `rgba(${red}, ${green}, ${blue}, ${alpha.toFixed(3)})`;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();

  if (r > 1.35) {
    ctx.fillStyle = `rgba(255, 255, 255, ${(alpha * 0.28).toFixed(3)})`;
    ctx.beginPath();
    ctx.arc(x - r * 0.24, y - r * 0.26, r * 0.34, 0, Math.PI * 2);
    ctx.fill();
  }
}

type Velocity = { vx: number; vy: number };

type DotState = {
  x: number;
  y: number;
  vx: number;
  vy: number;
};

function dotAlignment(localX: number, localY: number, velocity: Velocity): number {
  const dist = Math.hypot(localX, localY);
  const speed = Math.hypot(velocity.vx, velocity.vy);
  if (dist < 0.5 || speed < 0.001) return 0;
  const moveX = velocity.vx / speed;
  const moveY = velocity.vy / speed;
  return ((localX / dist) * moveX + (localY / dist) * moveY);
}

/** Comet-shaped drag target: narrow tail, rounded head, trailing spacing expansion. */
function computeCometTarget(
  localX: number,
  localY: number,
  pointerRadius: number,
  velocity: Velocity,
  amount: number,
): { x: number; y: number; alignment: number; tailFade: number } {
  const dist = Math.hypot(localX, localY);
  if (amount < 0.01 || dist < 0.5) {
    return { x: localX, y: localY, alignment: dotAlignment(localX, localY, velocity), tailFade: 1 };
  }

  const speed = Math.hypot(velocity.vx, velocity.vy);
  if (speed < 0.001) {
    return { x: localX, y: localY, alignment: 0, tailFade: 1 };
  }

  const moveX = velocity.vx / speed;
  const moveY = velocity.vy / speed;
  let along = localX * moveX + localY * moveY;
  let perpX = localX - along * moveX;
  let perpY = localY - along * moveY;
  const perpDist = Math.hypot(perpX, perpY);

  const dirX = localX / dist;
  const dirY = localY / dist;
  const alignment = dirX * moveX + dirY * moveY;

  const alongNorm = along / pointerRadius;
  const wing = Math.min(1, perpDist / pointerRadius);
  const trail = Math.max(0, -alongNorm);
  const tailT = Math.min(1, trail);

  // Side dots (high wing) fold backward into the tail — strongest at trailing edge.
  const wingFold = wing * wing;
  const backStrength = amount * (trail * (0.35 + 0.65 * wingFold) + wingFold * 0.42 * (1 - Math.max(0, alongNorm)));
  along -= backStrength * COMET_BACK_PUSH * pointerRadius;

  // Perpendicular squeeze: collapse radius toward motion axis, tighter toward tail tip.
  const narrowStrength = amount * (0.18 + 0.82 * tailT * tailT) * (0.25 + 0.75 * wing);
  const perpScale = Math.max(0.06, 1 - narrowStrength * COMET_WING_NARROW);
  perpX *= perpScale;
  perpY *= perpScale;

  let tailFade = 1 - amount * COMET_TAIL_FADE * tailT ** 1.25 * (0.35 + 0.65 * wing);

  if (along > 0) {
    const headT = Math.min(1, along / pointerRadius);
    const headScale = 1 + amount * COMET_HEAD_PUFF * headT;
    perpX *= headScale;
    perpY *= headScale;
  }

  let x = along * moveX + perpX;
  let y = along * moveY + perpY;

  // Leading hemisphere only: slight compression (no trailing radial expansion — it breaks the comet).
  if (alignment > 0.05) {
    const newDist = Math.hypot(x, y);
    if (newDist > 0.5) {
      const compress = 1 - alignment * amount * COMET_LEAD_COMPRESS;
      x *= compress;
      y *= compress;
    }
  }

  return { x, y, alignment, tailFade: Math.max(0.1, tailFade) };
}

function wingFromDelta(deltaX: number, deltaY: number, pointerRadius: number): number {
  const dist = Math.hypot(deltaX, deltaY);
  return Math.min(1, dist / Math.max(1, pointerRadius));
}

function stepDotState(
  state: DotState,
  restX: number,
  restY: number,
  targetX: number,
  targetY: number,
  alignment: number,
  dragging: boolean,
  spacingAmount: number,
  pointerRadius: number,
) {
  const trail = Math.max(0, -alignment);
  const returning = !dragging || spacingAmount < 0.008;
  const tx = returning ? restX : targetX;
  const ty = returning ? restY : targetY;

  if (!returning && alignment < -0.04) {
    const ax = (tx - state.x) * TRAIL_SPRING * spacingAmount;
    const ay = (ty - state.y) * TRAIL_SPRING * spacingAmount;
    state.vx = (state.vx + ax) * TRAIL_DAMPING;
    state.vy = (state.vy + ay) * TRAIL_DAMPING;
    state.x += state.vx;
    state.y += state.vy;
    return;
  }

  if (!returning && alignment > 0.04) {
    state.x += (tx - state.x) * LEAD_FOLLOW;
    state.y += (ty - state.y) * LEAD_FOLLOW;
    state.vx *= 0.45;
    state.vy *= 0.45;
    return;
  }

  // Side / equator dots: faster follow so the comet cone reads while dragging.
  if (!returning) {
    const sideFollow = 0.42 + wingFromDelta(tx - restX, ty - restY, pointerRadius) * 0.18;
    state.vx *= 0.62;
    state.vy *= 0.62;
    state.x += (tx - state.x) * sideFollow + state.vx;
    state.y += (ty - state.y) * sideFollow + state.vy;
    return;
  }

  const follow = REST_FOLLOW - trail * (REST_FOLLOW - REST_TRAIL_FOLLOW);
  state.vx *= 0.7;
  state.vy *= 0.7;
  state.x += (tx - state.x) * follow + state.vx;
  state.y += (ty - state.y) * follow + state.vy;
}

function drawDotMatrix(
  ctx: CanvasRenderingContext2D,
  dpr: number,
  padOffset: { x: number; y: number },
  colorDiscR: number,
  velocity: Velocity,
  spacingAmount: number,
  dragging: boolean,
  wavePhase: number,
  dotStates: Map<string, DotState>,
) {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, SIZE, SIZE);

  const cx = SIZE / 2;
  const cy = SIZE / 2;
  const radius = DOTTED_POINTER_R - 1.5;

  for (let gy = GRID_STEP / 2; gy < SIZE; gy += GRID_STEP) {
    for (let gx = GRID_STEP / 2; gx < SIZE; gx += GRID_STEP) {
      const dx = gx - cx;
      const dy = gy - cy;
      const dist = Math.hypot(dx, dy);
      if (dist > radius) continue;

      const t = dist / radius;
      const falloff = (1 - t) ** 1.55;
      if (falloff < 0.04) continue;

      const key = `${gx},${gy}`;
      let state = dotStates.get(key);
      if (!state) {
        state = { x: dx, y: dy, vx: 0, vy: 0 };
        dotStates.set(key, state);
      }

      const target = computeCometTarget(dx, dy, radius, velocity, spacingAmount);
      stepDotState(state, dx, dy, target.x, target.y, target.alignment, dragging, spacingAmount, radius);

      const drawX = cx + state.x;
      const drawY = cy + state.y;

      const nx = dx / radius;
      const ny = dy / radius;
      const nz = Math.sqrt(Math.max(0, 1 - nx * nx - ny * ny));
      const shade = 0.68 + 0.32 * Math.max(0, nx * LIGHT.x + ny * LIGHT.y + nz * LIGHT.z);

      const ripple = dragging ? 0 : waveBoost(t, wavePhase);
      const edgeWeight = perimeterWaveWeight(t);
      const waveVisibility = 1 - ripple * edgeWeight;

      const dotR = (MIN_DOT_R + (MAX_DOT_R - MIN_DOT_R) * falloff) * (1 + 0.38 * ripple);
      const alpha = Math.min(
        1,
        (0.38 + 0.78 * falloff) * shade * (1 + 0.55 * ripple) * target.tailFade * waveVisibility,
      );
      if (alpha < 0.015) continue;

      const [r, g, b] = emotionColorAtPadOffset(
        padOffset.x + state.x,
        padOffset.y + state.y,
        colorDiscR,
      );
      const lit = 1 + 0.22 * ripple;
      const red = Math.min(255, Math.round(r * shade * lit));
      const green = Math.min(255, Math.round(g * shade * lit));
      const blue = Math.min(255, Math.round(b * shade * lit));

      drawDotWithShadow(ctx, drawX, drawY, dotR, red, green, blue, alpha);
    }
  }
}

type Props = {
  padOffset: { x: number; y: number };
  colorDiscR: number;
  dragMotionRef: RefObject<DragMotion>;
  /** Cursor over the tracker — speeds up perimeter wave. */
  hovered?: boolean;
  className?: string;
  style?: CSSProperties;
};

export function DottedSpherePointer({
  padOffset,
  colorDiscR,
  dragMotionRef,
  hovered = false,
  className,
  style,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const padOffsetRef = useRef(padOffset);
  const hoveredRef = useRef(hovered);
  const wavePeriodRef = useRef(WAVE_PERIOD_REST_S);
  const smoothVelocityRef = useRef<Velocity>({ vx: 0, vy: 0 });
  const spacingAmountRef = useRef(0);

  padOffsetRef.current = padOffset;
  hoveredRef.current = hovered;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(SIZE * dpr);
    canvas.height = Math.round(SIZE * dpr);

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let rafId = 0;
    let lastNow = performance.now();
    let wavePhase = 0;
    const dotStates = new Map<string, DotState>();

    const tick = (now: number) => {
      const dt = Math.min(0.05, Math.max(0, (now - lastNow) * 0.001));
      lastNow = now;
      const motion = dragMotionRef.current ?? { vx: 0, vy: 0, active: false };
      const smooth = smoothVelocityRef.current;
      const spacing = spacingAmountRef.current;
      const userDragging = motion.active;

      if (userDragging) {
        smooth.vx += (motion.vx - smooth.vx) * 0.62;
        smooth.vy += (motion.vy - smooth.vy) * 0.62;
        const target = Math.min(1, Math.hypot(motion.vx, motion.vy) / DRAG_SPEED_FULL);
        spacingAmountRef.current = spacing + (target - spacing) * 0.5;
      } else {
        smooth.vx *= 0.82;
        smooth.vy *= 0.82;
        spacingAmountRef.current = spacing * 0.86;
      }

      const targetPeriod = hoveredRef.current ? WAVE_PERIOD_HOVER_S : WAVE_PERIOD_REST_S;
      wavePeriodRef.current +=
        (targetPeriod - wavePeriodRef.current) * WAVE_PERIOD_LERP;
      wavePhase = (wavePhase + dt / wavePeriodRef.current) % 1;

      drawDotMatrix(
        ctx,
        dpr,
        padOffsetRef.current,
        colorDiscR,
        smooth,
        spacingAmountRef.current,
        userDragging,
        wavePhase,
        dotStates,
      );
      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [colorDiscR, dragMotionRef]);

  return (
    <canvas
      ref={canvasRef}
      data-testid="dotted-pointer-tracker"
      className={className}
      width={SIZE}
      height={SIZE}
      style={{ width: SIZE, height: SIZE, ...style }}
      aria-hidden
    />
  );
}
