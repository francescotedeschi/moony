from pydantic import BaseModel, Field

from app.models.catalog import VA


class EmbeddingPenaltyRange(BaseModel):
    """MOSS segment play range rejected early in session (skip / same-mood handoff ≤15s)."""

    track_id: str
    from_ms: int = Field(ge=0)
    to_ms: int = Field(ge=0)
    added_at_ms: int = Field(ge=0)


class MatchRequest(BaseModel):
    position: VA
    direction: VA
    bpm_current: int = Field(default=120, ge=40, le=220)
    exclude_ids: list[str] = Field(default_factory=list)
    current_track_id: str | None = None
    current_t_ms: int | None = None
    """When true, match only from pad target (no blend toward next-section motion). Embeddings still apply."""
    pad_only: bool = False
    """First track of a browser session: calm, joy, or energy — fewest global plays."""
    session_seed: bool = False
    """Segment-mood handoff (legacy): next song for playhead mood, mood_distribution ≥ 0.5."""
    same_mood_handoff: bool = False
    embedding_penalties: list[EmbeddingPenaltyRange] = Field(default_factory=list)


class MatchResponse(BaseModel):
    track_id: str
    title: str
    artist: str
    bpm: int
    audio_url: str
    start_ms: int
    score: float
    mood_distance: float | None = None
    mood_quality: str | None = None
    emotion_label: str | None = None
    segment: dict
    musixmatch: dict | None = None
    bpm_from: int | None = None
    bpm_to: int | None = None
    playback_rate_start: float = 1.0
    playback_rate_end: float = 1.0
    playback_rate_out_end: float | None = None
    crossfade_ms: int | None = None
    crossfade_curve: str | None = None
    crossfade_mood_jump: float | None = None
    """When to start the outgoing crossfade on the current track (ms). None = start immediately."""
    crossfade_start_ms: int | None = None
    """Precomputed YouTube-style attenuation (linear ≤ 1) at `start_ms`; omit if unknown."""
    youtube_playback_gain: float | None = Field(default=None, ge=0.0, le=1.0)


class TargetEntryRequest(BaseModel):
    target: VA
    after_t_ms: int | None = Field(default=None, ge=0)


class TargetEntryResponse(BaseModel):
    track_id: str
    start_ms: int
    segment: dict


class PrefetchRequest(BaseModel):
    current_track_id: str
    t_ms: int = 0
    position: VA
    bpm_current: int = 120
    depth: int = Field(default=1, ge=1, le=2)
    """Track IDs already played this session — never offered again in prefetch."""
    exclude_ids: list[str] = Field(default_factory=list)
    """Only prefetch segment-mood slot (intent 0) — playhead mood, not pad target."""
    same_mood_only: bool = False
    """Prefetch one pad zone intent (2=Joy, 3=Energy, …) without other moods."""
    single_intent: int | None = Field(default=None, ge=0, le=7)
    """With ``single_intent``: require mood_distribution ≥ 0.5 for that **target mood** label."""
    restrict_mood_share: bool = False
    embedding_penalties: list[EmbeddingPenaltyRange] = Field(default_factory=list)


class PrefetchL2Request(BaseModel):
    current_track_id: str
    l1_intents: dict[str, list[dict]] = Field(
        description="L1 top candidates per emotion intent (keys 2,3,4,6,7)"
    )


class PrefetchLyricsRequest(BaseModel):
    current: dict
    intents: list[int] = Field(default_factory=lambda: list(range(8)))
    candidates_l1: dict[str, list[dict]] = Field(default_factory=dict)


class LyricLine(BaseModel):
    t_ms: int
    text: str
    line_index: int
    """When Musixmatch inserts an empty timed marker, the line ends there instead of at the next lyric."""
    end_ms: int | None = None


class LyricsResponse(BaseModel):
    track_id: str
    lines: list[LyricLine]
    lyrics_copyright: str = ""
    pixel_tracking_url: str | None = None
    script_tracking_url: str | None = None
    source: str = "subtitle"
