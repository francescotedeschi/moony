import { useCallback, useEffect, useRef, useState } from "react";

type Props = {
  volume: number;
  muted: boolean;
  onVolumeChange: (level: number) => void;
  onToggleMute: () => void;
};

const iconClass = "h-[18px] w-[18px] shrink-0";

function SpeakerIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 9v6h4l5 4V5L8 9H4z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      <path
        d="M16 9.5a4.5 4.5 0 010 5"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <path
        d="M18.5 7a7.5 7.5 0 010 10"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MutedIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 9v6h4l5 4V5L8 9H4z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      <path
        d="M15 9l4 6M19 9l-4 6"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Long-press threshold in ms — used only on touch devices. */
const LONG_PRESS_MS = 380;

export function VolumeControl({ volume, muted, onVolumeChange, onToggleMute }: Props) {
  const [open, setOpen] = useState(false);
  const leaveTimerRef = useRef(0);

  // Mobile long-press state
  const longPressTimerRef = useRef(0);
  const longPressTriggeredRef = useRef(false);
  const pointerTypeRef = useRef("");

  useEffect(() => () => {
    window.clearTimeout(leaveTimerRef.current);
    window.clearTimeout(longPressTimerRef.current);
  }, []);

  const showPopover = useCallback(() => {
    window.clearTimeout(leaveTimerRef.current);
    setOpen(true);
  }, []);

  const hidePopoverSoon = useCallback(() => {
    window.clearTimeout(leaveTimerRef.current);
    leaveTimerRef.current = window.setTimeout(() => setOpen(false), 120);
  }, []);

  const displayVolume = muted ? 0 : volume;
  const pct = Math.round(displayVolume * 100);

  return (
    <div
      className="relative flex items-center"
      onMouseEnter={showPopover}
      onMouseLeave={hidePopoverSoon}
    >
      {open ? (
        <div
          className="absolute bottom-full left-1/2 z-20 mb-3 -translate-x-1/2"
          onMouseEnter={showPopover}
          onMouseLeave={hidePopoverSoon}
        >
          <div className="moony-volume-popover">
            <div className="moony-volume-slider-wrap">
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={pct}
                aria-label="Volume"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={pct}
                aria-valuetext={`${pct} percent`}
                className="moony-volume-slider"
                style={{ ["--moony-vol-pct" as string]: `${pct}%` }}
                onChange={(e) => onVolumeChange(Number(e.target.value) / 100)}
                onClick={(e) => e.stopPropagation()}
              />
            </div>
          </div>
          <div
            className="mx-auto h-0 w-0 border-x-[7px] border-t-[8px] border-x-transparent border-t-black"
            aria-hidden
          />
        </div>
      ) : null}

      <button
        type="button"
        aria-label={muted ? "Unmute" : "Mute"}
        title={muted ? "Unmute" : "Mute"}
        onPointerDown={(e) => {
          pointerTypeRef.current = e.pointerType;
          if (e.pointerType !== "touch") return;
          // Start long-press timer for touch devices
          longPressTriggeredRef.current = false;
          window.clearTimeout(longPressTimerRef.current);
          longPressTimerRef.current = window.setTimeout(() => {
            longPressTriggeredRef.current = true;
            showPopover();
          }, LONG_PRESS_MS);
        }}
        onPointerUp={() => {
          window.clearTimeout(longPressTimerRef.current);
        }}
        onPointerCancel={() => {
          window.clearTimeout(longPressTimerRef.current);
        }}
        onClick={(e) => {
          e.stopPropagation();

          if (pointerTypeRef.current === "touch") {
            // Long press already opened the slider — do nothing on the
            // subsequent synthetic click.
            if (longPressTriggeredRef.current) return;

            if (open) {
              // Tap while slider is visible → close it, don't toggle mute.
              setOpen(false);
              return;
            }
            // Tap while slider is hidden → toggle mute.
            onToggleMute();
            return;
          }

          // Desktop (mouse / pen): original behaviour.
          onToggleMute();
        }}
        className={[
          "flex h-12 w-12 items-center justify-center rounded-full border border-white/15 bg-[#2a2a32]/90 text-white/90 transition hover:bg-[#35353f]",
          muted ? "text-white/70" : "",
        ].join(" ")}
      >
        {muted ? <MutedIcon /> : <SpeakerIcon />}
      </button>
    </div>
  );
}
