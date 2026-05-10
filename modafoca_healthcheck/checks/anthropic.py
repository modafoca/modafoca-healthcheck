"""Anthropic API health check — probes the models list endpoint.

``GET /v1/models`` is the cheapest authenticated call on the Anthropic
API. Free, fast, doesn't burn message tokens. Validates that:

* the API endpoint is reachable
* the API key is still valid and not revoked

Note: this verifies auth + connectivity but doesn't prove the *messages*
endpoint specifically is healthy. For services whose product depends on
``messages.create``, a tiny ``max_tokens=1`` round-trip would be a
truer readiness signal. Worth a separate ``anthropic_messages_check``
factory in a future release; ``models`` is the right v0.2.0 default.

Uses plain HTTPS via ``requests``. No need for the ``anthropic`` SDK
just to call a documented public endpoint.
"""
from __future__ import annotations

from typing import Optional

import requests

from .base import CheckFn

ANTHROPIC_VERSION = "2023-06-01"  # the only supported value as of writing


def anthropic_check(
    api_key: str,
    timeout: float = 5.0,
    base_url: str = "https://api.anthropic.com",
) -> CheckFn:
    """Return a check that probes Anthropic's models endpoint.

    Args:
        api_key: ``ANTHROPIC_API_KEY`` value.
        timeout: per-request seconds. Default 5.
        base_url: override for testing; should not be set in production.

    Returns:
        A no-arg callable returning (status, error).
    """
    if not api_key:
        raise ValueError("api_key is required")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    probe_url = base_url.rstrip("/") + "/v1/models"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
    }

    def check() -> tuple[str, Optional[str]]:
        try:
            r = requests.get(probe_url, headers=headers, timeout=timeout)
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
        if r.status_code == 429:
            return ("fail", "rate limited")
        return ("fail", f"HTTP {r.status_code}")

    return check
