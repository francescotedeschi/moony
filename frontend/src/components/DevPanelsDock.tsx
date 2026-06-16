import { useState } from "react";
import { CatalogInfoPanel } from "./CatalogInfoPanel";
import { MoodMonitorPanel } from "./MoodMonitorPanel";
import { moodMonitor, type MoodTrackEntry } from "../lib/moodMonitor";

import { FeatureTipToast } from "./FeatureTipToast";
import type { FeatureTip } from "../hooks/useFeatureTips";

type Props = {
  isPlaying: boolean;
  onReplayHistoryTrack?: (track: MoodTrackEntry) => void;
  featureTip?: FeatureTip | null;
  onFeatureTipDismiss?: () => void;
  timelineDockHint?: boolean;
  onTimelineDockHintDismiss?: () => void;
};

export function DevPanelsDock({
  isPlaying,
  onReplayHistoryTrack,
  featureTip,
  onFeatureTipDismiss,
  timelineDockHint = false,
  onTimelineDockHintDismiss,
}: Props) {
  const [timelineCollapsed, setTimelineCollapsed] = useState(true);
  const [catalogCollapsed, setCatalogCollapsed] = useState(true);
  const timelineEnabled = moodMonitor.isEnabled();
  const mergedBar =
    timelineEnabled && timelineCollapsed && catalogCollapsed;

  const onTimelineCollapsedChange = (collapsed: boolean) => {
    setTimelineCollapsed(collapsed);
    if (!collapsed) onTimelineDockHintDismiss?.();
  };

  const showTimelineFeatureTip = featureTip?.id === "timeline" && onFeatureTipDismiss;
  const showTimelineDockTip = timelineDockHint && onTimelineDockHintDismiss && !showTimelineFeatureTip;

  return (
    <div
      className="pointer-events-none fixed inset-x-4 bottom-4 z-50 sm:mx-auto sm:max-w-[min(1280px,calc(100vw-2rem))]"
      data-testid="dev-panels-dock"
    >
      <div className="relative">
        {showTimelineFeatureTip ? (
          <FeatureTipToast
            title={featureTip.title}
            body={featureTip.body}
            onDismiss={onFeatureTipDismiss}
            className="feature-tip--dock-left"
            testId="feature-tip-timeline"
          />
        ) : null}
        {showTimelineDockTip ? (
          <FeatureTipToast
            title="Timeline"
            body="Review your session—tracks played, mood shifts, skips, and replays in one chronological view."
            onDismiss={onTimelineDockHintDismiss}
            className="feature-tip--dock-left"
            testId="feature-tip-timeline-dock"
          />
        ) : null}
        {featureTip?.id === "catalog" && onFeatureTipDismiss ? (
          <FeatureTipToast
            title={featureTip.title}
            body={featureTip.body}
            onDismiss={onFeatureTipDismiss}
            className="feature-tip--dock-right"
            testId="feature-tip-catalog"
          />
        ) : null}
        <div
          className={
            mergedBar
              ? "pointer-events-auto grid grid-cols-1 overflow-hidden rounded-xl bg-black/90 shadow-2xl backdrop-blur-sm sm:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"
              : "grid grid-cols-1 items-end gap-3 sm:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"
          }
        >
        {timelineEnabled ? (
          <MoodMonitorPanel
            isPlaying={isPlaying}
            collapsed={timelineCollapsed}
            onCollapsedChange={onTimelineCollapsedChange}
            embedded={mergedBar}
            className="pointer-events-auto min-w-0"
            onReplayTrack={onReplayHistoryTrack}
          />
        ) : null}
        <CatalogInfoPanel
          collapsed={catalogCollapsed}
          onCollapsedChange={setCatalogCollapsed}
          embedded={mergedBar}
          embeddedDivider={mergedBar && timelineEnabled}
          className="pointer-events-auto min-w-0"
        />
      </div>
      </div>
    </div>
  );
}
