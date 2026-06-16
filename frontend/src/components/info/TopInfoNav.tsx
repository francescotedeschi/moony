type Panel = "api" | "about";

type Props = {
  active: Panel | null;
  onSelect: (panel: Panel) => void;
};

export function TopInfoNav({ active, onSelect }: Props) {
  const linkClass = (panel: Panel) =>
    `rounded-lg border px-3 py-1.5 text-xs font-medium tracking-wide transition ${
      active === panel
        ? "border-moony-accent/50 bg-moony-accent/15 text-moony-glow"
        : "border-white/10 bg-black/25 text-white/55 hover:border-white/20 hover:bg-white/5 hover:text-white/80"
    }`;

  return (
    <nav
      className="fixed right-4 top-4 z-[55] flex gap-2"
      aria-label="Information"
      data-testid="top-info-nav"
    >
      <button type="button" className={linkClass("api")} onClick={() => onSelect("api")}>
        API
      </button>
      <button type="button" className={linkClass("about")} onClick={() => onSelect("about")}>
        About
      </button>
    </nav>
  );
}

export type { Panel as InfoPanel };
