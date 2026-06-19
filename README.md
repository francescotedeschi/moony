# Moony

Adaptive listening powered by **segment-level emotion** — built for the [Musixmatch Musicathon](https://www.musixmatch.com/musicathon) (June 2026).

Drag the mood pad → the matcher finds the best **next section** across a Jamendo catalog enriched with hybrid MOSS + Cyanite analysis → optional **live synced lyrics** (never stored in the catalog).

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, Python 3.12 |
| Frontend | React, Vite, Tailwind |
| Catalog | `catalog/catalog_V17.json` (sections + Cyanite mood/energy) |
| Analysis | `analyzer/` + `pipeline/song_analysis.py` |
| Audio | Jamendo CDN |
| Lyrics | Musixmatch API at **runtime only** |

## Musicathon compliance

- Catalog stores **Musixmatch IDs and flags only** — no lyric or subtitle bodies
- Lyrics fetched via `GET /tracks/{id}/lyrics` at playback time
- In-memory session cache (TTL), not persistent storage

## Quick start

```bash
cp .env.example .env
# catalog/catalog_V17.json is the production catalog (committed)

docker compose up --build
```

- API: http://localhost:8090 (see `API_HOST_PORT` in `.env`)
- Web: http://localhost:5190
- Health: http://localhost:8090/health

## Catalog pipeline

See **[pipeline/README.md](pipeline/README.md)** for the full offline flow (Jamendo → Musixmatch → `song_analysis.py` → validate).

Project description for judges: **[docs/musicathon-project-description.md](docs/musicathon-project-description.md)**.

## API (summary)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health + catalog stats |
| POST | `/match` | Segment-level emotion match |
| POST | `/prefetch` | Intent tree around playhead |
| GET | `/tracks/{id}/timeline` | Sections + Cyanite energy curve |
| GET | `/tracks/{id}/energy/at` | Energy + V/A at play time |
| GET | `/tracks/{id}/lyrics` | Musixmatch subtitle proxy |

## Local tests

```bash
cd backend && pip install -r requirements.txt && pytest
make validate-catalog   # catalog V17 pre-deploy check
make smoke-live         # against running stack
```

## Layout

```
moony/
├── analyzer/           # offline MOSS + Cyanite analysis (in-repo)
├── backend/app/        # FastAPI runtime
├── frontend/src/       # React player
├── catalog/            # catalog_V17.json + example schema
├── pipeline/           # catalog build + song_analysis.py
└── docs/               # Musicathon project description
```
