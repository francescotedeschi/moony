import { useMemo, useState, type MouseEvent, type ReactNode } from "react";
import { EMOTION_ZONES } from "../lib/emotions";
import { MotionCurveOverlay } from "./MotionCurveOverlay";
import {
  formatMs,
  segmentAtTime,
  segmentDescriptionLines,
  segmentHasInspectData,
  segmentIndexAtTime,
  segmentMoodColor,
  segmentMoodLabel,
  syncedSegmentIndexByMotion,
  type MatchTimelineRow,
  type TimelineView,
} from "../lib/segments";
import type { MossSegment, TrackTimeline } from "../lib/api";

type Props = {
  view: TimelineView | null;
  currentMs: number;
  /** True only before the first prefetch rows exist (not background enrich). */
  matchesLoading?: boolean;
  showSyncedMatches?: boolean;
  /** When true, render only the synced matches block (for layout below the toggle). */
  matchesOnly?: boolean;
  onSelectMatch?: (trackId: string, entryMs: number) => void;
  onSelectCurrentSegment?: (segmentIndex: number) => void;
  /** Status note beside the target-mood zone row (e.g. deep prefetch after 30s). */
  targetZonePrefetchNote?: { zone: string; text: string } | null;
  /** Rendered on the segment tags row (e.g. Show Matches toggle). */
  matchesToggle?: ReactNode;
};

function SegmentRow({
  label,
  sublabel,
  timeline,
  durationMs,
  playheadMs,
  highlightIndex,
  entryMs,
  accentClass,
  moodHint,
  emphasizeSyncedSegment,
  onClick,
  onSegmentClick,
  labelNote,
  showSegmentInspect = false,
  variant = "card",
}: {
  label: string;
  labelNote?: string;
  sublabel?: string;
  timeline: TrackTimeline;
  durationMs: number;
  playheadMs?: number;
  highlightIndex?: number;
  entryMs?: number;
  accentClass?: string;
  /** Row mood name (Calm, Joy, …) for solid segment colors on match rows. */
  moodHint?: string;
  /** Match rows: dim non-synced segments, highlight the next synced segment. */
  emphasizeSyncedSegment?: boolean;
  onClick?: () => void;
  onSegmentClick?: (segmentIndex: number) => void;
  showSegmentInspect?: boolean;
  /** Minimal: track bar only (no row chrome or header). */
  variant?: "card" | "minimal";
}) {
  const isMinimal = variant === "minimal";
  const segmentCount = timeline.segments.length;
  const [hoveredSegIdx, setHoveredSegIdx] = useState<number | null>(null);
  const activeSeg =
    playheadMs !== undefined ? segmentAtTime(timeline.segments, playheadMs) : null;
  const effectiveDurationMs =
    durationMs > 0
      ? durationMs
      : timeline.segments.reduce((max, s) => Math.max(max, s.t_end), 0);

  const Wrapper = onClick ? "button" : "div";

  return (
    <Wrapper
      type={onClick ? "button" : undefined}
      disabled={onClick ? false : undefined}
      onClick={onClick}
      className={`timeline-row ${isMinimal ? "timeline-row--minimal" : ""} ${onClick ? "cursor-pointer" : ""}`}
    >
      {!isMinimal ? (
        <div className="mb-0 flex items-baseline justify-between gap-2">
          <div className="min-w-0">
            <p className="timeline-row-label truncate">
              {label}
              {labelNote ? (
                <span className="ml-2 font-normal italic text-white/45">{labelNote}</span>
              ) : null}
            </p>
            {sublabel ? <p className="timeline-row-sublabel truncate">{sublabel}</p> : null}
          </div>
          {activeSeg ? (
            <span className="timeline-row-badge">{activeSeg.label}</span>
          ) : highlightIndex !== undefined ? (
            <span className="timeline-row-badge text-white/50">
              {timeline.segments[highlightIndex]?.label ?? "—"}
            </span>
          ) : null}
        </div>
      ) : null}
      <div
        className={`timeline-track-shell ${isMinimal ? "timeline-track-shell--minimal" : ""}`}
        onMouseLeave={() => setHoveredSegIdx(null)}
      >
        {showSegmentInspect && hoveredSegIdx !== null ? (
          <SegmentInspectOverlay
            seg={timeline.segments[hoveredSegIdx]!}
            durationMs={effectiveDurationMs}
            segmentIndex={hoveredSegIdx}
          />
        ) : null}
        <div className="timeline-track-inner">
        {timeline.segments.map((seg, idx) => (
          <SegmentBlock
            key={`${seg.t_start}-${seg.t_end}-${idx}`}
            seg={seg}
            durationMs={effectiveDurationMs}
            moodHint={moodHint}
            active={playheadMs !== undefined && playheadMs >= seg.t_start && playheadMs < seg.t_end}
            synced={highlightIndex === idx}
            entry={entryMs !== undefined && entryMs >= seg.t_start && entryMs < seg.t_end}
            emphasizeSynced={emphasizeSyncedSegment}
            flush
            isFirst={idx === 0}
            isLast={idx === segmentCount - 1}
            clickable={onSegmentClick != null}
            inspectable={showSegmentInspect && segmentHasInspectData(seg)}
            onInspectEnter={
              showSegmentInspect && segmentHasInspectData(seg)
                ? () => setHoveredSegIdx(idx)
                : undefined
            }
            onClick={
              onSegmentClick
                ? (e) => {
                    e.stopPropagation();
                    onSegmentClick(idx);
                  }
                : undefined
            }
          />
        ))}
        </div>
        <MotionCurveOverlay
          points={timeline.motion_preview}
          durationMs={effectiveDurationMs}
        />
        {playheadMs !== undefined && effectiveDurationMs > 0 ? (
          <div
            className="timeline-playhead"
            style={{ left: `${Math.min(100, (playheadMs / effectiveDurationMs) * 100)}%` }}
          />
        ) : null}
        {entryMs !== undefined && effectiveDurationMs > 0 ? (
          <div
            className={`timeline-entry-marker ${accentClass ?? "bg-moony-glow"}`}
            style={{ left: `${Math.min(100, (entryMs / effectiveDurationMs) * 100)}%` }}
            title="Synced segment entry"
          />
        ) : null}
      </div>
    </Wrapper>
  );
}

function SegmentInspectOverlay({
  seg,
  durationMs,
  segmentIndex,
}: {
  seg: MossSegment;
  durationMs: number;
  segmentIndex: number;
}) {
  if (durationMs <= 0) return null;
  const left = (seg.t_start / durationMs) * 100;
  const width = Math.max(0.4, ((seg.t_end - seg.t_start) / durationMs) * 100);
  const center = left + width / 2;

  return (
    <div
      className="pointer-events-none absolute bottom-full z-40 mb-1.5 flex justify-center"
      style={{ left: `${center}%`, transform: "translateX(-50%)" }}
      role="tooltip"
      data-testid={`segment-inspect-${segmentIndex}`}
    >
      <div className="w-[min(24rem,calc(100vw-2.5rem))] rounded-lg border border-white/15 bg-black/92 px-3.5 py-3 shadow-2xl backdrop-blur-sm">
        <p className="mb-1.5 text-[12px] font-medium uppercase tracking-wide text-white/40">
          {seg.label} · {formatMs(seg.t_start)}–{formatMs(seg.t_end)}
        </p>
        <div className="space-y-1 text-[13px] leading-snug text-white/75">
          {seg.description?.trim() ? (
            segmentDescriptionLines(seg.description).map((line, i) => (
              <p
                key={`${segmentIndex}-${i}`}
                className={line.bold ? "font-semibold text-white/90" : undefined}
              >
                {line.text}
              </p>
            ))
          ) : (
            <p>No MOSS description.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function SegmentBlock({
  seg,
  durationMs,
  moodHint,
  active,
  synced,
  entry,
  emphasizeSynced,
  flush,
  isFirst,
  isLast,
  clickable,
  inspectable,
  onInspectEnter,
  onClick,
}: {
  seg: MossSegment;
  durationMs: number;
  moodHint?: string;
  active?: boolean;
  synced?: boolean;
  entry?: boolean;
  emphasizeSynced?: boolean;
  flush?: boolean;
  isFirst?: boolean;
  isLast?: boolean;
  clickable?: boolean;
  inspectable?: boolean;
  onInspectEnter?: () => void;
  onClick?: (e: MouseEvent) => void;
}) {
  if (durationMs <= 0) return null;
  const left = (seg.t_start / durationMs) * 100;
  const rawWidth = ((seg.t_end - seg.t_start) / durationMs) * 100;
  const minWidth = clickable ? 1.25 : 0.4;
  const width = isLast ? Math.max(minWidth, 100 - left) : Math.max(minWidth, rawWidth);
  const color = segmentMoodColor(seg, moodHint);
  const opacity = active
    ? 1
    : emphasizeSynced
      ? synced
        ? 1
        : 0.32
      : synced || entry
        ? 0.9
        : 0.78;
  const edgeClass =
    isFirst && isLast
      ? "timeline-segment--edge-both"
      : isFirst
        ? "timeline-segment--edge-start"
        : isLast
          ? "timeline-segment--edge-end"
          : "";
  const className = [
    "timeline-segment",
    flush ? "timeline-segment--flush" : "",
    edgeClass,
    active ? "timeline-segment--active" : "",
    synced ? "timeline-segment--synced" : "",
    clickable || inspectable ? "timeline-segment--clickable" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const hoverHandlers = inspectable
    ? { onMouseEnter: onInspectEnter, onFocus: onInspectEnter }
    : {};
  const style = {
    left: `${left}%`,
    width: `${width}%`,
    backgroundColor: color,
    opacity,
  };
  const title = `${seg.label} (${formatMs(seg.t_start)}–${formatMs(seg.t_end)})`;

  if (clickable && onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={className}
        style={style}
        title={title}
        aria-label={`Play from ${seg.label}`}
        {...hoverHandlers}
      />
    );
  }

  return <div className={className} style={style} title={title} {...hoverHandlers} />;
}

function MatchRow({
  row,
  highlightIndex,
  onSelect,
  labelNote,
}: {
  row: MatchTimelineRow;
  highlightIndex: number;
  onSelect?: (trackId: string, entryMs: number) => void;
  labelNote?: string;
}) {
  const zone = EMOTION_ZONES.find((z) => z.name === row.emotion);
  const syncSeg = row.segments[highlightIndex];
  const syncStartMs = syncSeg?.t_start ?? row.entryMs;

  return (
    <SegmentRow
      label={row.emotion}
      labelNote={labelNote}
      sublabel={`${row.title} · ${row.artist}`}
      timeline={row}
      durationMs={row.duration_ms}
      highlightIndex={highlightIndex}
      entryMs={syncStartMs}
      accentClass={zone?.dotClass}
      emphasizeSyncedSegment
      moodHint={row.emotion}
      onClick={onSelect ? () => onSelect(row.track_id, syncStartMs) : undefined}
    />
  );
}

export function SegmentTimelinePlayer({
  view,
  currentMs,
  matchesLoading,
  showSyncedMatches = false,
  matchesOnly = false,
  onSelectMatch,
  onSelectCurrentSegment,
  targetZonePrefetchNote,
  matchesToggle,
}: Props) {
  const sourceSegIdx = view
    ? segmentIndexAtTime(view.current.segments, currentMs)
    : 0;

  const matchHighlightIndices = useMemo(() => {
    if (!view) return [];
    return view.matches.map((row) =>
      syncedSegmentIndexByMotion(view.current, sourceSegIdx, row, row.entryMs),
    );
  }, [view, sourceSegIdx]);

  if (!view) {
    return null;
  }

  const currentSeg = segmentAtTime(view.current.segments, currentMs);

  const matchesBlock = showSyncedMatches ? (
    <div className="space-y-2" data-testid="synced-matches">
      <p className="timeline-matches-heading">Synced matches</p>
      {matchesLoading && view.matches.length === 0 ? (
        <p className="text-sm text-white/35">Loading matches…</p>
      ) : view.matches.length > 0 ? (
        view.matches.map((row, i) => (
          <MatchRow
            key={`${row.emotion}-${row.track_id}`}
            row={row}
            highlightIndex={matchHighlightIndices[i] ?? 0}
            onSelect={onSelectMatch}
            labelNote={
              targetZonePrefetchNote?.zone === row.emotion
                ? targetZonePrefetchNote.text
                : undefined
            }
          />
        ))
      ) : (
        <p className="text-sm text-white/35">No prefetched matches.</p>
      )}
    </div>
  ) : null;

  if (matchesOnly) {
    return matchesBlock;
  }

  return (
    <div className="timeline-player timeline-player--minimal">
      <SegmentRow
        variant="minimal"
        label=""
        timeline={view.current}
        durationMs={view.current.duration_ms}
        playheadMs={currentMs}
        onSegmentClick={onSelectCurrentSegment}
        showSegmentInspect
      />

      {currentSeg || matchesToggle ? (
        <div className="timeline-active-meta">
          {currentSeg ? (
            <div className="timeline-active-meta__chips">
              <span className="timeline-meta-chip">{currentSeg.label}</span>
              <span
                className="timeline-meta-chip timeline-meta-chip--mood"
                style={{
                  color: segmentMoodColor(currentSeg),
                  borderColor: `${segmentMoodColor(currentSeg)}44`,
                }}
              >
                {segmentMoodLabel(currentSeg)}
              </span>
              <span className="timeline-meta-chip timeline-meta-chip--time">
                {formatMs(currentSeg.t_start)}–{formatMs(currentSeg.t_end)}
              </span>
            </div>
          ) : null}
          {matchesToggle ? (
            <div className="timeline-active-meta__toggle">{matchesToggle}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
