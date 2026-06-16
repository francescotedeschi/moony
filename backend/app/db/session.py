"""Optional PostgreSQL for session metadata — not Musixmatch lyrics storage."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    """Use psycopg v3 (psycopg[binary]); bare postgresql:// defaults to psycopg2."""
    url = get_settings().database_url.strip()
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(_database_url(), pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _session_factory
