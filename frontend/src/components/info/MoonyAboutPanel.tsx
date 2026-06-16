import { useEffect, useState } from "react";
import { AboutProblemVisual } from "./AboutProblemVisual";
import { AboutSegmentSearchVisual } from "./AboutSegmentSearchVisual";
import { InfoPanelShell } from "./InfoPanelShell";
import { MOOD_COLORS } from "../../lib/emotions";

type Props = {
  open: boolean;
  onClose: () => void;
  onExploreApi?: () => void;
};

const ABOUT_NAV = [
  { id: "about-problem", label: "Problem" },
  { id: "about-approach", label: "Approach" },
  { id: "about-how", label: "How it works" },
  { id: "about-use-cases", label: "Use cases" },
] as const;

const ABOUT_SECTION_IDS = ABOUT_NAV.map(({ id }) => id);

const ABOUT_VALUE_PROPS = [
  "Segment-level emotion",
  "Catalog-agnostic API",
  "Adaptive listening journeys",
] as const;

function scrollAboutSection(id: string) {
  const body = document.querySelector('[data-testid="moony-about-panel"] .info-panel-body');
  body?.querySelector(`#${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function AboutSection({
  id,
  title,
  subtitle,
  visual,
  children,
}: {
  id: string;
  title: string;
  subtitle?: string;
  visual?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="about-section">
      <h3 className="about-section-title">{title}</h3>
      {subtitle ? <p className="about-section-subtitle">{subtitle}</p> : null}
      {visual ? <div className="about-visual">{visual}</div> : null}
      <div className="about-section-body">{children}</div>
    </section>
  );
}

function AboutNav({ activeSection }: { activeSection: string }) {
  return (
    <nav className="about-nav" aria-label="About sections">
      {ABOUT_NAV.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          className={`about-nav-link${id === activeSection ? " about-nav-link--active" : ""}`}
          aria-current={id === activeSection ? "true" : undefined}
          onClick={() => scrollAboutSection(id)}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}

function TrackToMapVisual() {
  const rows = [
    { section: "Intro", mood: "calm" },
    { section: "Verse", mood: "tension" },
    { section: "Chorus", mood: "joy" },
    { section: "Bridge", mood: "energy" },
    { section: "Outro", mood: "sad" },
  ];
  return (
    <div className="about-map-flow" aria-hidden>
      <div className="about-map-track">
        {rows.map((row) => {
          const color = MOOD_COLORS[row.mood];
          return (
            <div
              key={row.section}
              className="about-map-track-seg"
              style={{ backgroundColor: `${color}55`, borderColor: `${color}99` }}
            >
              {row.section}
            </div>
          );
        })}
      </div>
      <div className="about-map-arrow">↓</div>
      <div className="about-map-tags">
        {rows.map((row) => (
          <span key={row.section} className="about-map-tag" style={{ color: MOOD_COLORS[row.mood] }}>
            {row.mood}
          </span>
        ))}
      </div>
      <p className="about-map-caption">Track → Sections → Emotional Map</p>
    </div>
  );
}

function UseCaseGridVisual() {
  const cases = [
    { label: "Focus", color: MOOD_COLORS.calm },
    { label: "Study", color: MOOD_COLORS.joy },
    { label: "Workout", color: MOOD_COLORS.energy },
    { label: "Wellness", color: MOOD_COLORS.sad },
    { label: "Gaming", color: MOOD_COLORS.tension },
    { label: "Streaming", color: "#38bdf8" },
  ];
  return (
    <div className="about-use-grid" aria-hidden>
      {cases.map((item) => (
        <div key={item.label} className="about-use-card">
          <svg viewBox="0 0 48 20" className="about-use-spark">
            <path
              d="M2 14 Q12 4, 24 10 T46 8"
              fill="none"
              stroke={item.color}
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
}

function useAboutActiveSection(open: boolean) {
  const [activeSection, setActiveSection] = useState<string>(ABOUT_SECTION_IDS[0]);

  useEffect(() => {
    if (!open) return;

    const body = document.querySelector('[data-testid="moony-about-panel"] .info-panel-body');
    if (!body) return;

    const sections = ABOUT_SECTION_IDS.map((id) => body.querySelector(`#${id}`)).filter(
      (el): el is HTMLElement => el instanceof HTMLElement,
    );
    if (sections.length === 0) return;

    const visible = new Map<string, number>();

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          visible.set(entry.target.id, entry.intersectionRatio);
        }
        let bestId = ABOUT_SECTION_IDS[0];
        let bestRatio = -1;
        for (const id of ABOUT_SECTION_IDS) {
          const ratio = visible.get(id) ?? 0;
          if (ratio > bestRatio) {
            bestRatio = ratio;
            bestId = id;
          }
        }
        if (bestRatio > 0) setActiveSection(bestId);
      },
      { root: body, rootMargin: "-12% 0px -55% 0px", threshold: [0, 0.1, 0.25, 0.5, 0.75, 1] },
    );

    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [open]);

  return activeSection;
}

export function MoonyAboutPanel({ open, onClose, onExploreApi }: Props) {
  const activeSection = useAboutActiveSection(open);

  return (
    <InfoPanelShell open={open} title="About" wide testId="moony-about-panel" onClose={onClose}>
      <div className="about-page">
        <section className="about-hero">
          <h2 className="about-hero-brand moony-title">moony</h2>
          <p className="about-hero-tagline">
            <span className="about-hero-tagline-line">the emotional intelligence API</span>
            <span className="about-hero-tagline-line">for music catalogs</span>
          </p>
          <ul className="about-hero-values" aria-label="Key capabilities">
            {ABOUT_VALUE_PROPS.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="about-hero-lead">
            Moony analyzes music at segment level and builds listening journeys that adapt to mood,
            activity, and context—without rebuilding your catalog.
          </p>
          <div className="about-hero-ctas">
            <button type="button" className="about-cta about-cta--accent" onClick={onClose}>
              Start listening
            </button>
            <button
              type="button"
              className="about-cta"
              onClick={() => {
                onClose();
                onExploreApi?.();
              }}
            >
              Explore the API
            </button>
          </div>
        </section>

        <AboutNav activeSection={activeSection} />

        <AboutSection
          id="about-problem"
          title="The Problem"
          subtitle="Mood playlists are static. People are not."
          visual={<AboutProblemVisual />}
        >
          <p>
            Most music apps lock users into fixed mood categories—a focus playlist stays calm until
            someone manually switches. Real sessions shift: concentration becomes motivation, intensity
            becomes recovery, gameplay ramps up and down.
          </p>
          <p>The challenge is keeping the right mood without interrupting the listener.</p>
        </AboutSection>

        <AboutSection
          id="about-approach"
          title="Section-Level Intelligence"
          subtitle="Not a player—the brain behind adaptive listening."
          visual={<TrackToMapVisual />}
        >
          <p>
            Moony reads each song as a sequence of sections, each with its own mood, energy, and
            transition potential—so it understands how a track evolves moment by moment.
          </p>
          <ul className="about-list">
            <li>Indexes catalogs by emotion, activity, and context—not just genre or BPM.</li>
            <li>Selects the best next segment instead of only the next track.</li>
            <li>Integrates into streaming, focus, fitness, wellness, and gaming products.</li>
          </ul>
        </AboutSection>

        <AboutSection
          id="about-how"
          title="How It Works"
          subtitle="Multi-layer analysis, section-level search."
          visual={<AboutSegmentSearchVisual />}
        >
          <p>Every segment gets a rich emotional profile from three complementary layers:</p>
          <ul className="about-list">
            <li>
              <strong>Musixmatch</strong> — section lyrics and word-level timing
            </li>
            <li>
              <strong>Cyanite</strong> — BPM, valence, arousal, mood labels, and energy curve
            </li>
            <li>
              <strong>MOSS-Music</strong> — section identification, semantic meaning, and performance
            </li>
          </ul>
          <p>
            Moony then searches for the best next moment—not just &ldquo;happy songs&rdquo;—weighing
            mood, lyrical theme, transition quality, and the direction you want to move.
          </p>
        </AboutSection>

        <AboutSection
          id="about-use-cases"
          title="Use Cases"
          subtitle="Built for real listening contexts."
          visual={<UseCaseGridVisual />}
        >
          <ul className="about-list">
            <li>
              <strong>Focus &amp; study</strong> — calm concentration that can ramp into motivation
              without leaving the session
            </li>
            <li>
              <strong>Fitness</strong> — high-energy sections for effort, softer moments for recovery
            </li>
            <li>
              <strong>Wellness &amp; gaming</strong> — smoother emotional arcs that follow intensity in
              real time
            </li>
            <li>
              <strong>Streaming</strong> — mood-based listening that moves with the listener, not fixed
              playlists
            </li>
          </ul>
        </AboutSection>

        <section className="about-section about-closing">
          <h3 className="about-section-title">Moony is not another mood playlist generator.</h3>
          <p className="about-closing-statement">
            It is the emotional intelligence API that turns existing catalogs into adaptive
            experiences—fast to integrate, catalog-agnostic.
          </p>
          <p className="about-trust-strip">Powered by MOSS-Music · Musixmatch · Cyanite</p>
          <div className="about-hero-ctas about-closing-ctas">
            <button type="button" className="about-cta about-cta--accent" onClick={onClose}>
              Start listening
            </button>
            <button
              type="button"
              className="about-cta"
              onClick={() => {
                onClose();
                onExploreApi?.();
              }}
            >
              Open API reference
            </button>
          </div>
        </section>
      </div>
    </InfoPanelShell>
  );
}
