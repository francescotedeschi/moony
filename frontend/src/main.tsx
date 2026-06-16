import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import FluidPadDemo from "./pages/FluidPadDemo";
import "./index.css";

const pathname = window.location.pathname.replace(/\/$/, "") || "/";

function RootPage() {
  if (pathname === "/demo/fluid-pad") return <FluidPadDemo />;
  return <App />;
}

const rootEl = document.getElementById("root");

if (!rootEl) {
  throw new Error("Missing #root element");
}

try {
  ReactDOM.createRoot(rootEl).render(
    <React.StrictMode>
      <ErrorBoundary>
        <RootPage />
      </ErrorBoundary>
    </React.StrictMode>,
  );
} catch (error) {
  const message = error instanceof Error ? error.message : "Unknown startup error";
  rootEl.innerHTML = `
    <div style="display:flex;min-height:100vh;align-items:center;justify-content:center;padding:2rem;text-align:center;font-family:system-ui,sans-serif;color:rgba(255,255,255,0.85);background:#0a0a0f;">
      <div>
        <p style="font-size:1.25rem;margin:0 0 0.75rem;">Moony failed to start</p>
        <p style="font-size:0.875rem;opacity:0.7;margin:0 0 1rem;">${message}</p>
        <button type="button" onclick="location.reload()" style="border:1px solid rgba(255,255,255,0.2);background:rgba(255,255,255,0.06);color:white;border-radius:999px;padding:0.5rem 1rem;cursor:pointer;">Reload</button>
      </div>
    </div>
  `;
  console.error("[moony] Startup error:", error);
}
