import { FLUID_PAD_WRAPPER_PX } from "./FluidEmotionPad";

/** Colored mood disc diameter — matches FluidEmotionPad PAD_SIZE. */
const PAD_DISC_PX = 480;
/** Ring sits just outside the colored disc edge. */
const ORBIT_RING_PX = PAD_DISC_PX + 14;

export function PadOrbitLoader() {
  return (
    <div
      className="moony-pad-orbit-loader"
      role="status"
      aria-label="Loading track"
      data-testid="pad-track-switch-loader"
      style={{
        width: ORBIT_RING_PX,
        height: ORBIT_RING_PX,
        left: FLUID_PAD_WRAPPER_PX / 2,
        top: FLUID_PAD_WRAPPER_PX / 2,
      }}
    >
      <svg viewBox="0 0 100 100" className="moony-pad-orbit-loader__svg" aria-hidden>
        <circle cx="50" cy="50" r="47.5" className="moony-pad-orbit-loader__track" />
        <circle cx="50" cy="50" r="47.5" className="moony-pad-orbit-loader__arc" />
      </svg>
    </div>
  );
}
