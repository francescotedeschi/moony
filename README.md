# Moony

Emotion-driven music navigation for the **Musixmatch Musicathon** (June 2026).

Drag the mood pad → vector matching over a MOSS-enriched Jamendo catalog → **live Musixmatch lyrics** (no lyrics stored in catalog).

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, Python 3.12 |
| Frontend | React, Vite, Tailwind |
| Catalog | `catalog/catalog.json` (MOSS segments — **you provide**) |
| Audio | Jamendo CDN URLs |
| Lyrics | Musixmatch Pro API at **runtime only** |
| Dev DB | PostgreSQL 16 (Docker) — optional, not required for MVP |
| Prod | Railway |

## Musicathon compliance

- `catalog.json` contains **Musixmatch IDs only** — never lyrics/subtitle bodies
- Lyrics fetched via `GET /tracks/{id}/lyrics` with tracking + copyright in UI
- In-memory session cache (TTL), not persistent storage

## Quick start

```bash
cp .env.example .env
cp catalog/catalog.example.json catalog/catalog.json   # or your MOSS export

docker compose up --build
```

- API: http://localhost:8000  
- Web: http://localhost:5173  
- Health: http://localhost:8000/health  

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health + catalog stats |
| GET | `/catalog/stats` | Track counts |
| POST | `/match` | Emotion + metric match |
| POST | `/prefetch` | 8 intents × top 3 (L1) |
| POST | `/prefetch/lyrics` | Lyric anchors (L2, Musixmatch live) |
| GET | `/tracks/{id}/lyrics` | Subtitle/snippet proxy |
| GET | `/tracks/{id}/analysis` | Lyric Lens |
| GET | `/jamendo/tracks` | Jamendo proxy |

## Catalog (your MOSS JSON)

Copy your extracted file to `catalog/catalog.json`. Schema: see `catalog/catalog.example.json`.

Required per track:

```json
{
  "id": "jamendo_…",
  "title": "…",
  "artist": "…",
  "bpm": 110,
  "audio_url": "https://mp3l.jamendo.com/…",
  "musixmatch": { "commontrack_id": "…", "track_id": "…", "has_subtitles": 1, "has_lyrics": 1 },
  "beat_grid": { "offset_ms": 0, "bar_ms": 2182 },
  "segments": [{ "t_start": 0, "t_end": 45000, "v": 0.7, "ar": -0.6, "label": "intro" }],
  "transitions": [{ "from_seg": 0, "to_seg": 1, "dv": -0.2, "dar": 0.7 }]
}
```

## Railway deploy

1. **API service** — root `backend/`, set env vars from `.env.example`, mount or bake `catalog.json`
2. **Web service** — root `frontend/`, build arg `VITE_API_URL=https://your-api.up.railway.app`, Dockerfile target `production`

## Local tests

```bash
cd backend && pip install -r requirements.txt && pytest
```

## Project layout

```
moony/
├── backend/app/          # FastAPI
├── frontend/src/         # React
├── catalog/              # catalog.json (gitignored)
├── pipeline/             # offline MOSS / enrich docs
└── docker-compose.yml
```
