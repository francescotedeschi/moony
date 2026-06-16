import { useCallback, useEffect, useRef, useState } from "react";

export type FeatureTipId = "matches" | "timeline" | "catalog";

export type FeatureTip = {
  id: FeatureTipId;
  title: string;
  body: string;
};

export const FEATURE_TIPS: FeatureTip[] = [
  {
    id: "matches",
    title: "Show Matches",
    body: "Preview the next tracks and entry segments Moony's API would pick from your current mood.",
  },
  {
    id: "timeline",
    title: "Timeline",
    body: "Review your session—tracks played, mood shifts, skips, and replays in one chronological view.",
  },
  {
    id: "catalog",
    title: "Catalog",
    body: "Explore mood distribution, track count, and coverage for the catalog powering this demo.",
  },
];

const SEEN_KEY = "moony-feature-tips-seen";
const POST_PLAY_KEY = "moony-post-play-hint-dismissed";
export const FEATURE_TIP_DURATION_MS = 10_000;
const START_DELAY_MS = 800;

/** First session: post-play hint, then a single Matches tip only. */
const ONBOARDING_TIP_IDS: FeatureTipId[] = ["matches"];

function loadSeenTips(): Set<FeatureTipId> {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as FeatureTipId[]);
  } catch {
    return new Set();
  }
}

function markTipSeen(id: FeatureTipId) {
  try {
    const seen = loadSeenTips();
    seen.add(id);
    localStorage.setItem(SEEN_KEY, JSON.stringify([...seen]));
  } catch {
    /* ignore */
  }
}

function pendingOnboardingTips(): FeatureTip[] {
  const seen = loadSeenTips();
  return FEATURE_TIPS.filter(
    (tip) => ONBOARDING_TIP_IDS.includes(tip.id) && !seen.has(tip.id),
  );
}

export function useFeatureTips(sessionActive: boolean) {
  const [currentTip, setCurrentTip] = useState<FeatureTip | null>(null);
  const queueRef = useRef<FeatureTip[]>([]);
  const startTimerRef = useRef<number | null>(null);
  const showNextRef = useRef<() => void>(() => {});

  const clearStartTimer = () => {
    if (startTimerRef.current != null) {
      window.clearTimeout(startTimerRef.current);
      startTimerRef.current = null;
    }
  };

  showNextRef.current = () => {
    const next = queueRef.current.shift() ?? null;
    setCurrentTip(next);
  };

  const dismissCurrent = useCallback(() => {
    setCurrentTip((tip) => {
      if (tip) markTipSeen(tip.id);
      return null;
    });
    window.setTimeout(() => showNextRef.current(), 0);
  }, []);

  useEffect(() => {
    if (!sessionActive) {
      clearStartTimer();
      setCurrentTip(null);
      queueRef.current = [];
      return;
    }

    let cancelled = false;

    queueRef.current = pendingOnboardingTips();
    if (queueRef.current.length === 0) return;

    const beginQueue = () => {
      if (cancelled || startTimerRef.current != null) return;
      startTimerRef.current = window.setTimeout(() => {
        startTimerRef.current = null;
        if (cancelled) return;
        showNextRef.current();
      }, START_DELAY_MS);
    };

    let postPlaySeen = false;
    try {
      postPlaySeen = localStorage.getItem(POST_PLAY_KEY) === "1";
    } catch {
      postPlaySeen = true;
    }

    if (postPlaySeen) {
      beginQueue();
    } else {
      const onPostPlayDismiss = () => beginQueue();
      window.addEventListener("moony-post-play-dismissed", onPostPlayDismiss, { once: true });
      return () => {
        cancelled = true;
        window.removeEventListener("moony-post-play-dismissed", onPostPlayDismiss);
        clearStartTimer();
      };
    }

    return () => {
      cancelled = true;
      clearStartTimer();
    };
  }, [sessionActive]);

  return { currentTip, dismissCurrent };
}
