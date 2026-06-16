import { useEffect, type ReactNode } from "react";

type Props = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
  wide?: boolean;
};

export function InfoPanelShell({ open, title, onClose, children, testId, wide }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex justify-end">
      <button
        type="button"
        aria-label="Close panel"
        className="absolute inset-0 bg-black/55 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal
        aria-labelledby="info-panel-title"
        data-testid={testId}
        className={`relative flex h-full w-full flex-col border-l border-white/10 bg-moony-bg shadow-[-12px_0_48px_rgba(0,0,0,0.55)] ${
          wide ? "max-w-3xl" : "max-w-lg sm:max-w-xl"
        }`}
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
          <h2 id="info-panel-title" className="text-lg font-medium tracking-tight">
            {title}
          </h2>
          <button
            type="button"
            data-testid="info-panel-close"
            onClick={onClose}
            className="shrink-0 rounded-lg border border-white/10 px-2.5 py-1 text-sm text-white/55 transition hover:bg-white/5 hover:text-white/80"
          >
            Close
          </button>
        </div>
        <div className="info-panel-body min-h-0 flex-1 overflow-y-auto px-5 py-5">{children}</div>
      </div>
    </div>
  );
}
