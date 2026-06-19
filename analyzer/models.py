from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class JamendoInfo(BaseModel):
    track_id: int
    audio_url: str
    audiodownload_allowed: bool = False
    license_cc: str = ""
    tags: list[str] = Field(default_factory=list)
    listens_total: int = 0
    popularity_total: float = 0.0
    local_audio_path: str = ""


class MusixmatchStub(BaseModel):
    """Musixmatch IDs and flags only — never store lyrics here."""

    commontrack_id: str | int | None = None
    track_id: str | int | None = None
    has_lyrics: bool | int = False
    has_subtitles: bool | int = False
    match_status: str = "pending"


class CyaniteStub(BaseModel):
    """Cyanite track-level outputs (full raw analysis lives in cache)."""

    library_track_id: str | None = None
    status: str = "pending"
    segment_timestamps_sec: list[float] = Field(default_factory=list)
    energy_curve: list[float] = Field(default_factory=list)
    error_message: str = ""


class CatalogSection(BaseModel):
    """v1.7 section: MOSS structure + description + embedding; mood from Cyanite."""

    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    structure_label: str = ""
    cyanite_mood_tag: str = ""
    cyanite_mood_score: float = 0.0
    cyanite_mood_scores: dict[str, float] = Field(default_factory=dict)
    cyanite_valence: float = 0.0
    cyanite_arousal: float = 0.0
    description: str = ""
    embedding_model: str = ""
    embedding: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def _end_after_start(self) -> CatalogSection:
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be greater than start_sec")
        return self


class CatalogV17Track(BaseModel):
    id: str
    title: str
    artist: str
    duration_sec: float
    bpm: int = Field(default=0, ge=0)
    jamendo: JamendoInfo
    sections: list[CatalogSection] = Field(default_factory=list)
    musixmatch: MusixmatchStub = Field(default_factory=MusixmatchStub)
    cyanite: CyaniteStub = Field(default_factory=CyaniteStub)


class CatalogV17Document(BaseModel):
    version: str = "1.7"
    catalog_schema: str = "moodpad-catalog-musicathon"
    generated_at: str
    catalog_name: str = ""
    embedding_model: str = ""
    source_catalog_version: str = ""
    source_track_count: int = 0
    tracks: list[CatalogV17Track] = Field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
