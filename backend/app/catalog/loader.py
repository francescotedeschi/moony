import json
import logging
from pathlib import Path

from app.catalog.mood_distribution import (
    MOOD_DISTRIBUTION_LABELS,
    compute_mood_distribution,
    dominant_mood,
    segment_pad_mood,
)
from app.catalog.normalize import normalize_catalog
from app.config import get_settings
from app.matching.core import MATCHER_VERSION
from app.models.catalog import Catalog

logger = logging.getLogger(__name__)


def _resolve_catalog_name(data: dict) -> str | None:
    name = data.get("catalog_name") or data.get("name")
    if name:
        return str(name)
    if "jamendo_tags" in data:
        return "Jamendo"
    tracks = data.get("tracks") or []
    if tracks and isinstance(tracks[0], dict) and "jamendo" in tracks[0]:
        return "Jamendo"
    return None


class CatalogStore:
    def __init__(self) -> None:
        self._catalog = Catalog()
        self._loaded = False
        self._meta: dict = {}

    @property
    def catalog(self) -> Catalog:
        if not self._loaded:
            self.load()
        return self._catalog

    @property
    def meta(self) -> dict:
        if not self._loaded:
            self.load()
        return self._meta

    def load(self) -> None:
        path = Path(get_settings().catalog_path)
        if not path.is_file():
            logger.warning("Catalog not found at %s — using empty catalog", path)
            self._catalog = Catalog()
            self._loaded = True
            return

        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        self._meta = {
            k: data[k]
            for k in (
                "version",
                "catalog_schema",
                "catalog_name",
                "emotion_ids",
                "generated_at",
                "analyzer",
                "embedding_model",
                "moss_status",
                "motion_status",
                "source_catalog_version",
            )
            if k in data
        }
        if "catalog_name" not in self._meta:
            catalog_name = _resolve_catalog_name(data)
            if catalog_name:
                self._meta["catalog_name"] = catalog_name
        self._catalog = normalize_catalog(data)
        self._loaded = True
        logger.info("Loaded %d tracks from %s", len(self._catalog.tracks), path)

    def _mood_aggregate(self, tracks: list) -> dict:
        mood_counts = {label: 0 for label in MOOD_DISTRIBUTION_LABELS}
        dominant_track_counts = {label: 0 for label in MOOD_DISTRIBUTION_LABELS}
        segment_total = 0
        for track in tracks:
            for seg in track.segments:
                mood_counts[segment_pad_mood(seg)] += 1
                segment_total += 1
            if not track.segments:
                continue
            if len(track.mood_distribution) == len(MOOD_DISTRIBUTION_LABELS):
                dist = track.mood_distribution
            else:
                dist = compute_mood_distribution(track.segments)
            dominant_track_counts[dominant_mood(dist)] += 1

        if segment_total == 0:
            shares = [0.0] * len(MOOD_DISTRIBUTION_LABELS)
        else:
            shares = [
                round(mood_counts[label] / segment_total, 4)
                for label in MOOD_DISTRIBUTION_LABELS
            ]
        return {
            "segment_count": segment_total,
            "mood_labels": list(MOOD_DISTRIBUTION_LABELS),
            "mood_segment_counts": [mood_counts[label] for label in MOOD_DISTRIBUTION_LABELS],
            "mood_segment_share": shares,
            "dominant_mood_track_counts": [
                dominant_track_counts[label] for label in MOOD_DISTRIBUTION_LABELS
            ],
        }

    def stats(self) -> dict:
        cat = self.catalog
        if not cat.tracks:
            return {
                **self.meta,
                "track_count": 0,
                "with_musixmatch": 0,
                "with_subtitles": 0,
                "with_synced_subtitles": 0,
                "with_energy": 0,
                "energy_coverage": 0.0,
                "lyrics_mode": "off",
                "segment_count": 0,
                "mood_labels": list(MOOD_DISTRIBUTION_LABELS),
                "mood_segment_counts": [0] * len(MOOD_DISTRIBUTION_LABELS),
                "mood_segment_share": [0.0] * len(MOOD_DISTRIBUTION_LABELS),
                "dominant_mood_track_counts": [0] * len(MOOD_DISTRIBUTION_LABELS),
            }

        with_mm = sum(
            1
            for t in cat.tracks
            if t.musixmatch and (t.musixmatch.commontrack_id or t.musixmatch.track_id)
        )
        with_subs = sum(
            1
            for t in cat.tracks
            if t.musixmatch and t.musixmatch.has_subtitles
        )
        with_synced_subs = sum(
            1
            for t in cat.tracks
            if t.musixmatch and t.musixmatch.has_synced_subtitles
        )
        with_energy = sum(1 for t in cat.tracks if t.has_energy_curve)
        with_loudness = sum(1 for t in cat.tracks if t.loudness)
        total = len(cat.tracks)
        with_emb = sum(
            1
            for t in cat.tracks
            for s in t.segments
            if s.embedding
        )
        mood_agg = self._mood_aggregate(cat.tracks)
        return {
            **self.meta,
            "matcher": MATCHER_VERSION,
            "segments_with_embedding": with_emb,
            "avg_segments_per_track": round(mood_agg["segment_count"] / total, 1) if total else 0.0,
            **mood_agg,
            "track_count": total,
            "with_musixmatch": with_mm,
            "with_subtitles": with_subs,
            "with_synced_subtitles": with_synced_subs,
            "with_energy": with_energy,
            "energy_coverage": round(with_energy / total, 4) if total else 0.0,
            "with_loudness": with_loudness,
            "loudness_coverage": round(with_loudness / total, 4) if total else 0.0,
            "lyrics_mode": "musixmatch" if with_mm else "off",
            "bpm_range": {
                "min": min(t.bpm for t in cat.tracks),
                "max": max(t.bpm for t in cat.tracks),
            },
        }


catalog_store = CatalogStore()
