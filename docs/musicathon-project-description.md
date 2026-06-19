# Moony — adaptive listening powered by segment-level emotion

## What it is

**Moony** is an emotional intelligence layer for music catalogs. Instead of treating each song as a single mood label (“happy”, “chill”, “sad”), it understands how a track *changes over time*—intro, verse, chorus, bridge, outro—and uses that structure to build **listening journeys that follow the listener**, not fixed playlists.

Song structure is not guessed from genre tags or fixed time windows. It is **inferred jointly from the audio and the lyrics**: an LLM reads synced lyric lines (with timestamps) to understand *what* each part of the song is, while **MOSS-Music** listens to the recording to decide *where* those parts begin and end.

The listener controls mood on a **2D emotion pad** (valence × arousal). As they move the pointer, Moony does not simply jump to another “mood playlist”. It searches the catalog for the **best next moment**: a specific section inside a specific song, at a specific entry time, with a smooth transition from what is already playing.

The project is built for the **Musicathon** constraint: **lyrics are never stored in the catalog**. Musixmatch is used only at analysis and playback time (synced LRC), while the published dataset contains IDs, flags, and derived emotional metadata only.

---

## From audio to catalog: the offline pipeline

Every track in the catalog goes through a unified analysis pipeline (`song_analysis.py`), built on an in-repo `analyzer` package.

### 1. Catalog skeleton (Jamendo + Musixmatch)

Tracks come from **Jamendo** (metadata, preview URL, tags). Each track is matched to **Musixmatch** so we know whether synced subtitles exist and can fetch timed lyrics later—but we persist **only reference IDs and flags**, never lyric text.

Before a track is served to listeners, we run quality checks: verify that subtitles are truly timed (LRC), and audit whether the matched lyrics plausibly belong to that title/artist. Tracks flagged as untrusted are excluded from playback.

### 2. Song structure: lyrics (LLM) + audio (MOSS-Music)

A song is split into **sections**—time ranges with labels like *intro*, *verse*, *chorus*, *bridge*, *outro*. That structure is the foundation for segment-level matching. We build it with a **hybrid pipeline** that combines text and audio, because neither source alone is enough:

| Source | What it contributes | Why we need it |
|--------|---------------------|----------------|
| **Synced lyrics (Musixmatch LRC) + LLM** | Semantic structure: which blocks are verses, choruses, bridges, etc., inferred from repeated lines, themes, and narrative flow in the timed lyric text | Lyrics tell you *what* the sections mean, even when the production is subtle |
| **MOSS-Music (audio model)** | Acoustic structure: precise **start/end times** where the arrangement, texture, or energy shifts | Audio tells you *when* the music actually changes, even when lyrics are sparse or instrumental |

**How the hybrid step works (default mode):**

1. **Fetch synced lyrics at analysis time** — Musixmatch LRC is loaded in memory only; it is never written to the catalog (Musicathon rule).
2. **LLM pass on lyrics** — The model segments the song from the timed lyric stream: it groups lines into blocks (e.g. chorus returns, bridge contrast) and assigns a **structure label** to each block.
3. **MOSS-Music pass on audio** — The model analyzes the MP3 and proposes its own section boundaries from what it hears (drops, builds, instrumental breaks, etc.).
4. **Merge** — We keep **MOSS’s timestamps** (musically accurate cuts) and attach the **LLM’s labels** (lyric-aware names). If MOSS falls back to coarse fixed windows, we use the LLM-only structure instead.

The result is a timeline of sections that a human would recognize: the chorus *is* the chorus (lyrics), and it *starts and ends* where the arrangement changes (audio).

After structure is fixed, **MOSS-Music runs again per section** to write a short **caption** of what that slice sounds like (instruments, vocal character, mood of the performance, lyrical topic). Those captions are stored; the raw lyrics are discarded.

### 3. MOSS captions and embeddings

For every section, we take the MOSS **description** and compute a **text embedding** (MiniLM). These embeddings help the matcher prefer sections that feel similar or intentionally different to what is already playing—continuity and contrast, not just mood coordinates.

MOSS does **not** define the emotional coordinates used at playback. That role belongs to Cyanite. MOSS’s role in the pipeline is: **(1) hybrid structure with the LLM, (2) per-section sonic captions.**

### 4. Cyanite: mood, valence/arousal, and energy

**Cyanite** analyzes the full audio and maps onto each section:

- a **mood tag** (e.g. dark, chilled, energetic, sad),
- **valence** and **arousal** (the two axes of the emotion pad),
- a per-section **mood score vector** (fine-grained probabilities across Cyanite’s mood taxonomy).

At track level, Cyanite also provides an **energy curve** over time. The player uses this curve to drive visual intensity and to align transitions with musical dynamics—not a separate legacy “motion” model.

### 5. What ends up in the catalog

The runtime catalog (v1.7) is intentionally **slim**: only what the player and matcher need.

| Per section | Per track |
|-------------|-----------|
| `start_sec` / `end_sec`, `structure_label` (from **LLM + MOSS hybrid**) | Jamendo metadata + `audio_url` |
| MOSS `description` + `embedding` | Musixmatch IDs + trust flags |
| Cyanite mood tag, V/A, mood scores | Cyanite `energy_curve` + timestamps |

Legacy fields (whole-track mood, motion curves, MOSS valence/arousal duplicates) were removed so there is a **single source of truth**: **Cyanite for mood and energy**, **LLM + MOSS for section structure**, **MOSS for sonic descriptions**.

---

## How matching works

Matching is **segment-level**, not track-level. The engine asks: *“Given where the listener wants to go on the pad, what is the best **entry point** into the catalog right now?”*

### The emotion pad

The UI exposes **seven mood zones** on a valence–arousal disc: Energetic, Happy, Chilled, Romantic, Sad, Dark, Tense. When the listener moves the pointer, Moony maps that position to:

1. a **target mood zone** (which sections are eligible), and  
2. a **search coordinate** in catalog valence/arousal space (where inside that zone to aim).

The pad is expressive: small movements within a zone still change the search target, so “happy but calm” and “happy and upbeat” pull different sections.

### Choosing the next moment

For each candidate track, the matcher considers only **upcoming sections** whose mood label matches the target zone. It scores candidates using several signals together:

- **Mood distance** — how close the section’s Cyanite valence/arousal is to the listener’s target.
- **Cyanite mood scores** — finer texture within a zone (e.g. dark vs scary both map to “dark”, but scores break ties).
- **BPM continuity** — prefer musically plausible tempo changes from the current track.
- **Embedding similarity** — continuity with the current section’s MOSS description, or intentional departure after a skip.
- **Track mood depth** — bonus when a large share of a track shares the target mood (richer journeys inside one song).
- **Play fairness** — rotate less-played tracks so the catalog is explored evenly across sessions.

Structural rules keep journeys musical: **no entries in outros**, prefer **mid-track sections** over always starting at the intro, and **each track plays at most once per session** unless the listener explicitly steers into a same-mood handoff on the final section.

### Prefetch and transitions

While a track plays, the backend **prefetches** the best candidates for each mood direction around the pad. That keeps response time low when the listener moves the pointer.

Between tracks, Moony plans a **crossfade** informed by exit/entry valence–arousal and energy levels, so handoffs feel intentional rather than abrupt cuts.

---

## The player experience

The frontend is a **session-based adaptive radio**:

1. The listener places the mood pointer and starts listening.
2. Moony picks a seed track and **entry section** aligned with that mood.
3. Audio streams from Jamendo; optional **synced lyrics** load live from Musixmatch (never from the catalog file).
4. As playback moves through sections, the pad can reflect **current** mood (from Cyanite coordinates at the playhead) while the listener’s pointer expresses **desired** mood.
5. When the target mood changes—or the current section ends—the matcher selects the next segment, crossfades, and updates the journey.

Visual feedback ties to the music: a **fluid simulation** on the pad reacts to playback envelope and the Cyanite **energy curve**, so the interface feels alive with the audio.

The result is not “shuffle by genre” or “pick a playlist and forget it”. It is a **continuous, steerable emotional arc** across many songs—closer to how people actually feel during focus, workout, gaming, or winding down.

---

## Architecture in one sentence

**Offline**, Moony enriches a Jamendo catalog by inferring **section structure from synced lyrics (LLM) and audio (MOSS-Music)**, then layering Cyanite mood/energy and MOSS captions—without ever storing lyrics. **Online**, a segment-level matcher and prefetch layer turn pad input into the next best musical moment, and the player streams it with live synced lyrics and energy-aware visuals.

**Powered by:** MOSS-Music · Musixmatch · Cyanite · Jamendo
