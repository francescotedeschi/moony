# Pipeline (offline)

Scripts for building `catalog/catalog.json` from Jamendo + MOSS + Musixmatch match IDs.

**Musicathon rule:** do not persist Musixmatch lyrics/subtitles in the catalog.

## Flow

```
Jamendo sample
  → Musixmatch match (IDs + flags only)
  → download preview (temp)
  → MOSS-Music analysis        → segments, transitions, V/A
  → enrich_metrics.py (TODO)   → bpm, beat_grid from same preview
  → write catalog.json
  → delete preview file
```

## Catalog v1.7 (Musixmatch-only, MOSS pending)

`catalog/catalog_V17.json` — 421 Jamendo tracks with Musixmatch IDs, no segments/motion.
Rebuild from the working catalog:

```bash
python3 pipeline/build_catalog_v17.py
```

Expand with more Jamendo↔Musixmatch matches:

```bash
python3 pipeline/expand_catalog_jamendo.py --target 200
python3 pipeline/match_musixmatch.py catalog/catalog.json
```

## Your MOSS output

Place your extracted JSON as `catalog/catalog.json` (gitignored) or merge into the schema in `catalog.example.json`.

Required fields per track:

- `id`, `title`, `artist`, `bpm`, `audio_url`
- `musixmatch`: `{ commontrack_id, track_id, has_subtitles, has_lyrics }` — **no lyrics text**
- `segments[]`, `transitions[]`
- optional `beat_grid`: `{ offset_ms, bar_ms }`

## Staging previews

Optional: `pipeline/data/previews/` (gitignored) to re-run `enrich_metrics` without re-downloading.

## Validate before deploy

Check V/A ranges, placeholder `(0, 0)` segments, and transition deltas:

```bash
python3 pipeline/validate_catalog.py
# or
python3 pipeline/validate_catalog.py catalog/catalog.json --verbose
make validate-catalog
```

Expected ranges (MoodPad / Moony convention, **not** official MOSS):

| Field | Range |
|-------|-------|
| `valence` / `v`, `arousal` / `ar` | **[-1, 1]** |
| `dv` / `dar` (transitions) | **[-1, 1]** |

- **ERROR** — value outside range (blocks deploy; exit code 1)
- **WARN** — segment with `(0, 0)` placeholder (MOSS did not return coordinates)

Use `--strict` to fail on warnings too.
