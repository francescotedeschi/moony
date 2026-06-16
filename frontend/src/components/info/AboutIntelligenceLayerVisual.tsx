/** Catalog → Moony → product outputs — Intelligence Layer mini diagram. */

const OUTPUTS = ["Focus", "Fitness", "Gaming", "Streaming"] as const;

export function AboutIntelligenceLayerVisual() {
  return (
    <div className="about-intel-layer-visual" aria-hidden>
      <div className="about-intel-layer-node">Music Catalog</div>
      <span className="about-intel-layer-arrow">→</span>
      <div className="about-intel-layer-node about-intel-layer-node--accent">Moony API</div>
      <span className="about-intel-layer-arrow">→</span>
      <div className="about-intel-layer-outputs">
        {OUTPUTS.map((label) => (
          <span key={label} className="about-intel-layer-output">
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
