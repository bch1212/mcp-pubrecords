"""API-key auth + per-day rate limiting.

Tiers:
  - free: 30 calls/day (rolling 24h)
  - pro:  effectively unlimited (1,000,000 / day cap)

Default dev key ``pubrecords-dev-key-001`` is auto-seeded on init at the free
tier so local development works out of the box.
"""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Optional

from .cache import _connect, _lock  # noqa: WPS437 — internal helper reuse

DEV_API_KEY: str = "pubrecords-dev-key-001"
FREE_DAILY_LIMIT: int = 30
PRO_DAILY_LIMIT: int = 1_000_000
DAY_SECONDS: int = 86_400


def register_key(
    key: str,
    tier: str = "free",
    daily_limit: Optional[int] = None,
    path: Optional[str] = None,
) -> None:
    """Insert (or update) an api key row."""
    if daily_limit is None:
        daily_limit = PRO_DAILY_LIMIT if tier == "pro" else FREE_DAILY_LIMIT
    with _lock:
        conn = _connect(path)
        try:
            conn.execute(
                """INSERT INTO api_keys(key, tier, call_count, daily_limit, last_reset)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET
                       tier=excluded.tier,
                       daily_limit=excluded.daily_limit""",
                (key, tier, 0, daily_limit, time.time()),
            )
        finally:
            conn.close()


def get_key_info(key: str, path: Optional[str] = None) -> Optional[dict]:
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT key, tier, call_count, daily_limit, last_reset FROM api_keys WHERE key=?",
            (key,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "key": row[0],
        "tier": row[1],
        "call_count": row[2],
        "daily_limit": row[3],
        "last_reset": row[4],
    }


def check_and_increment(
    key: Optional[str], path: Optional[str] = None
) -> tuple[bool, dict]:
    """Validate key + bump counter atomically.

    Returns ``(allowed, info)``. ``info`` always includes ``tier`` and
    ``remaining`` (for diagnostics) plus ``error`` when ``allowed`` is False.
    """
    if not key:
        return False, {"error": "missing_api_key", "tier": None, "remaining": 0}

    with _lock:
        conn = _connect(path)
        try:
            row = conn.execute(
                "SELECT tier, call_count, daily_limit, last_reset FROM api_keys WHERE key=?",
                (key,),
            ).fetchone()
            if not row:
                return False, {"error": "invalid_api_key", "tier": None, "remaining": 0}
            tier, call_count, daily_limit, last_reset = row
            now = time.time()
            # rolling 24h reset window
            if (now - last_reset) >= DAY_SECONDS:
                call_count = 0
                last_reset = now
            if call_count >= daily_limit:
                conn.execute(
                    "UPDATE api_keys SET call_count=?, last_reset=? WHERE key=?",
                    (call_count, last_reset, key),
                )
                return False, {
                    "error": "rate_limit_exceeded",
                    "tier": tier,
                    "remaining": 0,
                    "upgrade_url": "https://mcpize.com/pubrecords-mcp",
                }
            call_count += 1
            conn.execute(
                "UPDATE api_keys SET call_count=?, last_reset=? WHERE key=?",
                (call_count, last_reset, key),
            )
            return True, {
                "tier": tier,
                "remaining": daily_limit - call_count,
            }
        finally:
            conn.close()


def seed_default_keys(path: Optional[str] = None) -> None:
    """Idempotently insert the public dev key. Safe to call on every boot."""
    info = get_key_info(DEV_API_KEY, path=path)
    if info is None:
        register_key(DEV_API_KEY, tier="free", path=path)
