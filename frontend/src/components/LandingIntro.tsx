import { useState } from "react";
import { MOONY_TRY_STEPS } from "../lib/moonyTrySteps";

type Props = {
  onOpenAbout: () => void;
  onOpenApi: () => void;
};

export function LandingIntro({ onOpenAbout, onOpenApi }: Props) {
  const [stepsOpen, setStepsOpen] = useState(false);

  return (
    <div className="landing-intro" data-testid="landing-intro">
      <h2 className="landing-intro-heading">How it works</h2>

      <button
        type="button"
        className="landing-intro-steps-toggle"
        aria-expanded={stepsOpen}
        onClick={() => setStepsOpen((open) => !open)}
      >
        {stepsOpen ? "Hide steps" : "How it works"}
      </button>

      <ol
        className={`landing-intro-steps${stepsOpen ? " landing-intro-steps--open" : ""}`}
        aria-label="How to try Moony"
      >
        {MOONY_TRY_STEPS.map((step, i) => (
          <li
            key={step.n}
            className="landing-intro-step"
            style={{ animationDelay: `${0.08 + i * 0.07}s` }}
          >
            <span className="landing-intro-step-n" aria-hidden>
              {step.n}
            </span>
            <div>
              <p className="landing-intro-step-title">{step.title}</p>
              <p className="landing-intro-step-body">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>

      <div className="landing-intro-actions">
        <button type="button" className="landing-intro-btn" onClick={onOpenAbout}>
          About Moony
        </button>
        <button type="button" className="landing-intro-btn landing-intro-btn--accent" onClick={onOpenApi}>
          Explore the API
        </button>
      </div>
    </div>
  );
}
