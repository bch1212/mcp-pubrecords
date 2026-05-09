"""SQLite-backed response cache with TTL.

The cache is keyed on a stable hash of (tool_name, args). Reads return
``None`` past the TTL so the caller can refresh from upstream.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional

DB_PATH: str = os.getenv("PUBRECORDS_DB_PATH", "pubrecords_cache.db")
DEFAULT_TTL: int = int(os.getenv("PUBRECORDS_CACHE_TTL", "86400"))

_lock = threading.Lock()


def _connect(path: Optional[str] = None) -> sqlite3.Connection:
    target = path or DB_PATH
    conn = sqlite3.connect(target, timeout=10, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(path: Optional[str] = None) -> None:
    """Create cache + api_keys tables if they don't exist."""
    with _lock:
        conn = _connect(path)
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS api_keys (
                    key TEXT PRIMARY KEY,
                    tier TEXT NOT NULL DEFAULT 'free',
                    call_count INTEGER NOT NULL DEFAULT 0,
                    daily_limit INTEGER NOT NULL DEFAULT 30,
                    last_reset REAL NOT NULL DEFAULT 0
                )"""
            )
        finally:
            conn.close()


def make_cache_key(tool: str, args: dict) -> str:
    """Stable hash key for (tool, args)."""
    payload = json.dumps({"tool": tool, "args": args}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_cached(
    cache_key: str, ttl: int = DEFAULT_TTL, path: Optional[str] = None
) -> Optional[Any]:
    """Return decoded JSON value if present and within TTL, else None."""
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT value, created_at FROM cache WHERE key=?", (cache_key,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    value, created_at = row
    if (time.time() - created_at) > ttl:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def set_cached(cache_key: str, value: Any, path: Optional[str] = None) -> None:
    """Insert or replace cache entry. Stores JSON-encoded value + timestamp."""
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO cache(key, value, created_at) VALUES(?,?,?)",
            (cache_key, json.dumps(value, default=str), time.time()),
        )
    finally:
        conn.close()


def clear_cache(path: Optional[str] = None) -> None:
    """Drop all cache rows. Test helper."""
    conn = _connect(path)
    try:
        conn.execute("DELETE FROM cache")
    finally:
        conn.close()
