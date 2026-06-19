# Pipeline catalog V17

Script offline per produrre `catalog/catalog_V17.json`: il formato che il player carica a runtime.

**Regola Musicathon:** i testi Musixmatch si usano solo in analisi (LRC sincronizzato). Non vanno mai scritti nel catalogo — solo ID e flag.

## Flusso

```
Jamendo + Musixmatch IDs     → catalogo scheletro (metadata, nessuna analisi)
MP3 locali                   → ALL_AUDIO_DIR/{jamendo_id}.mp3
song_analysis.py             → sections MOSS + Cyanite mood/energy
Verifica Musixmatch          → has_synced_subtitles, lyrics_trusted
validate_catalog.py          → controllo pre-deploy
```

## Schema output (per track)

Il player legge solo questi campi. Tutto il resto viene ignorato o ricalcolato in backend.

**Track:** `id`, `title`, `artist`, `duration_sec`, `bpm`, `jamendo`, `musixmatch`, `sections`, `cyanite`

**Section:** `start_sec`, `end_sec`, `structure_label`, `description`, `embedding`, `embedding_model`, `cyanite_mood_tag`, `cyanite_mood_score`, `cyanite_mood_scores`, `cyanite_valence`, `cyanite_arousal`

**Cyanite (track):** `energy_curve`, `segment_timestamps_sec`, `status`

| Fonte | Campi |
|-------|-------|
| Jamendo | metadata, `audio_url` |
| Musixmatch | `track_id`, `commontrack_id`, flag lyrics/subtitles, `lyrics_trusted` |
| MOSS | struttura, `description`, `embedding` |
| Cyanite | mood/V-A per section, `energy_curve` |

Mood ed energia in playback arrivano da **Cyanite**. MOSS non fornisce più coordinate V/A.

## 1. Catalogo scheletro

Due modi per ottenere un catalogo con brani Jamendo e match Musixmatch, senza sections:

**Da catalogo esistente** (tiene solo brani già matchati):

```bash
python3 pipeline/build_catalog_v17.py
```

**Espansione** (cerca nuovi brani vocali su Jamendo e pre-match Musixmatch):

```bash
python3 pipeline/expand_catalog_jamendo.py --target 200
python3 pipeline/match_musixmatch.py catalog/catalog_V17.json
```

Output: `catalog/catalog_V17.json`

## 2. Audio locale

Ogni brano analizzato richiede il file:

```
$ALL_AUDIO_DIR/{jamendo_id}.mp3
```

Esempio: `data/all_audio/1036435.mp3` per `jamendo_1036435`.

## 3. Analisi (`song_analysis.py`)

Entry point unico. Per ogni brano:

1. **Struttura** — hybrid di default (tagli MOSS + label da lyrics LLM)
2. **MOSS** — caption per section → `description`
3. **Embedding** — MiniLM dalla description
4. **Cyanite** — mood tag, V/A per section, `energy_curve` a livello track

Dipende dal package in-repo ``analyzer/`` (stesso repository).

```bash
# Un brano
python3 pipeline/song_analysis.py \
  --catalog catalog/catalog_V17.json \
  --track-id jamendo_1036435

# Batch completo
python3 pipeline/song_analysis.py \
  --catalog catalog/catalog_V17.json \
  --output catalog/catalog_V17.json

# Solo MOSS (senza API Cyanite)
python3 pipeline/song_analysis.py \
  --catalog catalog/catalog_V17.json \
  --limit 10 \
  --skip-cyanite

# Solo Cyanite (sections già presenti)
python3 pipeline/song_analysis.py \
  --catalog catalog/catalog_V17.json \
  --cyanite-only
```

Opzioni utili: `--structure-source hybrid|moss|lyrics-llm`, `--force`, `--no-resume`.

## 4. Verifica Musixmatch

Prima del deploy, il backend esclude i brani con `lyrics_trusted: false`.

```bash
# Flag LRC sincronizzato (live API)
python3 pipeline/verify_musixmatch_subtitles.py

# Audit trust (metadata mismatch, testi gospel su pop, ecc.)
python3 pipeline/audit_musixmatch_lyrics.py --apply
```

## 5. Validazione pre-deploy

```bash
python3 pipeline/validate_catalog.py catalog/catalog_V17.json
make validate-catalog
```

Controlla range V/A Cyanite, sections vuote o invalide, copertura minima per il matching.

## Variabili d'ambiente

| Variabile | Uso |
|-----------|-----|
| `ALL_AUDIO_DIR` | Cartella MP3 locali |
| `MUSIXMATCH_API_KEY` | Match ID + fetch LRC runtime |
| `MOSS_BACKEND`, `MOSS_SGLANG_BASE_URL` oppure `MOSS_MUSIC_REPO` + `MOSS_MODEL_PATH` | Analisi MOSS (GPU) |
| `OPENAI_API_KEY` o `LYRICS_LLM_API_KEY` | Struttura hybrid / lyrics-llm |
| `V17_STRUCTURE_SOURCE` | Default `hybrid` |
| `EMBEDDING_MODEL` | Default `sentence-transformers/all-MiniLM-L6-v2` |
| `CYANITE_ACCESS_TOKEN` | Mood + energy curve |
| `CYANITE_CACHE_DIR` | Cache analisi Cyanite |

Copia `.env` nella root del progetto o definisci le variabili elencate sopra.
