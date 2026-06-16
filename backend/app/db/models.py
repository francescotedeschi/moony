"""Persistent listening stats (not Musixmatch / catalog content)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TrackPlayStat(Base):
    __tablename__ = "track_play_stats"

    track_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_played_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
