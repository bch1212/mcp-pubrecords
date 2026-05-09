"""Shared pytest fixtures.

We point the SQLite cache at a per-test temp file so tests run in
isolation and don't collide with the dev cache.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so tests can import server/db/tools
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Each test gets its own SQLite file."""
    db_file = tmp_path / "test_cache.db"
    monkeypatch.setenv("PUBRECORDS_DB_PATH", str(db_file))

    # Re-import the cache module so DB_PATH picks up the env var
    import importlib

    from db import cache as cache_mod
    from db import keys as keys_mod

    importlib.reload(cache_mod)
    importlib.reload(keys_mod)
    cache_mod.init_db()
    keys_mod.seed_default_keys()
    yield db_file
