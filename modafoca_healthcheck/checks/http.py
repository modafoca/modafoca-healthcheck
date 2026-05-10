"""Generic HTTP probe — useful for any service exposing a public endpoint."""
from __future__ import annotations

from typing import Iterable, Optional

import requests

from .base import CheckFn


def http_check(
    url: str,
    timeout: float = 5.0,
    expected_status_codes: Optional[Iterable[int]] = None,
    method: str = "GET",
) -> CheckFn:
    """Return a check that GETs ``url`` and verifies the response.

    Args:
        url: full URL (https://...).
        timeout: per-request seconds. Default 5.
        expected_status_codes: if provided, only these codes are "ok"; the
            check fails on anything else. Default None means "any 2xx/3xx".
        method: HTTP method. GET by default; some services prefer HEAD.

    Returns:
        A no-arg callable returning (status, error).
    """
    if not url:
        raise ValueError("url is required")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    expected = list(expected_status_codes) if expected_status_codes is not None else None

    def check() -> tuple[str, Optional[str]]:
        try:
            r = requests.request(
                method=method,
                url=url,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.Timeout:
            return ("fail", f"timeout after {timeout}s")
        except requests.ConnectionError:
            return ("fail", "connection error")
        except requests.RequestException as e:
            return ("fail", type(e).__name__)

        if expected is not None:
            if r.status_code in expected:
                return ("ok", None)
            return ("fail", f"HTTP {r.status_code} (expected {expected})")
        if 200 <= r.status_code < 400:
            return ("ok", None)
        return ("fail", f"HTTP {r.status_code}")

    return check
