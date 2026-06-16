import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { moodColorForName } from "../lib/emotions";
import {
  moodMonitor,
  type MoodMonitorEvent,
  type MoodTrackEntry,
  type MoodUserAction,
} from "../lib/moodMonitor";

const MARKER_KINDS = new Set<MoodUserAction>([
  "session_start",
  "mood_change",
  "same_mood_change",
  "skip",
  "replay",
  "timeline",
  "next_track",
]);

const TIMELINE_VIEWPORT_H = 224;
const BASE_PX_PER_SEC = 2;
const MIN_PX_PER_SEC = 0.2;
const MAX_PX_PER_SEC = 10;
const ZOOM_FACTOR = 1.3;
/** After wheel/trackpad scroll, wait before snapping back to playhead. */
const SCROLL_SETTLE_MS = 5000;
/** Max tracks shown at once in the session list. */
const MAX_VISIBLE_TRACKS = 3;
/** Crossfade when the visible window shifts (scroll back or new track). */
const TRACK_LIST_FADE_MS = 2500;
/** Min vertical gap between event rows so labels do not overlap. */
const MARKER_ROW_MIN_PX = 24;

function fitPxPerSec(markers: MoodMonitorEvent[]): number {
  if (markers.length < 2) return BASE_PX_PER_SEC;

  const sorted = [...markers].sort((a, b) => a.at - b.at);
  let required = BASE_PX_PER_SEC;

  for (let i = 1; i < sorted.length; i++) {
    const deltaMs = sorted[i].at - sorted[i - 1].at;
    if (deltaMs <= 0) {
      required = MAX_PX_PER_SEC;
      continue;
    }
    required = Math.max(required, (MARKER_ROW_MIN_PX * 1000) / deltaMs);
  }

  return Math.min(MAX_PX_PER_SEC, Math.max(MIN_PX_PER_SEC, required));
}

function compactMarkerIds(
  markers: MoodMonitorEvent[],
  pxPerSec: number,
): Set<number> {
  const sorted = [...markers].sort((a, b) => a.at - b.at);
  const compact = new Set<number>();
  for (let i = 1; i < sorted.length; i++) {
    if (msToPx(sorted[i].at - sorted[i - 1].at, pxPerSec) < MARKER_ROW_MIN_PX) {
      compact.add(sorted[i].id);
      compact.add(sorted[i - 1].id);
    }
  }
  return compact;
}

type MarkerStyle = {
  label: string;
  color: string;
  ring: string;
};

function markerStyle(kind: MoodUserAction, ev: MoodMonitorEvent): MarkerStyle {
  switch (kind) {
    case "skip":
      return { label: "Skip", color: "#fb923c", ring: "ring-orange-400/60" };
    case "replay":
      return { label: "Replay", color: "#7dd3fc", ring: "ring-sky-300/60" };
    case "mood_change":
      return {
        label: ev.fromMood && ev.toMood ? `${ev.fromMood} → ${ev.toMood}` : "Mood change",
        color: moodColorForName(ev.toMood ?? ev.mood),
        ring: "ring-white/50",
      };
    case "same_mood_change":
      return {
        label: "Same mood",
        color: moodColorForName(ev.mood),
        ring: "ring-white/25",
      };
    case "timeline":
      return { label: "Timeline", color: "#c4b5fd", ring: "ring-violet-300/50" };
    case "next_track":
      return { label: "Next track", color: "#5eead4", ring: "ring-teal-300/50" };
    case "session_start":
      return { label: "Start", color: "#6ee7b7", ring: "ring-emerald-300/50" };
    default:
      return { label: kind, color: "#ffffff", ring: "ring-white/30" };
  }
}

function fmtOffset(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  if (sec >= 3600) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function msToPx(ms: number, pxPerSec: number): number {
  return (ms / 1000) * pxPerSec;
}

/** Min inner width so event labels stay on one line (column scrolls horizontally if needed). */
function timelineContentMinWidthRem(markers: MoodMonitorEvent[], elapsedMs: number): number {
  let labelChars = 10;
  for (const ev of markers) {
    labelChars = Math.max(labelChars, markerStyle(ev.kind, ev).label.length);
  }
  const timeChars = elapsedMs >= 3_600_000 ? 7 : 5;
  return timeChars * 0.52 + 3.5 + labelChars * 0.52 + 0.75;
}

function sessionMsAtContentY(contentHeight: number, y: number, pxPerSec: number): number {
  return Math.max(0, ((contentHeight - y) / pxPerSec) * 1000);
}

type TrackListItem = {
  key: string;
  track: MoodTrackEntry;
  opacity: number;
};

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, n));
}

function trackEntryKey(track: MoodTrackEntry): string {
  return `${track.trackId}-${track.fromMs}`;
}

function trackActiveAtView(
  history: readonly MoodTrackEntry[],
  viewMs: number,
  elapsedMs: number,
): MoodTrackEntry | null {
  if (!history.length) return null;
  for (let i = history.length - 1; i >= 0; i--) {
    const track = history[i];
    const end = track.toMs ?? elapsedMs;
    if (viewMs >= track.fromMs && viewMs <= end) return track;
  }
  if (viewMs < history[0].fromMs) return history[0];
  return history[history.length - 1];
}

/** Session tracks up to live elapsed time; newest on top. */
function computeTrackListItems(
  history: readonly MoodTrackEntry[],
  elapsedMs: number,
): TrackListItem[] {
  if (!history.length) return [];

  const eligible = history.filter(
    (t) => t.fromMs <= elapsedMs || t.toMs === null,
  );
  const coreKeys = new Set(
    eligible.slice(-MAX_VISIBLE_TRACKS).map((t) => `${t.trackId}-${t.fromMs}`),
  );
  const rows: TrackListItem[] = [];

  for (const track of history) {
    if (track.fromMs <= elapsedMs) continue;
    if (elapsedMs < track.fromMs - TRACK_LIST_FADE_MS) continue;
    const opacity = clamp01((track.fromMs - elapsedMs) / TRACK_LIST_FADE_MS);
    if (opacity <= 0.03) continue;
    rows.push({
      key: `${track.trackId}-${track.fromMs}-fadeout`,
      track,
      opacity,
    });
  }

  for (const track of [...eligible].reverse()) {
    const key = `${track.trackId}-${track.fromMs}`;
    rows.push({
      key,
      track,
      opacity: coreKeys.has(key) ? 1 : 0.45,
    });
  }

  return rows;
}

function TrackListRow({
  track,
  opacity,
  highlighted,
  onReplay,
}: {
  track: MoodTrackEntry;
  opacity: number;
  highlighted: boolean;
  onReplay?: (track: MoodTrackEntry) => void;
}) {
  const plays =
    track.playCount != null ? (
      <span className="tabular-nums">{track.playCount}</span>
    ) : (
      <span className="text-white/30">—</span>
    );

  return (
    <li
      data-track-key={trackEntryKey(track)}
      className={`shrink-0 rounded-md border px-2 py-1 transition-[opacity,background-color,border-color,box-shadow] duration-200 ${
        highlighted
          ? "border-rose-400/55 bg-rose-400/10 shadow-[inset_0_0_0_1px_rgba(251,113,133,0.2)]"
          : "border-white/10 bg-black/45"
      }`}
      style={{ opacity }}
    >
      {onReplay ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onReplay(track);
          }}
          className={`block w-full truncate text-left text-[15px] leading-tight transition hover:text-white ${
            highlighted ? "font-semibold text-white" : "font-medium text-white/90"
          }`}
          title={`Replay ${track.title}`}
        >
          {track.title}
        </button>
      ) : (
        <p
          className={`truncate text-[15px] leading-tight ${
            highlighted ? "font-semibold text-white" : "font-medium text-white/90"
          }`}
        >
          {track.title}
        </p>
      )}
      <p className="truncate text-[15px] leading-tight text-white/45">{track.artist}</p>
      <p className="mt-0.5 flex items-center gap-1.5 text-[15px] leading-tight text-white/40">
        <span
          className="inline-block h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: moodColorForName(track.primaryMood) }}
        />
        <span className="truncate">{track.primaryMood}</span>
        <span className="text-white/25">·</span>
        <span className="shrink-0">{plays} plays</span>
      </p>
    </li>
  );
}

function TrackHistoryList({
  history,
  elapsedMs,
  viewLocked,
  activeTrackKey,
  listResetSeq,
  onListPointerDown,
  onListScroll,
  onReplayTrack,
}: {
  history: readonly MoodTrackEntry[];
  elapsedMs: number;
  viewLocked: boolean;
  activeTrackKey: string | null;
  listResetSeq: number;
  onListPointerDown: () => void;
  onListScroll: () => void;
  onReplayTrack?: (track: MoodTrackEntry) => void;
}) {
  const listRef = useRef<HTMLUListElement>(null);
  const suppressScrollRef = useRef(false);
  const items = computeTrackListItems(history, elapsedMs);

  useLayoutEffect(() => {
    if (viewLocked || !listRef.current) return;
    suppressScrollRef.current = true;
    listRef.current.scrollTop = 0;
    requestAnimationFrame(() => {
      suppressScrollRef.current = false;
    });
  }, [viewLocked, listResetSeq, items.length, items[0]?.key]);

  useLayoutEffect(() => {
    if (!viewLocked || !activeTrackKey || !listRef.current) return;
    const row = listRef.current.querySelector<HTMLElement>(
      `[data-track-key="${activeTrackKey}"]`,
    );
    row?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [viewLocked, activeTrackKey, elapsedMs]);

  const handleListScroll = () => {
    if (suppressScrollRef.current) return;
    onListScroll();
  };

  return (
    <div
      className="flex min-h-0 min-w-0 flex-col border-l border-white/10 pl-2"
      style={{ height: TIMELINE_VIEWPORT_H }}
    >
      {history.length === 0 ? (
        <p className="text-[15px] leading-snug text-white/30">No tracks yet</p>
      ) : (
        <ul
          ref={listRef}
          className="moony-mood-timeline-scroll flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overscroll-contain pr-0.5"
          onPointerDown={onListPointerDown}
          onScroll={handleListScroll}
        >
          {items.map((item) => (
            <TrackListRow
              key={item.key}
              track={item.track}
              opacity={item.opacity}
              highlighted={activeTrackKey === trackEntryKey(item.track)}
              onReplay={onReplayTrack}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function MarkerDot({ kind, ev }: { kind: MoodUserAction; ev: MoodMonitorEvent }) {
  const style = markerStyle(kind, ev);
  const hollow = kind === "same_mood_change";

  return (
    <span
      className={`block h-3.5 w-3.5 shrink-0 rounded-full ring-2 ${style.ring}`}
      style={
        hollow
          ? {
              backgroundColor: "rgba(0,0,0,0.85)",
              boxShadow: `inset 0 0 0 2px ${style.color}`,
            }
          : { backgroundColor: style.color }
      }
      aria-hidden
    />
  );
}

function pct(n: number): string {
  return `${(n * 100).toFixed(0)}%`;
}

function SessionStats() {
  const { moodShare, tracksPlayed, skipCount } = moodMonitor.getSessionStats();

  return (
    <div className="flex w-max max-w-full flex-col" style={{ height: TIMELINE_VIEWPORT_H }}>
      <div className="space-y-1 border-b border-white/10 pb-2">
        <div className="flex items-baseline gap-3 text-[15px] whitespace-nowrap">
          <span className="text-white/45">Tracks</span>
          <span className="font-medium tabular-nums text-white/85">{tracksPlayed}</span>
        </div>
        <div className="flex items-baseline gap-3 text-[15px] whitespace-nowrap">
          <span className="text-white/45">Skips</span>
          <span className="font-medium tabular-nums text-orange-300">{skipCount}</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-1 overflow-hidden pt-2">
        {moodShare.map(({ zone, share }) => (
          <div
            key={zone}
            className="flex items-center gap-1.5 text-[15px] leading-none whitespace-nowrap"
          >
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: moodColorForName(zone) }}
            />
            <span className="text-white/65">{zone}</span>
            <span className="font-mono tabular-nums text-white/45">{pct(share)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const zoomIconClass = "h-[15px] w-[15px] shrink-0";

function ZoomInIcon() {
  return (
    <svg className={zoomIconClass} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.75" />
      <path
        d="m20 20-3.5-3.5"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <path
        d="M11 8v6M8 11h6"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ZoomOutIcon() {
  return (
    <svg className={zoomIconClass} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.75" />
      <path
        d="m20 20-3.5-3.5"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <path
        d="M8 11h6"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ZoomButton({
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
      disabled={disabled}
      onClick={onClick}
      className="flex h-7 w-7 items-center justify-center rounded text-white/55 hover:bg-white/10 hover:text-white/85 disabled:cursor-not-allowed disabled:opacity-35"
    >
      {icon}
    </button>
  );
}

type TimelineProps = {
  elapsedMs: number;
  markers: MoodMonitorEvent[];
  trackHistory: readonly MoodTrackEntry[];
  onReplayTrack?: (track: MoodTrackEntry) => void;
};

/** Pin playhead (top of elapsed band = “now”) to the top of the viewport. */
function scrollToPlayhead(
  el: HTMLDivElement,
  elapsedPx: number,
  contentHeight: number,
) {
  const playheadTop = contentHeight - elapsedPx;
  const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
  el.scrollTop = Math.min(Math.max(0, playheadTop), maxScroll);
}

function MoodTimeline({
  elapsedMs,
  markers,
  trackHistory,
  onReplayTrack,
}: TimelineProps) {
  const trail = moodMonitor.getMoodTrail();
  const scrollRef = useRef<HTMLDivElement>(null);
  const userZoomRef = useRef(false);
  const userScrollLockRef = useRef(false);
  const pointerOnScrollerRef = useRef(false);
  const programmaticScrollRef = useRef(false);
  const scrollSettleTimerRef = useRef<number | undefined>(undefined);
  const scrollMetricsRef = useRef({ elapsedPx: 24, contentHeight: TIMELINE_VIEWPORT_H });
  const [pxPerSec, setPxPerSec] = useState(() => fitPxPerSec(markers));
  const [viewMs, setViewMs] = useState(elapsedMs);
  const [viewLocked, setViewLocked] = useState(false);
  const [listResetSeq, setListResetSeq] = useState(0);
  const prevHistoryLenRef = useRef(trackHistory.length);

  const elapsedPx = Math.max(msToPx(elapsedMs, pxPerSec), 24);
  const contentHeight = Math.max(TIMELINE_VIEWPORT_H, elapsedPx + 12);
  scrollMetricsRef.current = { elapsedPx, contentHeight };

  const markerFitKey = markers.map((m) => `${m.id}:${m.at}`).join("|");
  const compactIds = useMemo(
    () => compactMarkerIds(markers, pxPerSec),
    [markerFitKey, pxPerSec],
  );
  const timelineContentMinW = useMemo(
    () => `${timelineContentMinWidthRem(markers, elapsedMs).toFixed(2)}rem`,
    [markerFitKey, elapsedMs],
  );
  const syncViewMsFromScroll = (el: HTMLDivElement) => {
    const { contentHeight: h } = scrollMetricsRef.current;
    const topMs = sessionMsAtContentY(h, el.scrollTop, pxPerSec);
    setViewMs(Math.max(0, Math.min(elapsedMs, topMs)));
  };

  const lockView = useCallback(() => {
    userScrollLockRef.current = true;
    setViewLocked(true);
  }, []);

  const applyPlayheadScroll = useCallback((el: HTMLDivElement) => {
    const { elapsedPx: px, contentHeight: h } = scrollMetricsRef.current;
    programmaticScrollRef.current = true;
    scrollToPlayhead(el, px, h);
    setViewMs(elapsedMs);
    requestAnimationFrame(() => {
      programmaticScrollRef.current = false;
    });
  }, [elapsedMs]);

  const resumeLiveView = useCallback(() => {
    userScrollLockRef.current = false;
    setViewLocked(false);
    setListResetSeq((n) => n + 1);
    const el = scrollRef.current;
    if (el) applyPlayheadScroll(el);
    else setViewMs(elapsedMs);
  }, [applyPlayheadScroll, elapsedMs]);

  const scheduleResumeLive = useCallback(() => {
    window.clearTimeout(scrollSettleTimerRef.current);
    scrollSettleTimerRef.current = window.setTimeout(() => {
      resumeLiveView();
    }, SCROLL_SETTLE_MS);
  }, [resumeLiveView]);

  const onTrackListPointerDown = useCallback(() => {
    lockView();
    window.clearTimeout(scrollSettleTimerRef.current);
  }, [lockView]);

  const onTrackListScroll = useCallback(() => {
    lockView();
    scheduleResumeLive();
  }, [lockView, scheduleResumeLive]);

  useEffect(() => {
    if (markers.length === 1 && markers[0]?.kind === "session_start") {
      userZoomRef.current = false;
    }
    if (userZoomRef.current) return;
    setPxPerSec(fitPxPerSec(markers));
  }, [markerFitKey]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const onPointerDown = () => {
      pointerOnScrollerRef.current = true;
      lockView();
      window.clearTimeout(scrollSettleTimerRef.current);
    };

    const onPointerUp = () => {
      if (!pointerOnScrollerRef.current) return;
      pointerOnScrollerRef.current = false;
      scheduleResumeLive();
    };

    const onScroll = () => {
      syncViewMsFromScroll(el);
      if (programmaticScrollRef.current) return;
      lockView();
      if (pointerOnScrollerRef.current) return;
      scheduleResumeLive();
    };

    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);

    return () => {
      window.clearTimeout(scrollSettleTimerRef.current);
      el.removeEventListener("pointerdown", onPointerDown);
      el.removeEventListener("scroll", onScroll);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
    };
  }, [elapsedMs, lockView, pxPerSec, scheduleResumeLive]);

  useLayoutEffect(() => {
    if (viewLocked) return;
    const el = scrollRef.current;
    if (!el) return;
    applyPlayheadScroll(el);
  }, [
    viewLocked,
    elapsedMs,
    elapsedPx,
    contentHeight,
    pxPerSec,
    markers.length,
    markers[markers.length - 1]?.id,
    applyPlayheadScroll,
  ]);

  useEffect(() => {
    if (!viewLocked) setViewMs(elapsedMs);
  }, [elapsedMs, viewLocked]);

  useEffect(() => {
    if (trackHistory.length <= prevHistoryLenRef.current) {
      prevHistoryLenRef.current = trackHistory.length;
      return;
    }
    prevHistoryLenRef.current = trackHistory.length;
    resumeLiveView();
  }, [trackHistory.length, resumeLiveView]);

  const zoomIn = () => {
    userZoomRef.current = true;
    setPxPerSec((p) => Math.min(MAX_PX_PER_SEC, p * ZOOM_FACTOR));
  };
  const zoomOut = () => {
    userZoomRef.current = true;
    setPxPerSec((p) => Math.max(MIN_PX_PER_SEC, p / ZOOM_FACTOR));
  };

  const activeTrack = useMemo(
    () => trackActiveAtView(trackHistory, viewMs, elapsedMs),
    [trackHistory, viewMs, elapsedMs],
  );
  const activeTrackKey = activeTrack ? trackEntryKey(activeTrack) : null;

  return (
    <div className="px-3 py-3">
      <div className="grid min-w-0 grid-cols-[3fr_5fr_2fr] gap-2">
        <div className="flex min-w-0 gap-0.5">
          <div className="flex shrink-0 flex-col justify-start gap-0.5">
            <ZoomButton
              label="Zoom in"
              icon={<ZoomInIcon />}
              onClick={zoomIn}
              disabled={pxPerSec >= MAX_PX_PER_SEC}
            />
            <ZoomButton
              label="Zoom out"
              icon={<ZoomOutIcon />}
              onClick={zoomOut}
              disabled={pxPerSec <= MIN_PX_PER_SEC}
            />
          </div>
          <div
            ref={scrollRef}
            className="moony-mood-timeline-scroll moony-mood-timeline-axis-scroll min-w-0 flex-1 overflow-x-auto overflow-y-auto"
            style={{ height: TIMELINE_VIEWPORT_H }}
          >
          <div
            className="relative"
            style={{ height: contentHeight, minWidth: timelineContentMinW }}
          >
            <div
              className="absolute bottom-0 left-0 right-0"
              style={{ height: elapsedPx }}
            >
              <div
                className="absolute bottom-0 left-2 z-[1] w-4 -translate-x-1/2 overflow-hidden rounded-full bg-white/10"
                style={{ height: elapsedPx }}
              >
                {trail.map((seg, i) => {
                  const bottomPx = msToPx(seg.from, pxPerSec);
                  const endMs = seg.to ?? elapsedMs;
                  const heightPx = Math.max(msToPx(endMs - seg.from, pxPerSec), 3);
                  return (
                    <span
                      key={`${seg.zone}-${seg.from}-${i}`}
                      title={seg.zone}
                      className="absolute inset-x-0"
                      style={{
                        bottom: bottomPx,
                        height: heightPx,
                        backgroundColor: moodColorForName(seg.zone),
                      }}
                    />
                  );
                })}
                {activeTrack ? (
                  <span
                    className="moony-timeline-track-stripe pointer-events-none absolute inset-x-0 transition-[bottom,height] duration-200"
                    style={{
                      bottom: msToPx(activeTrack.fromMs, pxPerSec),
                      height: Math.max(
                        msToPx(
                          (activeTrack.toMs ?? elapsedMs) - activeTrack.fromMs,
                          pxPerSec,
                        ),
                        3,
                      ),
                    }}
                    title={activeTrack.title}
                  />
                ) : null}
                <span
                  className="pointer-events-none absolute inset-x-0 top-0 z-[1] h-0.5 bg-white/90 shadow-[0_0_6px_rgba(255,255,255,0.65)]"
                  aria-hidden
                />
              </div>

              {markers.map((ev) => {
                const bottomPx = msToPx(ev.at, pxPerSec);
                const style = markerStyle(ev.kind, ev);
                const compact = compactIds.has(ev.id);
                const tooltip = `${fmtOffset(ev.at)} · ${style.label}`;
                return (
                  <span
                    key={ev.id}
                    className="absolute left-4 z-[2] flex -translate-y-1/2 items-center gap-1.5 whitespace-nowrap"
                    style={{ bottom: bottomPx }}
                    title={tooltip}
                  >
                    {compact ? (
                      <>
                        <span className="h-px w-2 shrink-0 bg-white/30" aria-hidden />
                        <span
                          className="block h-0.5 w-6 shrink-0 rounded-full"
                          style={{ backgroundColor: style.color }}
                          aria-hidden
                        />
                      </>
                    ) : (
                      <>
                        <span className="shrink-0 text-[15px] leading-none tabular-nums text-white/35">
                          {fmtOffset(ev.at)}
                        </span>
                        <span className="h-px w-2 shrink-0 bg-white/30" aria-hidden />
                        <MarkerDot kind={ev.kind} ev={ev} />
                        <span
                          className="text-[15px] leading-none"
                          style={{ color: style.color }}
                        >
                          {style.label}
                        </span>
                      </>
                    )}
                  </span>
                );
              })}
            </div>
          </div>
          </div>
        </div>

        <TrackHistoryList
          history={trackHistory}
          elapsedMs={elapsedMs}
          viewLocked={viewLocked}
          activeTrackKey={activeTrackKey}
          listResetSeq={listResetSeq}
          onListPointerDown={onTrackListPointerDown}
          onListScroll={onTrackListScroll}
          onReplayTrack={onReplayTrack}
        />

        <div className="min-w-0 border-l border-white/10 pl-2">
          <SessionStats />
        </div>
      </div>
    </div>
  );
}

type Props = {
  isPlaying: boolean;
  className?: string;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  /** Strip outer chrome when docked in a merged bar. */
  embedded?: boolean;
  onReplayTrack?: (track: MoodTrackEntry) => void;
};

export function MoodMonitorPanel({
  isPlaying,
  className = "",
  collapsed: collapsedProp,
  onCollapsedChange,
  embedded = false,
  onReplayTrack,
}: Props) {
  const [events, setEvents] = useState<MoodMonitorEvent[]>([]);
  const [trackHistory, setTrackHistory] = useState<MoodTrackEntry[]>([]);
  const [collapsedInternal, setCollapsedInternal] = useState(true);
  const collapsed = collapsedProp ?? collapsedInternal;
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    if (!moodMonitor.isEnabled()) return;
    const sync = () => {
      setEvents([...moodMonitor.getEvents()]);
      setTrackHistory([...moodMonitor.getTrackHistory()]);
      setElapsedMs(moodMonitor.getElapsedMs());
    };
    sync();
    return moodMonitor.subscribe(sync);
  }, []);

  useEffect(() => {
    if (!moodMonitor.isEnabled() || !isPlaying) return;
    const id = window.setInterval(() => {
      setElapsedMs(moodMonitor.getElapsedMs());
    }, 1000);
    return () => window.clearInterval(id);
  }, [isPlaying]);

  if (!moodMonitor.isEnabled()) return null;

  const currentMood = moodMonitor.getCurrentMood();
  const sessionActive = moodMonitor.isSessionActive();
  const markers = events.filter((ev) => MARKER_KINDS.has(ev.kind));

  const setCollapsed = (next: boolean | ((prev: boolean) => boolean)) => {
    const value = typeof next === "function" ? next(collapsed) : next;
    if (onCollapsedChange) onCollapsedChange(value);
    else setCollapsedInternal(value);
  };
  const toggleCollapsed = () => setCollapsed((c) => !c);

  const shellClass = embedded
    ? "w-full rounded-none border-0 bg-transparent shadow-none backdrop-blur-none"
    : "w-full rounded-xl border border-rose-400/25 bg-black/90 shadow-2xl backdrop-blur-sm";

  return (
    <section
      data-testid="timeline-panel"
      className={`${shellClass} ${className}`}
    >
      <header
        className={`flex cursor-pointer items-center justify-between gap-2 px-3 py-2 ${
          !collapsed && sessionActive ? "border-b border-white/10" : ""
        }`}
        onClick={toggleCollapsed}
        aria-expanded={!collapsed}
      >
        <div className="pointer-events-none min-w-0 flex-1">
          <p className="text-[18px] font-semibold uppercase tracking-wide text-rose-300">
            TIMELINE
          </p>
          <p className="truncate text-[15px] text-white/45">
            {currentMood ? (
              <>
                <span
                  className="mr-1 inline-block h-3 w-3 rounded-full align-middle"
                  style={{ backgroundColor: moodColorForName(currentMood) }}
                />
                {currentMood}
                {sessionActive ? ` · ${fmtOffset(elapsedMs)}` : ""}
              </>
            ) : (
              "Waiting for session…"
            )}
          </p>
        </div>
        <button
          type="button"
          className="pointer-events-auto shrink-0 rounded px-2 py-1 text-[15px] text-white/50 hover:bg-white/10 hover:text-white/80"
          onClick={(e) => {
            e.stopPropagation();
            toggleCollapsed();
          }}
        >
          {collapsed ? "Expand" : "Collapse"}
        </button>
      </header>

      {!collapsed && sessionActive ? (
        <MoodTimeline
          elapsedMs={elapsedMs}
          markers={markers}
          trackHistory={trackHistory}
          onReplayTrack={onReplayTrack}
        />
      ) : null}
    </section>
  );
}
