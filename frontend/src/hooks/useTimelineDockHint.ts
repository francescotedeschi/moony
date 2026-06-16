import { useCallback, useEffect, useState } from "react";

const SEEN_KEY = "moony-timeline-dock-hint-seen";
/** Show Timeline hint after this much listening time in the first sessions. */
const DELAY_MS = 2 * 60 * 1000;

export function useTimelineDockHint(sessionActive: boolean) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!sessionActive) {
      setShow(false);
      return;
    }
    try {
      if (localStorage.getItem(SEEN_KEY) === "1") return;
    } catch {
      /* ignore */
    }

    const id = window.setTimeout(() => setShow(true), DELAY_MS);
    return () => window.clearTimeout(id);
  }, [sessionActive]);

  const dismiss = useCallback(() => {
    setShow(false);
    try {
      localStorage.setItem(SEEN_KEY, "1");
    } catch {
      /* ignore */
    }
  }, []);

  return { showTimelineHint: show, dismissTimelineHint: dismiss };
}
