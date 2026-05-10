"""Supabase health check — probes the REST API root.

When a Supabase project is paused, the REST endpoint goes down (timeout
or 5xx). When live, ``/rest/v1/`` responds 200. That catches the
paused-project case which was the original "RAYO showed green while
Supabase was down" incident.

Doesn't require the ``supabase-py`` SDK — a raw HTTPS GET with the
project's anon key is enough for a liveness probe. Richer probes (e.g.,
verifying a specific table is queryable through RPC) belong in future
factories like ``supabase_table_check`` and would warrant the SDK extra.
"""
from __future__ import annotations

from typing import Optional

import requests

from .base import CheckFn


def supabase_check(url: str, key: str, timeout: float = 5.0) -> CheckFn:
    """Return a check that probes a Supabase project's REST root.

    Args:
        url: Supabase project URL (https://<ref>.supabase.co), no trailing slash needed.
        key: anon or service-role key — passed in the ``apikey`` header.
        timeout: per-request seconds. Default 5.

    Returns:
        A no-arg callable returning (status, error).
    """
    if not url:
        raise ValueError("url is required")
    if not key:
        raise ValueError("key is required")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    probe_url = url.rstrip("/") + "/rest/v1/"

    def check() -> tuple[str, Optional[str]]:
        try:
            r = requests.get(
                probe_url,
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                timeout=timeout,
            )
        except requests.Timeout:
            return ("fail", f"timeout after {timeout}s")
        except requests.ConnectionError:
            return ("fail", "connection error")
        except requests.RequestException as e:
            return ("fail", type(e).__name__)

        if r.status_code == 200:
            return ("ok", None)
        if r.status_code in (401, 403):
            return ("fail", f"auth failed (HTTP {r.status_code})")
        return ("fail", f"HTTP {r.status_code}")

    return check
