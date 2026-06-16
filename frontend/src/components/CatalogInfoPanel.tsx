import { useEffect, useState } from "react";
import { moodPieGradient } from "../lib/catalogMoodSlices";
import { setCatalogMoodArcSlices } from "../lib/catalogMoodShares";
import { moodColorForName } from "../lib/emotions";
import { api, type CatalogStats } from "../lib/api";
import { errorMessage, isAbortError } from "../lib/abortError";

const MOOD_DISPLAY: Record<string, string> = {
  calm: "Calm",
  joy: "Joy",
  energy: "Energy",
  tension: "Tension",
  sad: "Sad",
};

const CATALOG_URLS: Record<string, string> = {
  Jamendo: "https://www.jamendo.com/",
};

function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-[18px]">
      <span className="text-white/50">{label}</span>
      <span className="font-medium text-white/85 tabular-nums">{value}</span>
    </div>
  );
}

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

type Props = {
  className?: string;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  embedded?: boolean;
  embeddedDivider?: boolean;
};

export function CatalogInfoPanel({
  className = "",
  collapsed: collapsedProp,
  onCollapsedChange,
  embedded = false,
  embeddedDivider = false,
}: Props) {
  const [collapsedInternal, setCollapsedInternal] = useState(true);
  const collapsed = collapsedProp ?? collapsedInternal;
  const [stats, setStats] = useState<CatalogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void api
      .catalogStats(controller.signal)
      .then((s) => {
        if (!controller.signal.aborted) {
          setStats(s);
          setCatalogMoodArcSlices(s.mood_labels, s.mood_segment_share);
        }
      })
      .catch((e) => {
        if (isAbortError(e)) return;
        setError(errorMessage(e, "Failed to load catalog"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort("catalog-stats");
  }, []);

  const labels = stats?.mood_labels ?? ["calm", "joy", "energy", "tension", "sad"];
  const shares = stats?.mood_segment_share ?? [];
  const counts = stats?.mood_segment_counts ?? [];
  const dominantTracks = stats?.dominant_mood_track_counts ?? [];

  const subtitle = loading
    ? "Loading…"
    : error
      ? "Unavailable"
      : stats
        ? `${stats.track_count.toLocaleString()} tracks · ${stats.segment_count.toLocaleString()} sections`
        : "No data";

  const setCollapsed = (next: boolean | ((prev: boolean) => boolean)) => {
    const value = typeof next === "function" ? next(collapsed) : next;
    if (onCollapsedChange) onCollapsedChange(value);
    else setCollapsedInternal(value);
  };

  const shellClass = embedded
    ? `w-full rounded-none border-0 bg-transparent shadow-none backdrop-blur-none${
        embeddedDivider
          ? " border-t border-white/10 sm:border-t-0 sm:border-l sm:border-white/10"
          : ""
      }`
    : "w-full rounded-xl border border-sky-400/25 bg-black/90 shadow-2xl backdrop-blur-sm";

  return (
    <section
      data-testid="catalog-info-panel"
      className={`${shellClass} ${className}`}
    >
      <header
        className={`flex items-center justify-between gap-2 px-3 py-2 ${
          !collapsed ? "border-b border-white/10" : ""
        }`}
      >
        <button
          type="button"
          className="min-w-0 flex-1 text-left"
          onClick={() => setCollapsed((c) => !c)}
          aria-expanded={!collapsed}
        >
          <p className="text-[18px] font-semibold uppercase tracking-wide text-sky-300">
            Catalog
          </p>
          <p className="truncate text-[15px] text-white/45">{subtitle}</p>
        </button>
        <button
          type="button"
          data-testid="catalog-info-toggle"
          className="shrink-0 rounded px-2 py-1 text-[15px] text-white/50 hover:bg-white/10 hover:text-white/80"
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? "Expand" : "Collapse"}
        </button>
      </header>

      {!collapsed ? (
        <div className="px-3 py-3">
          {loading ? (
            <p className="text-[21px] text-white/40">Loading catalog stats…</p>
          ) : error ? (
            <p className="text-[21px] text-red-400">{error}</p>
          ) : !stats ? (
            <p className="text-[21px] text-white/40">No catalog data.</p>
          ) : (
            <div className="space-y-4">
              {stats.catalog_name ? (
                CATALOG_URLS[stats.catalog_name] ? (
                  <a
                    href={CATALOG_URLS[stats.catalog_name]}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-block text-[20px] font-semibold text-sky-300 underline-offset-2 hover:underline"
                  >
                    {stats.catalog_name}
                  </a>
                ) : (
                  <p className="text-[20px] font-semibold text-white/90">{stats.catalog_name}</p>
                )
              ) : null}
              <div className="grid gap-4 sm:grid-cols-[minmax(0,10.5rem)_1fr]">
                <div className="flex flex-col items-center gap-2">
                  <div
                    className="h-[10.5rem] w-[10.5rem] rounded-full border border-white/10 shadow-inner"
                    style={{ background: moodPieGradient(labels, shares) }}
                    role="img"
                    aria-label="Section mood distribution pie chart"
                  />
                  <p className="text-center text-[15px] text-white/40">Section moods</p>
                </div>

                <ul className="space-y-1">
                  {labels.map((label, i) => (
                    <li key={label} className="flex items-center gap-2 text-[18px]">
                      <span
                        className="h-3 w-3 shrink-0 rounded-full"
                        style={{ backgroundColor: moodColorForName(label) }}
                      />
                      <span className="min-w-[4rem] text-white/75">
                        {MOOD_DISPLAY[label] ?? label}
                      </span>
                      <span className="flex-1 font-mono text-[17px] text-white/55 tabular-nums">
                        {pct(shares[i] ?? 0)}
                      </span>
                      <span className="font-mono text-[15px] text-white/35 tabular-nums">
                        {(counts[i] ?? 0).toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="border-t border-white/10 pt-3 space-y-1.5">
                <p className="text-[15px] uppercase tracking-wide text-white/35">
                  Tracks by dominant mood
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {labels.map((label, i) => (
                    <span
                      key={`dom-${label}`}
                      className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-black/30 px-2.5 py-1 text-[15px] text-white/65"
                    >
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: moodColorForName(label) }}
                      />
                      {MOOD_DISPLAY[label]} {dominantTracks[i] ?? 0}
                    </span>
                  ))}
                </div>
              </div>

              <div className="grid gap-x-4 gap-y-1 border-t border-white/10 pt-3 sm:grid-cols-2">
                <StatRow label="Tracks" value={stats.track_count.toLocaleString()} />
                <StatRow
                  label="Avg sections / track"
                  value={stats.avg_segments_per_track ?? "—"}
                />
                <StatRow
                  label="BPM"
                  value={
                    stats.bpm_range
                      ? `${stats.bpm_range.min}–${stats.bpm_range.max}`
                      : "—"
                  }
                />
              </div>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
