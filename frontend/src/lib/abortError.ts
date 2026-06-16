const ABORT_REASONS = new Set([
  "track-change",
  "session-stop",
  "panel-close",
  "play-count",
  "handoff",
]);

function messageLooksAborted(message: string): boolean {
  const trimmed = message.trim();
  if (ABORT_REASONS.has(trimmed)) return true;
  const msg = trimmed.toLowerCase();
  return (
    msg.includes("signal is aborted") ||
    msg.includes("without reason") ||
    msg.includes("the user aborted") ||
    msg.includes("operation was aborted") ||
    msg.includes("aborterror")
  );
}

/** True when a fetch/task was cancelled via AbortController (expected, not a user error). */
export function isAbortError(err: unknown): boolean {
  if (err == null) return false;

  if (typeof err === "string") {
    return messageLooksAborted(err);
  }

  if (typeof err === "object") {
    const named = err as {
      name?: string;
      message?: string;
      cause?: unknown;
      errors?: unknown[];
    };
    if (named.name === "AbortError") return true;
    if (named.cause != null && isAbortError(named.cause)) return true;
    if (Array.isArray(named.errors) && named.errors.some((e) => isAbortError(e))) {
      return true;
    }
    if (typeof named.message === "string" && messageLooksAborted(named.message)) {
      return true;
    }
  }

  return false;
}

/** User-visible error text; null when the failure was an expected abort. */
export function errorMessage(err: unknown, fallback: string): string | null {
  if (isAbortError(err)) return null;
  if (err instanceof Error) {
    const msg = err.message.trim();
    if (!msg || messageLooksAborted(msg)) return null;
    return msg;
  }
  if (typeof err === "string") {
    const msg = err.trim();
    if (!msg || messageLooksAborted(msg)) return null;
    return msg;
  }
  return fallback;
}
