/** Static playlists vs adaptive mood journey — Problem section visual. */

const PLAYLISTS = [
  { color: "#6ec8f0", glow: "#6ec8f066", icon: "cloud" },
  { color: "#5eead4", glow: "#5eead466", icon: "leaf" },
  { color: "#facc15", glow: "#facc1566", icon: "sun" },
  { color: "#fb7185", glow: "#fb718566", icon: "heart" },
  { color: "#c084fc", glow: "#c084fc66", icon: "moon" },
] as const;

function MoodIcon({ type, color }: { type: (typeof PLAYLISTS)[number]["icon"]; color: string }) {
  const props = { fill: "none", stroke: color, strokeWidth: 1.6, strokeLinecap: "round" as const };
  switch (type) {
    case "cloud":
      return (
        <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
          <path {...props} d="M7 16h10a3 3 0 0 0 .2-6 4 4 0 0 0-7.6-1.2A3.2 3.2 0 0 0 7 16z" />
        </svg>
      );
    case "leaf":
      return (
        <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
          <path {...props} d="M12 4C8 8 6 12 6 17c4 0 7-2 10-6-1-5-2-7-4-7z" />
          <path {...props} d="M12 11v6" />
        </svg>
      );
    case "sun":
      return (
        <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
          <circle {...props} cx="12" cy="12" r="3.5" />
          <path {...props} d="M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" />
        </svg>
      );
    case "heart":
      return (
        <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
          <path
            {...props}
            d="M12 20s-6.5-4.2-8.5-7.4C1.8 10 3.6 6.8 6.8 6.8c1.8 0 3 1 3.8 2.1C11.4 7.8 12.6 6.8 14.4 6.8 17.6 6.8 19.4 10 20.5 12.6 18.5 15.8 12 20 12 20z"
          />
        </svg>
      );
    case "moon":
      return (
        <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
          <path {...props} d="M18 14.5A7.5 7.5 0 0 1 9.5 6 6.5 6.5 0 1 0 18 14.5z" />
        </svg>
      );
  }
}

function StaticWaveform({ color }: { color: string }) {
  const bars = [3, 5, 8, 6, 9, 5, 7, 4, 6, 8, 4, 5];
  return (
    <div className="flex h-5 flex-1 items-end justify-center gap-[2px] px-1" aria-hidden>
      {bars.map((h, i) => (
        <span
          key={i}
          className="w-[2px] rounded-full"
          style={{ height: `${h + 4}px`, backgroundColor: `${color}cc` }}
        />
      ))}
    </div>
  );
}

function StaticPlaylists() {
  return (
    <div className="about-problem-static">
      <div className="about-problem-stack">
        {PLAYLISTS.map((item) => (
          <div
            key={item.icon}
            className="about-problem-card"
            style={{
              borderColor: `${item.color}55`,
              background: `linear-gradient(90deg, ${item.glow} 0%, rgb(0 0 0 / 0.35) 100%)`,
              boxShadow: `0 0 18px ${item.glow}`,
            }}
          >
            <span
              className="about-problem-play"
              style={{ borderColor: `${item.color}88`, color: item.color }}
            >
              ▶
            </span>
            <StaticWaveform color={item.color} />
            <MoodIcon type={item.icon} color={item.color} />
          </div>
        ))}
      </div>
      <svg viewBox="0 0 80 28" className="about-problem-footline" aria-hidden>
        <path
          d="M40 2v14"
          stroke="rgb(255 255 255 / 0.22)"
          strokeWidth="1"
          strokeDasharray="2 3"
        />
        <rect x="30" y="16" width="20" height="10" rx="2" fill="none" stroke="rgb(255 255 255 / 0.35)" strokeWidth="1.2" />
        <path d="M36 22h8" stroke="rgb(255 255 255 / 0.35)" strokeWidth="1.2" />
      </svg>
    </div>
  );
}

function SvgMoodIcon({ type, color, x, y }: { type: (typeof PLAYLISTS)[number]["icon"]; color: string; x: number; y: number }) {
  const props = { fill: "none", stroke: color, strokeWidth: 1.4, strokeLinecap: "round" as const };
  const paths: Record<(typeof PLAYLISTS)[number]["icon"], string> = {
    cloud: "M7 16h10a3 3 0 0 0 .2-6 4 4 0 0 0-7.6-1.2A3.2 3.2 0 0 0 7 16z",
    leaf: "M12 4C8 8 6 12 6 17c4 0 7-2 10-6-1-5-2-7-4-7z",
    sun: "M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
    heart: "M12 20s-6.5-4.2-8.5-7.4C1.8 10 3.6 6.8 6.8 6.8c1.8 0 3 1 3.8 2.1C11.4 7.8 12.6 6.8 14.4 6.8 17.6 6.8 19.4 10 20.5 12.6 18.5 15.8 12 20 12 20z",
    moon: "M18 14.5A7.5 7.5 0 0 1 9.5 6 6.5 6.5 0 1 0 18 14.5z",
  };
  return (
    <g transform={`translate(${x - 8}, ${y - 8}) scale(0.66)`}>
      <path {...props} d={paths[type]} />
      {type === "sun" ? <circle {...props} cx="12" cy="12" r="3.5" /> : null}
      {type === "leaf" ? <path {...props} d="M12 11v6" /> : null}
    </g>
  );
}

function AdaptiveJourney() {
  const curve =
    "M12 62 C36 58, 52 48, 68 42 S108 12, 118 18 S148 38, 168 34 S198 48, 218 52 S232 56, 228 58";
  const nodes = [
    { x: 24, y: 58, icon: "cloud" as const, color: "#6ec8f0" },
    { x: 68, y: 42, icon: "leaf" as const, color: "#5eead4" },
    { x: 118, y: 18, icon: "sun" as const, color: "#facc15" },
    { x: 168, y: 34, icon: "heart" as const, color: "#fb7185" },
    { x: 218, y: 52, icon: "moon" as const, color: "#c084fc" },
  ];

  return (
    <div className="about-problem-adaptive">
      <svg viewBox="0 0 240 88" className="about-problem-curve-svg" aria-hidden>
        <defs>
          <linearGradient id="about-problem-curve-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#6ec8f0" />
            <stop offset="25%" stopColor="#5eead4" />
            <stop offset="50%" stopColor="#facc15" />
            <stop offset="75%" stopColor="#fb7185" />
            <stop offset="100%" stopColor="#c084fc" />
          </linearGradient>
          <linearGradient id="about-problem-fill" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#6ec8f028" />
            <stop offset="50%" stopColor="#facc1528" />
            <stop offset="100%" stopColor="#c084fc28" />
          </linearGradient>
          <filter id="about-problem-glow">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path d={`${curve} L228 78 L12 78 Z`} fill="url(#about-problem-fill)" stroke="none" />
        <path
          d={curve}
          fill="none"
          stroke="url(#about-problem-curve-grad)"
          strokeWidth="2.5"
          strokeLinecap="round"
          filter="url(#about-problem-glow)"
        />
        {nodes.map((node) => (
          <g key={node.icon}>
            <circle cx={node.x} cy={node.y} r="5" fill={`${node.color}33`} stroke={node.color} strokeWidth="1.5" />
            <SvgMoodIcon type={node.icon} color={node.color} x={node.x} y={node.y} />
          </g>
        ))}
      </svg>
    </div>
  );
}

export function AboutProblemVisual() {
  return (
    <div className="about-problem-visual" aria-hidden>
      <StaticPlaylists />
      <div className="about-problem-vs">
        <svg viewBox="0 0 120 24" className="about-problem-vs-line" aria-hidden>
          <path d="M0 12h42" stroke="rgb(255 255 255 / 0.18)" strokeWidth="1" strokeDasharray="3 4" />
          <path d="M78 12h42" stroke="rgb(255 255 255 / 0.18)" strokeWidth="1" strokeDasharray="3 4" />
        </svg>
        <span className="about-problem-vs-badge">vs.</span>
      </div>
      <AdaptiveJourney />
    </div>
  );
}
