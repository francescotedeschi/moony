import { useEffect, useRef, useState } from "react";
import { FEATURE_TIP_DURATION_MS } from "../hooks/useFeatureTips";

type Props = {
  title: string;
  body: string;
  onDismiss: () => void;
  className?: string;
  testId?: string;
};

export function FeatureTipToast({ title, body, onDismiss, className = "", testId }: Props) {
  const [progress, setProgress] = useState(100);
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;

  useEffect(() => {
    setProgress(100);
    const started = performance.now();
    let frame = 0;
    let dismissed = false;

    const tick = (now: number) => {
      const elapsed = now - started;
      const remaining = Math.max(0, 100 - (elapsed / FEATURE_TIP_DURATION_MS) * 100);
      setProgress(remaining);
      if (remaining > 0) {
        frame = requestAnimationFrame(tick);
      } else if (!dismissed) {
        dismissed = true;
        onDismissRef.current();
      }
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [title, body]);

  return (
    <div
      className={`feature-tip ${className}`.trim()}
      data-testid={testId}
      role="status"
    >
      <div className="feature-tip-progress" style={{ width: `${progress}%` }} aria-hidden />
      <div className="feature-tip-content">
        <p className="feature-tip-title">{title}</p>
        <p className="feature-tip-body">{body}</p>
      </div>
      <button type="button" className="feature-tip-dismiss" onClick={onDismiss} aria-label="Dismiss tip">
        ✕
      </button>
    </div>
  );
}
