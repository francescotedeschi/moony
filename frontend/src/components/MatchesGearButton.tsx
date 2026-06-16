type Props = {
  active: boolean;
  highlight?: boolean;
  /** First-time discoverability: keep label visible on small screens. */
  emphasizeLabel?: boolean;
  onClick: () => void;
  className?: string;
};

function ChevronPairIcon({ up }: { up: boolean }) {
  return (
    <svg
      className={`moony-matches-chevron h-3.5 w-3.5 shrink-0 opacity-80${up ? " moony-matches-chevron--up" : ""}`}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {up ? (
        <>
          <path d="M4 9.5 8 5.5 12 9.5" />
          <path d="M4 12.5 8 8.5 12 12.5" />
        </>
      ) : (
        <>
          <path d="M4 6.5 8 10.5 12 6.5" />
          <path d="M4 3.5 8 7.5 12 3.5" />
        </>
      )}
    </svg>
  );
}

export function MatchesGearButton({
  active,
  highlight = false,
  emphasizeLabel = false,
  onClick,
  className = "",
}: Props) {
  const label = active ? "Hide Matches" : "Show Matches";
  const labelClass =
    active || emphasizeLabel ? "inline" : "max-sm:sr-only max-sm:w-0 max-sm:overflow-hidden";

  return (
    <button
      type="button"
      data-testid="synced-matches-toggle"
      aria-label={label}
      aria-pressed={active}
      title={label}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-moony-glow ${
        active
          ? "border-moony-glow/35 bg-moony-glow/10 text-white/90 hover:bg-moony-glow/15"
          : highlight
            ? "moony-matches-btn--highlight border-moony-glow/45 bg-moony-glow/12 text-white/90 hover:bg-moony-glow/18"
            : "border-white/10 bg-white/5 text-white/70 hover:border-white/20 hover:bg-white/10 hover:text-white/90"
      } ${emphasizeLabel && !active ? "moony-matches-btn--emphasized" : ""} ${className}`}
    >
      <span className={labelClass}>{label}</span>
      <ChevronPairIcon up={active} />
    </button>
  );
}
