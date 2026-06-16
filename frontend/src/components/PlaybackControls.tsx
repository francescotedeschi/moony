import type { ReactNode } from "react";
import { VolumeControl } from "./VolumeControl";

type Props = {
  disabled?: boolean;
  isPlaying: boolean;
  hasTrack: boolean;
  volume: number;
  muted: boolean;
  onVolumeChange: (level: number) => void;
  onToggleMute: () => void;
  onPlayPause: () => void;
  onRewind: () => void;
  onSkip: () => void;
};

const iconClass = "h-5 w-5 shrink-0";

function RewindIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 5V2L7 7l5 5V9c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M8 5v14l11-7L8 5z" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M6 5h4v14H6V5zm8 0h4v14h-4V5z" />
    </svg>
  );
}

function SkipIcon() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
    </svg>
  );
}

export function PlaybackControls({
  disabled,
  isPlaying,
  hasTrack,
  volume,
  muted,
  onVolumeChange,
  onToggleMute,
  onPlayPause,
  onRewind,
  onSkip,
}: Props) {
  const inactive = disabled || !hasTrack;

  return (
    <div className="flex items-center justify-center gap-3">
      <ControlButton
        label="Rewind"
        disabled={inactive}
        onClick={onRewind}
        icon={<RewindIcon />}
      />
      <ControlButton
        label={isPlaying ? "Pause" : "Play"}
        disabled={inactive}
        onClick={onPlayPause}
        icon={isPlaying ? <PauseIcon /> : <PlayIcon />}
      />
      <ControlButton
        label="Skip"
        disabled={inactive}
        onClick={onSkip}
        icon={<SkipIcon />}
      />
      <VolumeControl
        volume={volume}
        muted={muted}
        onVolumeChange={onVolumeChange}
        onToggleMute={onToggleMute}
      />
    </div>
  );
}

function ControlButton({
  label,
  icon,
  onClick,
  disabled,
}: {
  label: string;
  icon: ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={[
        "flex h-12 w-12 items-center justify-center rounded-full border border-moony-accent bg-moony-accent text-white transition hover:opacity-90",
        disabled ? "cursor-not-allowed opacity-40" : "",
      ].join(" ")}
    >
      {icon}
    </button>
  );
}
