"""Shared pytest fixtures — resolve catalog path from repo root."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CATALOG = _REPO_ROOT / "catalog" / "catalog.json"


def pytest_configure() -> None:
    if _DEFAULT_CATALOG.is_file() and not os.environ.get("CATALOG_PATH"):
        os.environ["CATALOG_PATH"] = str(_DEFAULT_CATALOG)
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"


@pytest.fixture(scope="module")
def catalog():
    from app.catalog.loader import catalog_store

    if not _DEFAULT_CATALOG.is_file():
        pytest.skip(f"catalog not found at {_DEFAULT_CATALOG}")

    catalog_store._loaded = False
    catalog_store.load()
    cat = catalog_store.catalog
    if not cat.tracks:
        pytest.skip("catalog has no tracks")
    return cat
