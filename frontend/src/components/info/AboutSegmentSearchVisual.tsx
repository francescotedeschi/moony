/** Branching segment search flow — Segment-Level Emotional Search visual. */

type CapsuleSpec = { x: number; y: number; color: string; bars: number[] };

const CAPSULE_W = 22;
const CAPSULE_H = 10;
const BAR_COUNT = 5;
const BAR_W = 1.75;
const BAR_GAP = 1.35;
const BAR_RX = 0.65;
const INNER_PAD_Y = 1.5;
const MIN_BAR_H = 1.4;

function barHeights(bars: number[]): number[] {
  const max = Math.max(...bars, 1);
  const innerH = CAPSULE_H - INNER_PAD_Y * 2;
  const maxH = innerH - 0.25;
  return bars.map((value) => MIN_BAR_H + (value / max) * (maxH - MIN_BAR_H));
}

function drawCapsule(spec: CapsuleSpec, key: string) {
  const { x, y, color, bars } = spec;
  const heights = barHeights(bars.slice(0, BAR_COUNT));
  const totalBarsW = heights.length * BAR_W + (heights.length - 1) * BAR_GAP;
  const startX = x + (CAPSULE_W - totalBarsW) / 2;

  return (
    <g key={key} className="about-segment-capsule">
      <rect
        x={x}
        y={y - CAPSULE_H / 2}
        width={CAPSULE_W}
        height={CAPSULE_H}
        rx={5}
        fill={`${color}14`}
        stroke={`${color}70`}
        strokeWidth="1"
        style={{ filter: `drop-shadow(0 0 4px ${color}44)` }}
      />
      {heights.map((barH, i) => (
        <rect
          key={i}
          x={startX + i * (BAR_W + BAR_GAP)}
          y={y - barH / 2}
          width={BAR_W}
          height={barH}
          rx={BAR_RX}
          fill={`${color}cc`}
        />
      ))}
    </g>
  );
}

function BranchCapsules({ y, colors, active }: { y: number; colors: string[]; active: boolean }) {
  const startX = 118;
  const gap = 26;
  const barsSets = [
    [2, 4, 3, 5, 2],
    [3, 2, 5, 3, 4],
    [2, 5, 3, 4, 3],
  ];
  return (
    <>
      {colors.map((color, i) =>
        drawCapsule({ x: startX + i * gap, y, color, bars: barsSets[i] }, `branch-${y}-${i}`),
      )}
      {active ? (
        <g>
          <circle
            cx={210}
            cy={y}
            r="9"
            fill="#facc1522"
            stroke="#facc15"
            strokeWidth="1.5"
            style={{ filter: "drop-shadow(0 0 6px #facc1566)" }}
          />
          <circle cx={210} cy={y} r="6.5" fill="none" stroke="#facc1588" strokeWidth="0.8" />
          <path
            d={`M206 ${y + 1} l3 3 6-6`}
            fill="none"
            stroke="#facc15"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>
      ) : (
        <circle cx={210} cy={y} r="7" fill="none" stroke="rgb(255 255 255 / 0.22)" strokeWidth="1" strokeDasharray="2 3" />
      )}
    </>
  );
}

export function AboutSegmentSearchVisual() {
  const mainPath: CapsuleSpec[] = [
    { x: 26, y: 48, color: "#6ec8f0", bars: [2, 3, 5, 3, 4] },
    { x: 54, y: 48, color: "#5eead4", bars: [3, 4, 3, 5, 3] },
    { x: 82, y: 48, color: "#facc15", bars: [3, 5, 4, 6, 4] },
  ];

  const branchYs = [22, 48, 74];
  const branchColors = [
    ["#fb923c", "#fb7185", "#c084fc"],
    ["#78716c", "#fb7185", "#c084fc"],
    ["#5eead4", "#9ca3af", "#c084fc"],
  ];

  return (
    <div className="about-segment-search-visual" aria-hidden>
      <svg viewBox="0 0 230 88" className="about-segment-search-svg">
        <path
          d="M0 72 C30 66, 60 78, 90 70 S150 64, 230 70"
          fill="none"
          stroke="rgb(255 255 255 / 0.04)"
          strokeWidth="10"
          strokeLinecap="round"
        />

        <circle
          cx="14"
          cy="48"
          r="7"
          fill="#6ec8f022"
          stroke="#6ec8f0"
          strokeWidth="1.2"
          style={{ filter: "drop-shadow(0 0 5px #6ec8f066)" }}
        />
        <path d="M11.5 45.5 L11.5 50.5 L16 48 Z" fill="#6ec8f0" />

        <line x1="21" y1="48" x2="26" y2="48" stroke="rgb(255 255 255 / 0.25)" strokeWidth="1" />
        {mainPath.map((cap, i) => {
          const nextX = i < mainPath.length - 1 ? mainPath[i + 1].x : 104;
          return (
            <g key={`main-${i}`}>
              {drawCapsule(cap, `main-${i}`)}
              <line
                x1={cap.x + CAPSULE_W}
                y1={cap.y}
                x2={nextX}
                y2={cap.y}
                stroke="rgb(255 255 255 / 0.25)"
                strokeWidth="1"
              />
            </g>
          );
        })}

        {branchYs.map((y, i) => {
          const isActive = i === 0;
          const pivotX = 104;
          const branchStartX = 115;
          return (
            <g key={`branch-line-${y}`}>
              <path
                d={`M${pivotX} 48 C${pivotX + 6} 48, ${branchStartX - 4} ${y}, ${branchStartX} ${y}`}
                fill="none"
                stroke={isActive ? "#fb923caa" : "rgb(255 255 255 / 0.18)"}
                strokeWidth={isActive ? 1.5 : 1}
                strokeDasharray={isActive ? undefined : "2 3"}
              />
              <circle
                cx={branchStartX}
                cy={y}
                r="2"
                fill={isActive ? "#fb923c" : "rgb(255 255 255 / 0.25)"}
              />
              <line
                x1={192}
                y1={y}
                x2={201}
                y2={y}
                stroke={isActive ? "#facc1588" : "rgb(255 255 255 / 0.18)"}
                strokeWidth="1"
                strokeDasharray={isActive ? undefined : "2 3"}
              />
              <BranchCapsules y={y} colors={branchColors[i]} active={isActive} />
            </g>
          );
        })}
      </svg>
    </div>
  );
}
