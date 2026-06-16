"""Global play counts — used to spread listening across the catalog."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db.models import TrackPlayStat
from app.db.session import Base, get_engine, get_session_factory

logger = logging.getLogger(__name__)

_COUNTS_CACHE_TTL_SEC = 3.0


class PlayStatsStore:
    def __init__(self) -> None:
        self._enabled = False
        self._counts: dict[str, int] = {}
        self._counts_loaded_at = 0.0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def init(self) -> None:
        url = get_settings().database_url
        if not url or url.strip().lower() in ("", "off", "none"):
            logger.info("Play stats disabled (no DATABASE_URL)")
            return
        try:
            engine = get_engine()
            Base.metadata.create_all(engine)
            self._enabled = True
            self._refresh_counts(force=True)
            logger.info("Play stats ready (%d tracks with history)", len(self._counts))
        except Exception as exc:
            logger.warning("Play stats DB unavailable — fairness disabled: %s", exc)
            self._enabled = False

    def _invalidate_counts_cache(self) -> None:
        self._counts_loaded_at = 0.0

    def _refresh_counts(self, *, force: bool = False) -> None:
        if not self._enabled:
            self._counts = {}
            return
        now = time.monotonic()
        if not force and now - self._counts_loaded_at < _COUNTS_CACHE_TTL_SEC:
            return
        with get_session_factory()() as session:
            rows = session.execute(
                select(TrackPlayStat.track_id, TrackPlayStat.play_count)
            ).all()
        self._counts = {tid: int(count) for tid, count in rows}
        self._counts_loaded_at = now

    def get_play_counts(self) -> dict[str, int]:
        self._refresh_counts()
        return dict(self._counts)

    def get_play_count(self, track_id: str) -> int:
        tid = track_id.strip()
        if not tid or not self._enabled:
            return 0
        self._refresh_counts()
        return int(self._counts.get(tid, 0))

    def record_play(self, track_id: str) -> int:
        tid = track_id.strip()
        if not tid:
            return 0
        if not self._enabled:
            return 0
        now = datetime.now(timezone.utc)
        with get_session_factory()() as session:
            row = session.get(TrackPlayStat, tid)
            if row is None:
                row = TrackPlayStat(track_id=tid, play_count=1, last_played_at=now)
                session.add(row)
                new_count = 1
            else:
                row.play_count += 1
                row.last_played_at = now
                new_count = row.play_count
            session.commit()
        self._counts[tid] = new_count
        self._counts_loaded_at = time.monotonic()
        return new_count

    def stats_summary(self) -> dict:
        counts = self.get_play_counts()
        if not counts:
            return {
                "enabled": self._enabled,
                "tracks_with_plays": 0,
                "total_plays": 0,
                "max_play_count": 0,
            }
        values = list(counts.values())
        return {
            "enabled": self._enabled,
            "tracks_with_plays": len(counts),
            "total_plays": sum(values),
            "max_play_count": max(values),
        }


play_stats_store = PlayStatsStore()
