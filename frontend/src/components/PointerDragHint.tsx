/** Onboarding: looping hand gesture suggesting dragging the dotted pointer. */
import { HandPointerIcon } from "./HandPointerIcon";

export function PointerDragHint({ visible }: { visible: boolean }) {
  if (!visible) return null;

  return (
    <div
      className="moony-pointer-drag-hint"
      data-testid="pad-drag-hint"
      aria-hidden
    >
      <svg
        width="60"
        height="60"
        viewBox="552 291 898 1401"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="moony-pointer-drag-hint-graphic"
      >
        <defs>
          <filter
            id="moony-hand-outline-shadow"
            x="-10%"
            y="-10%"
            width="120%"
            height="120%"
          >
            <feDropShadow
              dx="0"
              dy="6"
              stdDeviation="8"
              floodColor="#000000"
              floodOpacity="0.5"
            />
          </filter>
        </defs>

        <g
          stroke="white"
          strokeLinecap="round"
          fill="none"
          className="moony-pointer-drag-hint-swoosh"
        >
          <path
            strokeWidth="44"
            d="M 820 1050 C 660 920, 520 760, 360 560"
          />
          <path
            strokeWidth="32"
            opacity="0.65"
            d="M 880 1120 C 720 990, 580 830, 420 620"
          />
        </g>

        <HandPointerIcon filter="url(#moony-hand-outline-shadow)" />
      </svg>
    </div>
  );
}
