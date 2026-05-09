"""Shared async HTTP helper with retry/backoff and standardized error envelope.

Rules:
  * Never raise — every failure mode must return a JSON-friendly dict.
  * Honor 429 with exponential backoff (max 2 retries: ~1s, ~2s).
  * Always set a polite User-Agent (some upstreams 403 anonymous traffic).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Mapping, Optional

import httpx

log = logging.getLogger("pubrecords.http")

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
DEFAULT_UA = os.getenv(
    "PUBRECORDS_HTTP_USER_AGENT",
    "PubRecordsMCP/0.1 (+https://mcpize.com/pubrecords-mcp)",
)


def error_envelope(reason: str, **extra: Any) -> dict:
    """Standard never-crash error response."""
    body = {"success": False, "error": reason, "cached": False}
    body.update(extra)
    return body


async def fetch_json(
    url: str,
    *,
    method: str = "GET",
    params: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    json_body: Optional[Mapping[str, Any]] = None,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    max_retries: int = 2,
    client: Optional[httpx.AsyncClient] = None,
) -> dict:
    """Fetch JSON with retry on 429/5xx. Returns either decoded JSON or
    an error_envelope dict. The caller can detect failure by checking
    ``result.get("success") is False``.
    """
    merged_headers = {"User-Agent": DEFAULT_UA, "Accept": "application/json"}
    if headers:
        merged_headers.update(headers)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    try:
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                resp = await client.request(
                    method,
                    url,
                    params=params,
                    headers=merged_headers,
                    json=json_body,
                )
            except httpx.HTTPError as exc:  # network / DNS / timeout
                last_exc = exc
                log.warning("http error %s on %s (attempt %d)", exc, url, attempt + 1)
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                return error_envelope("source_unavailable", detail=str(exc))

            if resp.status_code == 429 and attempt < max_retries:
                # Respect Retry-After when present, else exp backoff
                ra = resp.headers.get("Retry-After")
                wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else 2**attempt
                log.warning("429 from %s — sleeping %.1fs", url, wait)
                await asyncio.sleep(wait)
                continue

            if 500 <= resp.status_code < 600 and attempt < max_retries:
                await asyncio.sleep(2**attempt)
                continue

            if resp.status_code >= 400:
                return error_envelope(
                    "upstream_error",
                    status=resp.status_code,
                    detail=resp.text[:500],
                )

            try:
                return resp.json()
            except ValueError:
                return error_envelope(
                    "invalid_json",
                    status=resp.status_code,
                    detail=resp.text[:500],
                )
        return error_envelope("source_unavailable", detail=str(last_exc))
    finally:
        if own_client:
            await client.aclose()
