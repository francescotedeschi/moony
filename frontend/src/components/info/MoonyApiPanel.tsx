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
    summary: "Track metadata, macro segments, audio URL, and optional Cyanite energy curve.",
    example: `GET /tracks/jamendo_1007926

{
  "id": "jamendo_1007926",
  "title": "San Frutos",
  "artist": "Ra00",
  "bpm": 136,
  "duration_sec": 313.0,
  "duration_ms": 313000,
  "audio_url": "/tracks/jamendo_1007926/audio",
  "has_energy_curve": true,
  "energy_curve": [0.18, 0.45, 0.30],
  "energy_curve_timestamps_ms": [0, 15000, 30000],
  "segments": [
    { "t_start": 0, "t_end": 45000, "v": 0.2, "ar": -0.5, "label": "intro" }
  ]
}`,
  },
  {
    id: "timeline",
    method: "GET",
    path: "/tracks/{id}/timeline",
    summary:
      "MOSS segment map for UI timelines: mood, V/A, descriptions, Cyanite tags, Musixmatch ref, energy curve.",
    example: `GET /tracks/jamendo_1007926/timeline

{
  "track_id": "jamendo_1007926",
  "title": "San Frutos",
  "artist": "Ra00",
  "bpm": 136,
  "duration_ms": 313000,
  "duration_sec": 313.0,
  "musixmatch": { "commontrack_id": 12345, "track_id": 67890, "lyrics_trusted": true },
  "segments": [
    {
      "t_start": 0,
      "t_end": 45000,
      "v": 0.2,
      "ar": -0.5,
      "label": "intro",
      "emotion_label": "calm",
      "description": "Sparse drums, warm pad",
      "cyanite_mood_tag": "relaxed",
      "cyanite_v": -0.12,
      "cyanite_ar": -0.35
    }
  ],
  "energy_curve": [0.18, 0.45, 0.30],
  "energy_curve_timestamps_ms": [0, 15000, 30000]
}`,
  },
  {
    id: "energy",
    method: "GET",
    path: "/tracks/{id}/energy",
    summary:
      "Cyanite energy curve and playback lookup: full curve, preview, or value at time.",
    example: `# Full curve
GET /tracks/jamendo_1007926/energy

→ {
  "track_id": "jamendo_1007926",
  "energy_curve": [0.18, 0.45, 0.30],
  "energy_curve_timestamps_ms": [0, 15000, 30000]
}

# Downsampled curve for timeline UI
GET /tracks/jamendo_1007926/energy/preview

→ [{ "t_ms": 0, "energy": 0.18 }, { "t_ms": 15000, "energy": 0.45 }]

# Lookup at playback time (seconds)
GET /tracks/jamendo_1007926/energy/at?t_sec=42.5

→ {
  "track_id": "jamendo_1007926",
  "has_energy_curve": true,
  "t_sec": 42.5,
  "energy": 0.61,
  "valence": 0.35,
  "arousal": 0.72
}`,
  },
];

const PLAYER: ApiItem[] = [
  {
    id: "match",
    method: "POST",
    path: "/match",
    summary:
      "Pick the best next segment from pad position, direction, and session context. Returns crossfade and playback-rate plan.",
    example: `POST /match
Content-Type: application/json

{
  "position": { "v": 0.8, "ar": 0.6 },
  "direction": { "v": 0.1, "ar": -0.05 },
  "bpm_current": 120,
  "current_track_id": "jamendo_1007926",
  "current_t_ms": 95000,
  "session_seed": false,
  "pad_only": false,
  "exclude_ids": ["jamendo_1007926"],
  "embedding_penalties": []
}

→ {
  "track_id": "jamendo_1036435",
  "title": "…",
  "artist": "…",
  "bpm": 128,
  "audio_url": "/tracks/jamendo_1036435/audio",
  "start_ms": 12400,
  "score": 0.87,
  "mood_distance": 0.12,
  "mood_quality": "tight",
  "emotion_label": "energetic",
  "segment": {
    "v": 0.79,
    "ar": 0.58,
    "label": "chorus",
    "emotion_label": "energetic",
    "t_start": 12400,
    "t_end": 48000
  },
  "musixmatch": { "commontrack_id": 12345, "lyrics_trusted": true },
  "crossfade_ms": 3200,
  "crossfade_curve": "equal_power",
  "crossfade_start_ms": 91800,
  "playback_rate_start": 1.0,
  "playback_rate_end": 1.067,
  "youtube_playback_gain": 0.82
}`,
  },
  {
    id: "prefetch",
    method: "POST",
    path: "/prefetch",
    summary:
      "L1 intent tree — top candidates per emotional direction around the playhead. Includes embedded L2 branches when depth > 1.",
    example: `POST /prefetch
Content-Type: application/json

{
  "current_track_id": "jamendo_1007926",
  "t_ms": 95000,
  "position": { "v": 0.2, "ar": 0.9 },
  "bpm_current": 136,
  "depth": 2,
  "exclude_ids": ["jamendo_1007926"],
  "same_mood_only": false,
  "single_intent": null,
  "restrict_mood_share": false
}

→ {
  "current_track_id": "jamendo_1007926",
  "t_ms": 95000,
  "intents": {
    "0": [{
      "track_id": "…",
      "title": "…",
      "audio_start_ms": 8200,
      "score": 0.81,
      "segment": { "v": 0.2, "ar": 0.85, "label": "verse" },
      "musixmatch": { "lyrics_trusted": true },
      "crossfade_ms": 2800
    }]
  },
  "l2": {
    "0": {
      "from": { "track_id": "…", "title": "…", "artist": "…" },
      "intents": { "3": [{ "track_id": "…", "audio_start_ms": 5600, "score": 0.79 }] }
    }
  }
}`,
  },
  {
    id: "prefetch-l2",
    method: "POST",
    path: "/prefetch/l2",
    summary: "Background L2 tree from L1 branches already shown to the client.",
    example: `POST /prefetch/l2
Content-Type: application/json

{
  "current_track_id": "jamendo_1007926",
  "l1_intents": {
    "3": [{ "track_id": "jamendo_1036435", "audio_start_ms": 12400, "score": 0.87 }]
  }
}

→ {
  "l2": {
    "3": {
      "from": { "track_id": "jamendo_1036435", "title": "…", "artist": "…" },
      "intents": { "0": [{ "track_id": "…", "audio_start_ms": 5600, "score": 0.79 }] }
    }
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

const LYRICS: ApiItem[] = [
  {
    id: "lyrics",
    method: "GET",
    path: "/tracks/{id}/lyrics",
    summary:
      "Synced lyric lines from Musixmatch (subtitle or snippet). Requires MUSIXMATCH_API_KEY on the server.",
    example: `GET /tracks/jamendo_1007926/lyrics

→ {
  "track_id": "jamendo_1007926",
  "lines": [
    {
      "t_ms": 42040,
      "text": "And save it for a rainy day",
      "line_index": 0,
      "end_ms": 45760
    },
    {
      "t_ms": 66000,
      "text": "Shadows in the moonlight",
      "line_index": 1,
      "end_ms": null
    }
  ],
  "lyrics_copyright": "© …",
  "pixel_tracking_url": "https://…",
  "source": "subtitle"
}`,
  },
  {
    id: "analysis",
    method: "GET",
    path: "/tracks/{id}/analysis",
    summary: "Musixmatch rich-sync analysis payload for a track (word-level timing when available).",
    example: `GET /tracks/jamendo_1007926/analysis

→ {
  "track_id": "jamendo_1007926",
  "analysis": { … }
}`,
  },
  {
    id: "prefetch-lyrics",
    method: "POST",
    path: "/prefetch/lyrics",
    summary:
      "Lyric-aware crossfade anchors for L1 candidates: exit/entry line boundaries and aligned crossfade window.",
    example: `POST /prefetch/lyrics
Content-Type: application/json

{
  "current": { "track_id": "jamendo_1007926", "t_ms": 95000 },
  "candidates_l1": {
    "3": [{ "track_id": "jamendo_1036435", "audio_start_ms": 12400, "score": 0.87 }]
  }
}

→ {
  "intents": {
    "3": {
      "track_id": "jamendo_1036435",
      "title": "…",
      "artist": "…",
      "score_l1": 0.87,
      "exit_anchor": { "line_index": 12, "t_ms": 97200, "text": "…" },
      "entry_anchor": { "line_index": 0, "t_ms": 12400, "text": "…" },
      "crossfade": {
        "crossfade_start_ms": 93200,
        "crossfade_duration_ms": 8000,
        "audio_start_ms": 12300,
        "entry_t_ms": 12400,
        "exit_t_ms": 97200
      },
      "lyrics_copyright": "© …",
      "pixel_tracking_url": "https://…"
    }
  }
}`,
  },
];

const SYSTEM: ApiItem[] = [
  {
    id: "health",
    method: "GET",
    path: "/health",
    summary: "Service status, catalog summary, and play-stats availability.",
    example: `GET /health

→ {
  "status": "ok",
  "service": "moony-api",
  "catalog": {
    "track_count": 120,
    "segment_count": 840,
    "with_musixmatch": 95,
    "lyrics_mode": "musixmatch",
    "matcher": "moss",
    "analyzer": "cyanite"
  },
  "play_stats": { "enabled": true, "total_plays": 4821 }
}`,
  },
  {
    id: "catalog-stats",
    method: "GET",
    path: "/catalog/stats",
    summary: "Catalog metadata: mood distribution, energy coverage, embedding stats.",
    example: `GET /catalog/stats

→ {
  "catalog_name": "jamendo-demo",
  "track_count": 120,
  "segment_count": 840,
  "mood_labels": ["calm", "happy", "energetic", …],
  "with_energy": 118,
  "energy_coverage": 0.98,
  "with_musixmatch": 95,
  "bpm_range": { "min": 72, "max": 168 }
}`,
  },
  {
    id: "play-count",
    method: "GET",
    path: "/tracks/{id}/play-count",
    summary: "Global play count for a track (when play stats are enabled).",
    example: `GET /tracks/jamendo_1007926/play-count

→ {
  "track_id": "jamendo_1007926",
  "play_count": 42,
  "stats_enabled": true
}`,
  },
  {
    id: "played",
    method: "POST",
    path: "/tracks/{id}/played",
    summary: "Increment global play count when the client actually starts playback.",
    example: `POST /tracks/jamendo_1007926/played

→ {
  "track_id": "jamendo_1007926",
  "play_count": 43,
  "stats_enabled": true
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
          Core Moony endpoints for catalog owners integrating segment-level mood data, adaptive
          playback, and synced lyrics. Tap an endpoint to see a usage example.
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

        <ApiGroup
          title="Lyrics & sync"
          intro="Musixmatch-powered lyric lines and crossfade anchors (server key required)."
          items={LYRICS}
          openId={openId}
          onToggle={toggle}
        />

        <ApiGroup
          title="System & stats"
          intro="Health checks, catalog metadata, and optional global play counts."
          items={SYSTEM}
          openId={openId}
          onToggle={toggle}
        />
      </div>
    </InfoPanelShell>
  );
}
