import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
};

type State = {
  error: Error | null;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[moony] UI error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 p-6 text-center">
          <h1 className="moony-title text-4xl tracking-tight">moony</h1>
          <p className="text-sm text-white/70">
            Something went wrong loading the demo. Try a normal browser window or refresh the page.
          </p>
          <p className="rounded-lg border border-red-400/30 bg-red-950/40 px-3 py-2 font-mono text-xs text-red-200/90">
            {this.state.error.message}
          </p>
          <button
            type="button"
            className="rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm text-white/80 transition hover:bg-white/10"
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
