import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { DottedSpherePointer, DOTTED_POINTER_R, type DragMotion } from "./DottedSpherePointer";
import { PointerDragHint } from "./PointerDragHint";
import type { EmotionPadHandle } from "./EmotionPad";
import { createFluidSimulation, type FluidSimulation } from "../lib/fluidSimulation";
import { emotionFluidColorAtPadOffset, EMOTION_ZONES, padOffsetToVa, vaToPadOffset } from "../lib/emotions";
import type { CatalogMoodSlice } from "../lib/catalogMoodSlices";
import { loadCatalogMoodArcSlices } from "../lib/catalogMoodShares";
import { PeakEnvelopeFollower } from "../lib/audioPeakMeter";
import { bpmFlowIntensityScale } from "../lib/crossfadeTiming";
import { paintEmotionColorDisc } from "../lib/emotionColorDisc";

const PAD_SIZE = 480;
const WRAPPER_SIZE = 600;
const POINTER_R = DOTTED_POINTER_R;
const PAD_R = PAD_SIZE / 2;
/** Keep the dotted pointer fully inside the colored disc (center + radius ≤ PAD_R). */
const MAX_POINTER_DIST = PAD_R - POINTER_R;
/** Label radius as fraction of wrapper half-size — just outside the colored disc. */
const MOOD_LABEL_OUTER = 0.46;
const MOOD_LABEL_FONT_PX = 15;
/** Hysteresis so hover/wave does not flicker at the tracker edge. */
const POINTER_HIT_IN_SCALE = 1.1;
const POINTER_HIT_OUT_SCALE = 1.28;

export const FLUID_PAD_WRAPPER_PX = WRAPPER_SIZE;

type Point = { x: number; y: number };
type Va = { v: number; ar: number };

const DRAG_HINT_MOVE_PX = 10;

type Props = {
  onPositionChange: (v: number, ar: number) => void;
  onDragStart?: () => void;
  onDragEnd?: () => void;
  onPositionSettled?: (v: number, ar: number) => void;
  /** Looping hand on the dotted pointer until the user drags it once. */
  showDragHint?: boolean;
  /** Fired once when the user moves the dotted pointer by hand. */
  onPointerDragStarted?: () => void;
  interactionDisabled?: boolean;
  /** Drive fluid emission from playback envelope (visual only). */
  playbackEnvelopeActive?: boolean;
  sampleLinearPeak?: () => number;
  /** Current track BPM — scales envelope flow intensity. */
  playbackBpm?: number;
};

function clampToDisc(dx: number, dy: number): Point {
  const dist = Math.hypot(dx, dy);
  if (dist <= MAX_POINTER_DIST || dist < 1e-6) return { x: dx, y: dy };
  const s = MAX_POINTER_DIST / dist;
  return { x: dx * s, y: dy * s };
}

function vaToClampedPadOffset(v: number, ar: number): Point {
  const raw = vaToPadOffset(v, ar, PAD_R);
  return clampToDisc(raw.x, raw.y);
}

function offsetToVa(offset: Point): Va {
  return padOffsetToVa(offset.x, offset.y, PAD_R);
}

/** Joy-ward default — inset so the full sphere reads inside the disc on first paint. */
const DEFAULT_POINTER_VA = { v: 0.8, ar: 0.6 };
const DEFAULT_POINTER_OFFSET = (() => {
  const edge = vaToClampedPadOffset(DEFAULT_POINTER_VA.v, DEFAULT_POINTER_VA.ar);
  const inset = 0.78;
  return { x: edge.x * inset, y: edge.y * inset };
})();
const DEFAULT_POINTER_TARGET = offsetToVa(DEFAULT_POINTER_OFFSET);

function clientToPadOffset(clientX: number, clientY: number, padEl: HTMLElement): Point {
  const rect = padEl.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  return clampToDisc(clientX - cx, clientY - cy);
}

function offsetToClient(offset: Point, padEl: HTMLElement): { clientX: number; clientY: number } {
  const rect = padEl.getBoundingClientRect();
  return {
    clientX: rect.left + rect.width / 2 + offset.x,
    clientY: rect.top + rect.height / 2 + offset.y,
  };
}

/** Screen-pixel flow speed toward the pad center, scaled by meter level. */
const ENVELOPE_FLOW_SPEED_PX = 1.05;
/** Minimum meter excursion so flow stays visible between peaks. */
const ENVELOPE_METER_FLOOR = 0.12;

/** Offset fluid emission toward the pad center based on peak-meter excursion (0..1). */
function envelopeEmissionOffset(targetOffset: Point, meterT: number): Point {
  const delta = meterT * POINTER_R;
  if (delta < 1e-6) return targetOffset;
  const dist = Math.hypot(targetOffset.x, targetOffset.y);
  if (dist < 1e-6) return targetOffset;
  const towardCenterX = -targetOffset.x / dist;
  const towardCenterY = -targetOffset.y / dist;
  return {
    x: targetOffset.x + towardCenterX * delta,
    y: targetOffset.y + towardCenterY * delta,
  };
}

function envelopeFlowTowardCenter(emitOffset: Point, meterT: number, bpmScale: number): Point {
  const dist = Math.hypot(emitOffset.x, emitOffset.y);
  if (dist < 1e-6 || meterT < 1e-6) return { x: 0, y: 0 };
  const speed = ENVELOPE_FLOW_SPEED_PX * meterT * bpmScale;
  return {
    x: (-emitOffset.x / dist) * speed,
    y: (-emitOffset.y / dist) * speed,
  };
}

export const FluidEmotionPad = forwardRef<EmotionPadHandle, Props>(function FluidEmotionPad(
  {
    onPositionChange,
    onDragStart,
    onDragEnd,
    onPositionSettled,
    showDragHint = false,
    onPointerDragStarted,
    interactionDisabled,
    playbackEnvelopeActive = false,
    sampleLinearPeak,
    playbackBpm = 120,
  },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const colorDiscRef = useRef<HTMLCanvasElement>(null);
  const padRef = useRef<HTMLDivElement>(null);
  const simRef = useRef<FluidSimulation | null>(null);
  const dragging = useRef(false);
  const pointerPosRef = useRef<Point>(DEFAULT_POINTER_OFFSET);
  const prevPointerRef = useRef<Point>(DEFAULT_POINTER_OFFSET);
  const userTargetRef = useRef<Va>(DEFAULT_POINTER_TARGET);
  const dragMotionRef = useRef<DragMotion>({ vx: 0, vy: 0, active: false });
  const playbackDriveRef = useRef(false);
  const targetLockRef = useRef(false);
  const hasSongSampleRef = useRef(false);
  const songMoodTargetRef = useRef<Va>({ v: 0, ar: 0 });
  const blockedFluidHoldRef = useRef(false);
  const playbackEnvelopeHoldRef = useRef(false);
  const envelopeFollowerRef = useRef(new PeakEnvelopeFollower());
  const playbackBpmRef = useRef(playbackBpm);
  playbackBpmRef.current = playbackBpm;
  const playbackEnvelopeActiveRef = useRef(playbackEnvelopeActive);
  playbackEnvelopeActiveRef.current = playbackEnvelopeActive;
  const sampleLinearPeakRef = useRef(sampleLinearPeak);
  sampleLinearPeakRef.current = sampleLinearPeak;
  const capturedPointerIdRef = useRef<number | null>(null);
  const dragFromPointerRef = useRef(false);
  const dragHintOriginRef = useRef<Point | null>(null);
  const dragHintReportedRef = useRef(false);
  const interactionDisabledRef = useRef(interactionDisabled);
  const [pointerPos, setPointerPos] = useState<Point>(DEFAULT_POINTER_OFFSET);
  const [moodLabelsVisible, setMoodLabelsVisible] = useState(false);
  const [overPointer, setOverPointer] = useState(false);
  const overPointerStickyRef = useRef(false);
  const [isDragging, setIsDragging] = useState(false);

  pointerPosRef.current = pointerPos;
  const catalogSlicesRef = useRef<readonly CatalogMoodSlice[] | null>(null);
  interactionDisabledRef.current = interactionDisabled;

  useEffect(() => {
    const colorDisc = colorDiscRef.current;
    if (!colorDisc) return;

    const paint = (slices?: readonly CatalogMoodSlice[] | null) => {
      paintEmotionColorDisc(colorDisc, PAD_R, "#0a0a0f", slices);
    };

    paint();
    const rafPaint = requestAnimationFrame(() => paint(catalogSlicesRef.current));
    const observer = new ResizeObserver(() => paint(catalogSlicesRef.current));
    observer.observe(colorDisc);

    void loadCatalogMoodArcSlices()
      .then((slices) => {
        catalogSlicesRef.current = slices;
        paint(slices);
      })
      .catch(() => {
        /* pad keeps legacy blend until stats load */
      });

    return () => {
      cancelAnimationFrame(rafPaint);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const sim = createFluidSimulation(canvas, {
      simResolution: 64,
      dyeResolution: 256,
    });
    simRef.current = sim;

    return () => {
      sim.destroy();
      simRef.current = null;
    };
  }, []);

  const lockFilledToIntent = () => {
    targetLockRef.current = true;
    playbackDriveRef.current = false;
  };

  const resumePlaybackDrive = () => {
    targetLockRef.current = false;
    if (hasSongSampleRef.current) {
      playbackDriveRef.current = true;
    }
  };

  useImperativeHandle(
    ref,
    () => ({
      animateSongMoodTo(_v, _ar, _durationMs, onComplete) {
        onComplete?.();
      },
      setPlaybackMotion(v, ar) {
        if (dragging.current || targetLockRef.current) return;
        songMoodTargetRef.current = { v, ar };
        hasSongSampleRef.current = true;
        playbackDriveRef.current = true;
      },
      seedShadowMotion(v, ar) {
        songMoodTargetRef.current = { v, ar };
        hasSongSampleRef.current = true;
        playbackDriveRef.current = true;
        targetLockRef.current = false;
      },
      clearPlaybackDrive() {
        playbackDriveRef.current = false;
        targetLockRef.current = false;
        hasSongSampleRef.current = false;
      },
      lockFilledToIntent,
      resumePlaybackDrive,
      setUserTarget: (v: number, ar: number) => {
        const offset = vaToClampedPadOffset(v, ar);
        userTargetRef.current = offsetToVa(offset);
        prevPointerRef.current = offset;
        pointerPosRef.current = offset;
        setPointerPos(offset);
      },
      getUserTarget: () => ({ ...userTargetRef.current }),
    }),
    [],
  );

  const fluidColorAt = (offset: Point) => emotionFluidColorAtPadOffset(offset.x, offset.y, PAD_R);

  const syncSimPointer = (offset: Point, action: "down" | "move") => {
    const pad = padRef.current;
    if (!pad) return;
    const { clientX, clientY } = offsetToClient(offset, pad);
    const color = fluidColorAt(offset);
    if (action === "down") simRef.current?.pointerDown(clientX, clientY, color);
    else simRef.current?.pointerMove(clientX, clientY, color);
  };

  const syncSimAtClient = (clientX: number, clientY: number, action: "down" | "move") => {
    const pad = padRef.current;
    if (!pad) return;
    const offset = clientToPadOffset(clientX, clientY, pad);
    const color = fluidColorAt(offset);
    if (action === "down") simRef.current?.pointerDown(clientX, clientY, color);
    else simRef.current?.pointerMove(clientX, clientY, color);
  };

  const syncSimEnvelopeFlow = (emitOffset: Point, meterT: number, bpm: number) => {
    const pad = padRef.current;
    const sim = simRef.current;
    if (!pad || !sim) return;
    const { clientX, clientY } = offsetToClient(emitOffset, pad);
    const bpmScale = bpmFlowIntensityScale(bpm);
    const effectiveMeter = Math.max(meterT, ENVELOPE_METER_FLOOR);
    const flow = envelopeFlowTowardCenter(emitOffset, effectiveMeter, bpmScale);
    const color = fluidColorAt(pointerPosRef.current);
    sim.pointerEmitHold(clientX, clientY, color);
    sim.pointerEmitFlow(clientX, clientY, flow.x, flow.y, color, bpmScale);
    // Keep perimeter wave running — only user pointer drag should pause it.
    dragMotionRef.current = {
      vx: flow.x * (0.65 + effectiveMeter * 0.9),
      vy: flow.y * (0.65 + effectiveMeter * 0.9),
      active: false,
    };
  };

  const releasePlaybackEnvelopeHold = () => {
    if (!playbackEnvelopeHoldRef.current) return;
    playbackEnvelopeHoldRef.current = false;
    dragMotionRef.current = { vx: 0, vy: 0, active: false };
  };

  useEffect(() => {
    if (!sampleLinearPeakRef.current) return;

    let rafId = 0;

    const tick = () => {
      if (!playbackEnvelopeActiveRef.current) return;

      if (
        dragging.current ||
        interactionDisabledRef.current ||
        blockedFluidHoldRef.current
      ) {
        rafId = requestAnimationFrame(tick);
        return;
      }

      playbackEnvelopeHoldRef.current = true;
      const peak = sampleLinearPeakRef.current?.() ?? 0;
      const meterT = envelopeFollowerRef.current.push(peak);
      const emitOffset = envelopeEmissionOffset(pointerPosRef.current, meterT);
      syncSimEnvelopeFlow(emitOffset, meterT, playbackBpmRef.current);
      rafId = requestAnimationFrame(tick);
    };

    if (playbackEnvelopeActive) {
      envelopeFollowerRef.current.reset();
      rafId = requestAnimationFrame(tick);
    }

    return () => {
      cancelAnimationFrame(rafId);
      envelopeFollowerRef.current.reset();
      releasePlaybackEnvelopeHold();
    };
  }, [playbackEnvelopeActive, sampleLinearPeak]);

  useEffect(() => {
    if (interactionDisabled) {
      blockedFluidHoldRef.current = true;
      dragMotionRef.current = { vx: 0, vy: 0, active: false };
      syncSimPointer(pointerPosRef.current, "down");
      return;
    }

    if (blockedFluidHoldRef.current) {
      blockedFluidHoldRef.current = false;
      dragMotionRef.current = { vx: 0, vy: 0, active: false };
      simRef.current?.pointerUp();
    }
  }, [interactionDisabled]);

  const pointerHitDistance = (clientX: number, clientY: number) => {
    const pad = padRef.current;
    if (!pad) return Infinity;
    const rect = pad.getBoundingClientRect();
    const padCx = rect.left + rect.width / 2;
    const padCy = rect.top + rect.height / 2;
    const onPointer = pointerPosRef.current;
    return Math.hypot(clientX - padCx - onPointer.x, clientY - padCy - onPointer.y);
  };

  const hitPointerAt = (clientX: number, clientY: number) => {
    const dist = pointerHitDistance(clientX, clientY);
    const scale = overPointerStickyRef.current ? POINTER_HIT_OUT_SCALE : POINTER_HIT_IN_SCALE;
    return dist <= POINTER_R * scale;
  };

  const updatePointerHover = (clientX: number, clientY: number) => {
    if (interactionDisabledRef.current) return;
    const dist = pointerHitDistance(clientX, clientY);
    let next = overPointerStickyRef.current;
    if (next) {
      if (dist > POINTER_R * POINTER_HIT_OUT_SCALE) next = false;
    } else if (dist <= POINTER_R * POINTER_HIT_IN_SCALE) {
      next = true;
    }
    if (next !== overPointerStickyRef.current) {
      overPointerStickyRef.current = next;
      setOverPointer(next);
    }
  };

  const updateMoodLabelsForClient = (clientX: number, clientY: number) => {
    const pad = padRef.current;
    if (!pad) return;
    const rect = pad.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    setMoodLabelsVisible(Math.hypot(clientX - cx, clientY - cy) <= PAD_R);
    updatePointerHover(clientX, clientY);
  };

  const publishPointer = (offset: Point) => {
    const target = offsetToVa(offset);
    userTargetRef.current = target;
    onPositionChange(target.v, target.ar);
    return offset;
  };

  const applyPointerVisual = (clientX: number, clientY: number) => {
    const pad = padRef.current;
    if (!pad) return null;
    const next = clientToPadOffset(clientX, clientY, pad);
    prevPointerRef.current = next;
    pointerPosRef.current = next;
    setPointerPos(next);
    return next;
  };

  const reportPointerDragStarted = () => {
    if (dragHintReportedRef.current) return;
    dragHintReportedRef.current = true;
    dragHintOriginRef.current = null;
    onPointerDragStarted?.();
  };

  const applyPointer = (clientX: number, clientY: number, trackVelocity: boolean) => {
    const pad = padRef.current;
    if (!pad) return null;
    const next = clientToPadOffset(clientX, clientY, pad);
    if (trackVelocity) {
      const prev = prevPointerRef.current;
      dragMotionRef.current = {
        vx: next.x - prev.x,
        vy: next.y - prev.y,
        active: true,
      };
      if (dragFromPointerRef.current && dragHintOriginRef.current) {
        const o = dragHintOriginRef.current;
        if (Math.hypot(next.x - o.x, next.y - o.y) >= DRAG_HINT_MOVE_PX) {
          reportPointerDragStarted();
        }
      }
    }
    prevPointerRef.current = next;
    pointerPosRef.current = next;
    setPointerPos(next);
    publishPointer(next);
    return next;
  };

  const finishDrag = (e?: React.PointerEvent) => {
    if (!dragging.current) return;
    const wasTrackerDrag = dragFromPointerRef.current;
    dragging.current = false;
    setIsDragging(false);
    dragFromPointerRef.current = false;

    const pad = padRef.current;
    const pointerId = e?.pointerId ?? capturedPointerIdRef.current;
    if (pad && pointerId != null) {
      try {
        pad.releasePointerCapture(pointerId);
      } catch {
        /* already released */
      }
    }
    capturedPointerIdRef.current = null;

    if (!blockedFluidHoldRef.current) {
      dragMotionRef.current = { vx: 0, vy: 0, active: false };
      simRef.current?.pointerUp();
    }
    lockFilledToIntent();
    const { v, ar } = userTargetRef.current;
    onDragEnd?.();
    if (!interactionDisabledRef.current && wasTrackerDrag) {
      onPositionSettled?.(v, ar);
    }
    if (e) updateMoodLabelsForClient(e.clientX, e.clientY);
  };

  const pointerX = PAD_SIZE / 2 + pointerPos.x - POINTER_R;
  const pointerY = PAD_SIZE / 2 + pointerPos.y - POINTER_R;

  const padCursorClass = interactionDisabled
    ? "cursor-not-allowed"
    : isDragging && dragFromPointerRef.current
      ? "cursor-grabbing"
      : overPointer
        ? "cursor-pointer"
        : "cursor-default";

  return (
    <div
      className={`relative mx-auto ${interactionDisabled ? "opacity-60" : ""}`}
      style={{ width: WRAPPER_SIZE, height: WRAPPER_SIZE }}
      data-testid="fluid-emotion-pad"
    >
      {moodLabelsVisible
        ? EMOTION_ZONES.map((zone) => {
            const mag = Math.hypot(zone.v, zone.ar) || 1;
            const nx = zone.v / mag;
            const ny = zone.ar / mag;
            const [red, green, blue] = zone.rgb;
            return (
              <span
                key={zone.name}
                className="pointer-events-none absolute z-10 font-semibold"
                style={{
                  left: `${50 + nx * MOOD_LABEL_OUTER * 100}%`,
                  top: `${50 - ny * MOOD_LABEL_OUTER * 100}%`,
                  transform: "translate(-50%, -50%)",
                  fontSize: MOOD_LABEL_FONT_PX,
                  color: `rgb(${red}, ${green}, ${blue})`,
                  textShadow: "0 1px 4px rgba(0,0,0,0.85)",
                }}
              >
                {zone.name}
              </span>
            );
          })
        : null}

      <div
        ref={padRef}
        data-testid="emotion-pad"
        className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 touch-none overflow-hidden rounded-full ${padCursorClass}`}
        style={{
          width: PAD_SIZE,
          height: PAD_SIZE,
          boxShadow: "inset 0 0 40px rgba(0, 0, 0, 0.35)",
        }}
        onPointerEnter={(e) => updateMoodLabelsForClient(e.clientX, e.clientY)}
        onPointerLeave={() => {
          setMoodLabelsVisible(false);
          overPointerStickyRef.current = false;
          setOverPointer(false);
        }}
        onPointerDown={(e) => {
          if (interactionDisabled) return;
          updateMoodLabelsForClient(e.clientX, e.clientY);
          const pad = padRef.current;
          if (!pad) return;

          const rect = pad.getBoundingClientRect();
          const padCx = rect.left + rect.width / 2;
          const padCy = rect.top + rect.height / 2;

          const hitPad = Math.hypot(e.clientX - padCx, e.clientY - padCy) <= PAD_R;
          const hitPointer = hitPointerAt(e.clientX, e.clientY);

          if (!hitPad && !hitPointer) return;

          dragging.current = true;
          setIsDragging(true);
          dragFromPointerRef.current = hitPointer;
          targetLockRef.current = false;
          playbackDriveRef.current = false;
          onDragStart?.();
          capturedPointerIdRef.current = e.pointerId;
          pad.setPointerCapture(e.pointerId);

          if (hitPointer) {
            dragMotionRef.current = { vx: 0, vy: 0, active: true };
            if (showDragHint && !dragHintReportedRef.current) {
              dragHintOriginRef.current = { ...pointerPosRef.current };
            }
            syncSimPointer(pointerPosRef.current, "down");
          } else {
            dragMotionRef.current = { vx: 0, vy: 0, active: false };
            syncSimAtClient(e.clientX, e.clientY, "down");
          }
        }}
        onPointerMove={(e) => {
          updateMoodLabelsForClient(e.clientX, e.clientY);
          if (!dragging.current) return;

          if (dragFromPointerRef.current) {
            if (interactionDisabled && blockedFluidHoldRef.current) {
              const next = applyPointerVisual(e.clientX, e.clientY);
              if (next) syncSimPointer(next, "move");
              return;
            }
            const next = applyPointer(e.clientX, e.clientY, true);
            if (next) syncSimPointer(next, "move");
            return;
          }

          if (interactionDisabled && blockedFluidHoldRef.current) return;
          syncSimAtClient(e.clientX, e.clientY, "move");
        }}
        onPointerUp={(e) => finishDrag(e)}
        onPointerCancel={(e) => finishDrag(e)}
        onLostPointerCapture={(e) => finishDrag(e)}
      >
        <canvas
          ref={colorDiscRef}
          className="pointer-events-none absolute inset-0 block h-full w-full"
          style={{ width: PAD_SIZE, height: PAD_SIZE }}
        />
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 block h-full w-full"
          style={{ width: PAD_SIZE, height: PAD_SIZE }}
        />
        <div
          className="pointer-events-none absolute z-10 overflow-visible"
          style={{
            left: pointerX,
            top: pointerY,
            width: POINTER_R * 2,
            height: POINTER_R * 2,
          }}
        >
          <DottedSpherePointer
            padOffset={pointerPos}
            colorDiscR={PAD_R}
            dragMotionRef={dragMotionRef}
            hovered={overPointer || (isDragging && dragFromPointerRef.current)}
            className="absolute inset-0"
          />
          <PointerDragHint visible={showDragHint && !isDragging} />
        </div>
      </div>
    </div>
  );
});
