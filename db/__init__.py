"""PubRecords MCP — persistence layer (SQLite)."""
from .cache import init_db, get_cached, set_cached, make_cache_key, DB_PATH
from .keys import (
    register_key,
    check_and_increment,
    get_key_info,
    seed_default_keys,
    DEV_API_KEY,
    PRO_DAILY_LIMIT,
    FREE_DAILY_LIMIT,
)

__all__ = [
    "init_db",
    "get_cached",
    "set_cached",
    "make_cache_key",
    "DB_PATH",
    "register_key",
    "check_and_increment",
    "get_key_info",
    "seed_default_keys",
    "DEV_API_KEY",
    "PRO_DAILY_LIMIT",
    "FREE_DAILY_LIMIT",
]
