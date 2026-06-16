import { useState } from "react";
import { getApiBaseUrlLabel } from "../../lib/api";
import { InfoPanelShell } from "./InfoPanelShell";

type Props = {
  open: boolean;
  onClose: () => void;
  onOpenAbout?: () => void;
};

type ApiItem = {
  id: string;
  method: "GET" | "POST";
  path: string;
  summary: string;
  example: string;
};

const TRACK_DATA: ApiItem[] = [
  {
    id: "track",
    method: "GET",
    path: "/tracks/{id}",
    summary: "Track metadata, macro segments, and optional full motion payload.",
    example: `GET /tracks/jamendo_1007926

{
  "id": "jamendo_1007926",
  "title": "San Frutos",
  "artist": "Ra00",
  "bpm": 136,
  "duration_ms": 313000,
  "has_motion": true,
  "segments": [
    { "t_start": 0, "t_end": 45000, "v": 0.2, "ar": -0.5, "label": "intro" }
  ]
}`,
  },
  {
    id: "timeline",
    method: "GET",
    path: "/tracks/{id}/timeline",
    summary: "MOSS segment map for timelines: mood, V/A, descriptions, motion preview.",
    example: `GET /tracks/jamendo_1007926/timeline

{
  "track_id": "jamendo_1007926",
  "title": "San Frutos",
  "artist": "Ra00",
  "bpm": 136,
  "duration_ms": 313000,
  "segments": [
    {
      "t_start": 0,
      "t_end": 45000,
      "v": 0.2,
      "ar": -0.5,
      "label": "intro",
      "emotion_label": "calm"
    }
  ],
  "motion_preview": [{ "t_ms": 0, "y": 0.42 }]
}`,
  },
  {
    id: "motion",
    method: "GET",
    path: "/tracks/{id}/motion",
    summary:
      "Precomputed motion timeline and playback lookup: full curve, preview, or value at time.",
    example: `# Full timeline
GET /tracks/jamendo_1007926/motion

# Downsampled curve for UI
GET /tracks/jamendo_1007926/motion/preview

# Lookup at playback time (seconds)
GET /tracks/jamendo_1007926/motion/at?t_sec=42.5

{
  "track_id": "jamendo_1007926",
  "t_sec": 42.5,
  "energy": 0.61,
  "vocal": 0.28,
  "valence": 0.35,
  "arousal": 0.72,
  "mood": 0.54
}`,
  },
];

const PLAYER: ApiItem[] = [
  {
    id: "match",
    method: "POST",
    path: "/match",
    summary: "Pick the best next segment from pad position, direction, and session context.",
    example: `POST /match
Content-Type: application/json

{
  "position": { "v": 0.8, "ar": 0.6 },
  "direction": { "v": 0.1, "ar": -0.05 },
  "bpm_current": 120,
  "session_seed": true,
  "exclude_ids": ["jamendo_1007926"]
}

→ {
  "track_id": "jamendo_1036435",
  "title": "…",
  "start_ms": 12400,
  "score": 0.87,
  "crossfade_ms": 3200,
  "segment": { "v": 0.79, "ar": 0.58, "label": "chorus" }
}`,
  },
  {
    id: "prefetch",
    method: "POST",
    path: "/prefetch",
    summary: "L1 intent tree — top candidates per emotional direction around the playhead.",
    example: `POST /prefetch
Content-Type: application/json

{
  "current_track_id": "jamendo_1007926",
  "t_ms": 95000,
  "position": { "v": 0.2, "ar": 0.9 },
  "bpm_current": 136,
  "depth": 1,
  "exclude_ids": ["jamendo_1007926"]
}

→ {
  "current_track_id": "jamendo_1007926",
  "t_ms": 95000,
  "intents": {
    "0": [{ "track_id": "…", "audio_start_ms": 8200, "score": 0.81 }]
  }
}`,
  },
  {
    id: "prefetch-l2",
    method: "POST",
    path: "/prefetch/l2",
    summary: "Deeper prefetch branches for multi-step transition planning.",
    example: `POST /prefetch/l2
Content-Type: application/json

{
  "current_track_id": "jamendo_1007926",
  "t_ms": 95000,
  "position": { "v": 0.2, "ar": 0.9 },
  "bpm_current": 136,
  "candidates_l1": {
    "3": [{ "track_id": "jamendo_1036435", "audio_start_ms": 12400, "score": 0.87 }]
  }
}

→ {
  "intents": {
    "3": [{ "track_id": "…", "audio_start_ms": 5600, "score": 0.79 }]
  }
}`,
  },
  {
    id: "target-entry",
    method: "POST",
    path: "/tracks/{id}/target-entry",
    summary: "Resolve a mood target (V/A) to the best entry segment on a given track.",
    example: `POST /tracks/jamendo_1036435/target-entry
Content-Type: application/json

{
  "target": { "v": 0.75, "ar": 0.55 },
  "after_t_ms": 60000
}

→ {
  "track_id": "jamendo_1036435",
  "start_ms": 12400,
  "segment": {
    "v": 0.79,
    "ar": 0.58,
    "label": "chorus",
    "t_start": 12400,
    "t_end": 48000
  }
}`,
  },
];

function MethodBadge({ method }: { method: "GET" | "POST" }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide ${
        method === "GET"
          ? "bg-emerald-500/15 text-emerald-300/90"
          : "bg-sky-500/15 text-sky-300/90"
      }`}
    >
      {method}
    </span>
  );
}

function ApiGroup({
  title,
  intro,
  items,
  openId,
  onToggle,
}: {
  title: string;
  intro: string;
  items: ApiItem[];
  openId: string | null;
  onToggle: (id: string) => void;
}) {
  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-moony-glow/90">{title}</h3>
        <p className="mt-1 text-sm leading-relaxed text-white/50">{intro}</p>
      </div>
      <ul className="space-y-2">
        {items.map((item) => {
          const expanded = openId === item.id;
          return (
            <li
              key={item.id}
              className={`overflow-hidden rounded-lg border transition-colors ${
                expanded
                  ? "border-moony-accent/30 bg-moony-accent/5"
                  : "border-white/8 bg-white/[0.03]"
              }`}
            >
              <button
                type="button"
                aria-expanded={expanded}
                data-testid={`api-endpoint-${item.id}`}
                onClick={() => onToggle(item.id)}
                className="flex w-full items-start gap-2 px-3 py-2.5 text-left"
              >
                <MethodBadge method={item.method} />
                <span className="min-w-0 flex-1">
                  <code className="block font-mono text-xs text-white/85">{item.path}</code>
                  {!expanded ? (
                    <span className="mt-1 block text-sm leading-snug text-white/40">
                      {item.summary}
                    </span>
                  ) : null}
                </span>
                <span
                  className={`mt-0.5 shrink-0 text-white/35 transition-transform ${
                    expanded ? "rotate-180" : ""
                  }`}
                  aria-hidden
                >
                  ▾
                </span>
              </button>
              {expanded ? (
                <div className="space-y-2 border-t border-white/8 px-3 pb-3 pt-2">
                  <p className="text-sm leading-relaxed text-white/50">{item.summary}</p>
                  <pre className="overflow-x-auto rounded-md border border-white/8 bg-black/35 p-3 font-mono text-[11px] leading-relaxed text-white/70">
                    {item.example}
                  </pre>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function MoonyApiPanel({ open, onClose, onOpenAbout }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);
  const apiBase = getApiBaseUrlLabel();

  const toggle = (id: string) => {
    setOpenId((current) => (current === id ? null : id));
  };

  return (
    <InfoPanelShell open={open} title="API" testId="moony-api-panel" onClose={onClose}>
      <div className="space-y-8">
        {onOpenAbout ? (
          <p className="api-panel-about-link">
            New here?{" "}
            <button type="button" className="api-panel-about-link-btn" onClick={onOpenAbout}>
              Read how Moony works →
            </button>
          </p>
        ) : null}

        <section className="api-quick-start" aria-labelledby="api-quick-start-title">
          <h3 id="api-quick-start-title" className="api-quick-start-title">
            Quick start
          </h3>
          <p className="api-quick-start-base">
            Base URL: <code>{apiBase || "/"}</code>
          </p>
          <pre className="api-quick-start-code">{`POST /match
Content-Type: application/json

{ "position": { "v": 0.5, "ar": 0.3 }, "session_seed": true }

POST /prefetch
Content-Type: application/json

{ "current_track_id": "…", "t_ms": 0, "position": { "v": 0.5, "ar": 0.3 } }`}</pre>
          <p className="api-quick-start-note">
            This demo uses the same endpoints live while you play. Expand below for full request and
            response shapes.
          </p>
        </section>

        <p className="text-sm leading-relaxed text-white/55">
          Core Moony endpoints for catalog owners integrating segment-level mood data and adaptive
          playback. Tap an endpoint to see a usage example.
        </p>

        <ApiGroup
          title="Catalog & track data"
          intro="Read segment-level intelligence from your ingested catalog."
          items={TRACK_DATA}
          openId={openId}
          onToggle={toggle}
        />

        <ApiGroup
          title="Player & navigation"
          intro="Drive mood-adaptive listening sessions in your app."
          items={PLAYER}
          openId={openId}
          onToggle={toggle}
        />
      </div>
    </InfoPanelShell>
  );
}
