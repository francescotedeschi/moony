"""Official MOSS-Music prompt strings (OpenMOSS/MOSS-Music)."""

from __future__ import annotations

# moss_music_usage_guide.md — basic music description (generic; not used for catalog segments)
PROMPT_DETAILED_DESCRIPTION = "Please give a detailed musical description of this clip."

# Catalog pass-2: structured segment caption (clip-level, no hallucination).
CATALOG_CAPTION_PROMPT = (
    "Describe ONLY what is audible in this short audio clip.\n"
    "Do not invent instruments, vocals, mood, or lyrics you cannot hear.\n"
    "Do not quote or transcribe lyrics — only summarize what they seem to be about.\n"
    "If something is unclear, write \"unknown\" or \"none\".\n\n"
    "Reply with exactly these four lines and nothing else:\n"
    "Voice: <who sings/speaks and how — e.g. male/female, tone, style; or \"instrumental\">\n"
    "Mood: <emotional feel of this clip in a few words>\n"
    "Instruments: <main instruments or sounds that stand out>\n"
    "Lyrics topic: <theme/subject of the words in this clip; or \"none\" if instrumental>"
)

# moss_music_usage_guide.md — harmonic / emotional analysis
PROMPT_HARMONIC_EMOTIONAL = (
    "Please analyze the harmonic structure and emotional progression of this piece."
)

# app.py Gradio examples — structural segmentation
PROMPT_SEGMENT_SECTIONS = "Segment the song into verse / chorus / bridge sections."

# app.py DEFAULT_QUESTION (multilingual, style/genre/structure/mood)
PROMPT_MULTIDIM_DESCRIPTION_ZH = (
    "请从风格与速度、调性与和声、乐器编配、结构安排以及整体情绪几个方面描述这段音乐。"
)

CATALOG_STRUCTURE_PROMPT = (
    "Segment the song into structural sections (intro, verse, chorus, bridge, outro).\n"
    "Output ONLY one line per section in this exact format:\n"
    "[MM:SS-MM:SS] Label: short inline description\n"
    "Use timestamps from the start of the track. Cover the full duration with contiguous sections."
)


def build_structure_prompt_with_lyrics(lyrics_text: str) -> str:
    return (
        "Segment the song into structural sections (intro, verse, chorus, bridge, outro).\n"
        "Use the synced lyrics timestamps below to align section boundaries with the vocal content.\n"
        "Output ONLY one line per section in this exact format:\n"
        "[MM:SS-MM:SS] Label: short inline description\n"
        "Use timestamps from the start of the track. Cover the full duration with contiguous sections.\n\n"
        "Synced lyrics (timestamped — use these to locate verse/chorus/bridge boundaries):\n"
        f"{lyrics_text.strip()}"
    )


def build_caption_prompt_with_lyrics(section_lyrics: str, structure_label: str) -> str:
    label = structure_label or "section"
    lyrics_block = section_lyrics.strip() or "(no synced lyrics in this section)"
    return (
        f"Describe ONLY what is audible in this short audio clip ({label} section).\n"
        "Do not invent instruments, vocals, or mood you cannot hear.\n"
        "Do not quote or transcribe lyrics verbatim — only summarize what they seem to be about.\n"
        "If something is unclear, write \"unknown\" or \"none\".\n\n"
        "Lyrics in this section (context only — do not copy into output):\n"
        f"{lyrics_block}\n\n"
        "Reply with exactly these four lines and nothing else:\n"
        "Voice: <who sings/speaks and how; or \"instrumental\">\n"
        "Mood: <emotional feel of this clip in a few words>\n"
        "Instruments: <main instruments or sounds that stand out>\n"
        "Lyrics topic: <theme/subject of the words; or \"none\" if instrumental>"
    )

# Per-segment caption: structured clip prompt (see CATALOG_CAPTION_PROMPT above).
DEFAULT_MAX_NEW_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TOP_P = 1.0
DEFAULT_TOP_K = 50

# moss_segment_caption modes (Settings.moss_segment_caption):
# - all: MOSS caption on every segment clip (recommended for catalog v1.5)
# - missing: caption only segments without inline text from structure pass
# - off: keep structure-pass descriptions only (no per-segment caption calls)
SEGMENT_CAPTION_ALL = "all"
SEGMENT_CAPTION_MISSING = "missing"
SEGMENT_CAPTION_OFF = "off"
