from pydantic import BaseModel, Field, model_validator


class VA(BaseModel):
    v: float = Field(ge=-1.0, le=1.0)
    ar: float = Field(ge=-1.0, le=1.0)


class MusixmatchRef(BaseModel):
    commontrack_id: str | None = None
    track_id: str | None = None
    has_subtitles: int = 0
    has_lyrics: int = 0


class BeatGrid(BaseModel):
    offset_ms: int = 0
    bar_ms: int = 2000


class Segment(BaseModel):
    t_start: int
    t_end: int
    v: float
    ar: float
    label: str = "unknown"
    emotion_label: str = ""
    description: str = ""
    moss_emotion_label: str = ""
    essentia_emotion_label: str = ""
    embedding: list[float] = Field(default_factory=list)
    bar_count: int | None = None


class Transition(BaseModel):
    from_seg: int
    to_seg: int
    dv: float
    dar: float


class TrackLoudness(BaseModel):
    """EBU R128 integrated over the track (first MAX_ANALYZE_SEC from t=0)."""

    integrated_lufs: float
    true_peak_dbfs: float
    youtube_gain: float = Field(ge=0.0, le=1.0)


class TrackMotion(BaseModel):
    """Smooth playback timeline (precomputed offline — do not recompute at runtime)."""

    hop_sec: float = Field(default=1.0, gt=0)
    energy: list[float] = Field(default_factory=list)
    vocal: list[float] = Field(default_factory=list)
    valence_smooth: list[float] = Field(default_factory=list)
    arousal_smooth: list[float] = Field(default_factory=list)
    mood: list[float] = Field(default_factory=list)


class Track(BaseModel):
    id: str
    title: str
    artist: str
    bpm: int
    audio_url: str
    duration_sec: float | None = None
    jamendo_tags: list[str] = Field(default_factory=list)
    musixmatch: MusixmatchRef | None = None
    beat_grid: BeatGrid | None = None
    segments: list[Segment] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    motion: TrackMotion | None = None
    """Precomputed track loudness (instant YouTube-style gain at playback)."""
    loudness: TrackLoudness | None = None
    """Mood mix [calm, joy, energy, tension, sad] — segment counts / total segments."""
    mood_distribution: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ensure_mood_distribution(self) -> "Track":
        from app.catalog.mood_distribution import compute_mood_distribution

        expected = compute_mood_distribution(self.segments)
        self.mood_distribution = expected
        return self

    @property
    def has_motion(self) -> bool:
        return self.motion is not None and len(self.motion.energy) > 0


class Catalog(BaseModel):
    tracks: list[Track] = Field(default_factory=list)

    def get_track(self, track_id: str) -> Track | None:
        for track in self.tracks:
            if track.id == track_id:
                return track
        return None
