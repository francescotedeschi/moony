import { useEffect, useState } from "react";

const STORAGE_KEY = "moony-post-play-hint-dismissed";

export function dismissPostPlayHint() {
  try {
    localStorage.setItem(STORAGE_KEY, "1");
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent("moony-post-play-dismissed"));
}

export function PostPlayHint() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      setVisible(localStorage.getItem(STORAGE_KEY) !== "1");
    } catch {
      setVisible(true);
    }
  }, []);

  useEffect(() => {
    const onDismissed = () => setVisible(false);
    window.addEventListener("moony-post-play-dismissed", onDismissed);
    return () => window.removeEventListener("moony-post-play-dismissed", onDismissed);
  }, []);

  if (!visible) return null;

  return (
    <div className="post-play-hint" data-testid="post-play-hint" role="status">
      <p className="post-play-hint-text">
        Drag the mood pad to change direction · The mood sections bar shows where you are in the song
      </p>
      <button
        type="button"
        className="post-play-hint-dismiss"
        onClick={dismissPostPlayHint}
        aria-label="Dismiss hint"
      >
        ✕
      </button>
    </div>
  );
}
